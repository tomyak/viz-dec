"""One on-demand model process per installation, shared over a private Unix socket.

The lifetime flock is inherited by the child before startup, so simultaneous MCP
clients cannot load duplicate models, even during slow startup or stale-socket recovery.
No login service, TCP listener, pickle deserialization, or inference retry is involved.
"""

import argparse
import fcntl
import hashlib
import json
import os
import signal
import socket
import socketserver
import stat
import subprocess
import sys
import tempfile
import threading
import time
from importlib.metadata import version
from pathlib import Path

from ..runtime import EngineWorker
from .contracts import BatchRequest, ClassifyRequest, HealthRequest, InspectRequest, VideoRequest
from .settings import installation_home, load_settings

IDLE_SECONDS = 300
MAX_REQUEST = 1024 * 1024
MAX_RESPONSE = 64 * 1024 * 1024
CONTRACTS = {
    "model_health": HealthRequest,
    "classify_image": ClassifyRequest,
    "inspect_image": InspectRequest,
    "analyze_video": VideoRequest,
    "analyze_batch": BatchRequest,
}


def installation_digest(home):
    return hashlib.sha256(str(Path(home).resolve()).encode()).hexdigest()[:20]


def runtime_directory(home):
    base = os.getenv("TMPDIR")
    if not base and sys.platform == "darwin":
        # Some MCP hosts filter TMPDIR. Recover the user's normal macOS temp root
        # so those clients still find the same daemon as terminal/skill clients.
        base = subprocess.check_output(
            ["/usr/bin/getconf", "DARWIN_USER_TEMP_DIR"], text=True, timeout=5
        ).strip()
    root = Path(base or tempfile.gettempdir())
    if not root.is_absolute():
        raise ValueError("TMPDIR must be an absolute, writable directory")
    # Keep the supplied spelling: resolving /var to /private/var wastes socket bytes.
    path = root / f"vd-{os.getuid()}-{installation_digest(home)}"
    if len(os.fsencode(path / "engine.sock")) > 103:
        raise ValueError("TMPDIR is too long for a Unix socket; use a shorter writable TMPDIR")
    path.mkdir(mode=0o700, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError(f"Expected an owner-only runtime directory: {path}")
    return path


def acquire_engine_locks(home):
    """Lock one installation even when clients have different sandbox temp roots.

    flock supports read-only directory descriptors on macOS and Linux. No write to
    the installation is needed. Keep any pre-0.5.0 lifetime lock too, if it exists,
    so an older resident daemon cannot overlap a new model during an upgrade.
    """
    descriptors = []
    try:
        descriptors.append(os.open(home, os.O_RDONLY | os.O_DIRECTORY))
        legacy = Path("/tmp") / f"visual-decider-{os.getuid()}-{installation_digest(home)}"
        try:
            descriptors.append(os.open(legacy / "engine.lock", os.O_RDONLY | os.O_NOFOLLOW))
        except FileNotFoundError:
            pass
        for descriptor in descriptors:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return descriptors
    except BaseException:
        for descriptor in descriptors:
            os.close(descriptor)
        raise


def fingerprint(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


def exchange(path, request, *, timeout=3600):
    data = json.dumps(request, allow_nan=False).encode() + b"\n"
    if len(data) > MAX_REQUEST:
        raise ValueError("Shared engine request exceeds 1 MiB")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout)
        connection.connect(str(path))
        connection.sendall(data)
        with connection.makefile("rb") as stream:
            result = stream.readline(MAX_RESPONSE + 1)
    if not result:
        raise ConnectionResetError("Shared engine disconnected before returning a result")
    if len(result) > MAX_RESPONSE or not result.endswith(b"\n"):
        raise RuntimeError("Shared engine returned an oversized or incomplete response")
    response = json.loads(result)
    if "error" in response:
        raise RuntimeError(response["error"])
    return response["result"]


class SharedClient:
    def __init__(self, *, home=None, model=None, roots=None):
        self.home = Path(home or installation_home()).expanduser().resolve()
        if not self.home.exists():
            self.home.mkdir(parents=True, exist_ok=True)
        self.runtime = runtime_directory(self.home)
        self.socket = self.runtime / "engine.sock"
        self.model, self.roots = model, roots

    def status(self):
        try:
            return exchange(self.socket, {"operation": "status"}, timeout=5)
        except (FileNotFoundError, ConnectionError):
            return {"status": "stopped", "loaded": False}

    def stop(self):
        if self.status()["status"] == "stopped":
            return {"status": "stopped"}
        return exchange(self.socket, {"operation": "stop"}, timeout=5)

    def configuration(self):
        settings = load_settings(self.home)
        return {
            "version": version("visual-decider"),
            "model": self.model or settings.get("model"),
            "roots": self.roots or settings["roots"],
        }

    def ensure_running(self, config):
        expected = fingerprint(config)
        deadline = time.monotonic() + 30
        child = None
        while time.monotonic() < deadline:
            status = self.status()
            if status["status"] == "running":
                if status["fingerprint"] == expected:
                    return expected
                if status["active_requests"]:
                    raise RuntimeError(
                        "Shared engine is busy with another configuration; retry after it finishes"
                    )
                # Do not let an older agent session replace a newer installed service.
                if tuple(map(int, status["version"].split("."))) > tuple(
                    map(int, config["version"].split("."))
                ):
                    raise RuntimeError(
                        "A newer shared engine is running; restart this agent session"
                    )
                self.stop()
            if status["status"] == "stopped":
                if child is not None and child.poll() is not None:
                    raise RuntimeError(
                        f"Shared engine startup failed; see {self.runtime / 'engine.log'}"
                    )
                try:
                    locks = acquire_engine_locks(self.home)
                except BlockingIOError:
                    pass  # Another client is starting it, or the old process is exiting.
                else:
                    try:
                        with (self.runtime / "engine.log").open("ab") as log:
                            child = subprocess.Popen(
                                [
                                    sys.executable,
                                    "-m",
                                    __name__,
                                    "serve",
                                    "--home",
                                    str(self.home),
                                    "--config",
                                    json.dumps(config),
                                    *[arg for fd in locks for arg in ("--lock-fd", str(fd))],
                                ],
                                stdin=subprocess.DEVNULL,
                                stdout=log,
                                stderr=log,
                                start_new_session=True,
                                pass_fds=tuple(locks),
                            )
                        # Closing our descriptor (without LOCK_UN) leaves the child's
                        # inherited lifetime lock held until the entire process exits.
                        threading.Thread(target=child.wait, daemon=True).start()
                    finally:
                        for descriptor in locks:
                            os.close(descriptor)
            time.sleep(0.1)
        raise RuntimeError(
            "Shared engine did not start within 30 seconds. Another session may own this "
            "installation under a different TMPDIR or an older runtime. Stop it from that "
            "session, or let it exit after five idle minutes, then retry. "
            f"Current runtime: {self.runtime}"
        )

    def call(self, operation, **payload):
        started = time.perf_counter()
        expected = self.ensure_running(self.configuration())
        # Never replay inference after a disconnect: it may have already executed.
        result = exchange(
            self.socket, {"operation": operation, "fingerprint": expected, "payload": payload}
        )
        result.setdefault("timing", {})["round_trip_ms"] = 1000 * (time.perf_counter() - started)
        return result


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(10)
        try:
            line = self.rfile.readline(MAX_REQUEST + 1)
            if len(line) > MAX_REQUEST or not line.endswith(b"\n"):
                raise ValueError("Invalid or oversized request")
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("Expected a JSON object")
            result = {"result": self.server.dispatch(request)}
            response = json.dumps(result, allow_nan=False).encode() + b"\n"
            if len(response) > MAX_RESPONSE:
                raise ValueError("Shared engine response exceeds 64 MiB; reduce the batch size")
        except Exception as exc:
            response = json.dumps({"error": f"{type(exc).__name__}: {exc}"}).encode() + b"\n"
        try:
            self.wfile.write(response)
        except OSError:
            pass  # Client left; the single worker still completed its accepted request.


class SharedServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = False
    # Concurrent clients perform discovery immediately before submitting work.
    # The socketserver default backlog of five can refuse that startup burst.
    request_queue_size = 32

    def __init__(self, path, config, *, factory=None, idle_seconds=IDLE_SECONDS):
        self.config, self.identity = config, fingerprint(config)
        self.worker = EngineWorker(config.get("model"), config["roots"], factory=factory)
        self.state_lock = threading.Lock()
        self.active, self.loaded = 0, False
        self.stopping = False
        self.last_used = time.monotonic()
        self.idle_seconds = idle_seconds
        self.connections = threading.BoundedSemaphore(16)
        super().__init__(str(path), Handler)
        os.chmod(path, 0o600)

    def process_request(self, request, client_address):
        if not self.connections.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.connections.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.connections.release()

    def dispatch(self, request):
        operation = request.get("operation")
        with self.state_lock:
            if operation == "status":
                return {
                    "status": "stopping" if self.stopping else "running",
                    "pid": os.getpid(),
                    "loaded": self.loaded,
                    "active_requests": self.active,
                    "version": self.config["version"],
                    "model": self.config.get("model"),
                    "fingerprint": self.identity,
                    "idle_timeout_seconds": self.idle_seconds,
                }
            if operation == "stop":
                if self.active:
                    raise RuntimeError(
                        "Shared engine is busy; stop it after the current requests finish"
                    )
                self.stopping = True
                return {"status": "stopping"}
            if self.stopping:
                raise RuntimeError("Shared engine is stopping; retry the request")
            if request.get("fingerprint") != self.identity:
                raise RuntimeError("Shared engine configuration changed; retry the request")
            if operation not in CONTRACTS:
                raise ValueError("Unknown engine operation")
            payload = CONTRACTS[operation](**request.get("payload", {})).model_dump()
            self.active += 1
        try:
            result = self.worker.call(operation, **payload)
            self.loaded = True
            return result
        finally:
            with self.state_lock:
                self.active -= 1
                self.last_used = time.monotonic()

    def run_until_idle(self):
        self.timeout = 0.2
        while True:
            with self.state_lock:
                if not self.active and (
                    self.stopping or time.monotonic() - self.last_used >= self.idle_seconds
                ):
                    self.stopping = True
                    return
            self.handle_request()


def serve(home, config, *, lock_fds=None, idle_seconds=IDLE_SECONDS, factory=None):
    runtime = runtime_directory(home)
    # Keep this descriptor alive through interpreter/model teardown, not merely the
    # server loop. Explicit launches also acquire it before constructing any worker.
    if lock_fds is None:
        try:
            lock_fds = acquire_engine_locks(home)
        except BlockingIOError:
            raise RuntimeError("Shared engine is already running") from None
    path = runtime / "engine.sock"
    path.unlink(missing_ok=True)
    server = SharedServer(path, config, factory=factory, idle_seconds=idle_seconds)

    def stop_when_finished(*_):
        server.stopping = True

    signal.signal(signal.SIGTERM, stop_when_finished)
    signal.signal(signal.SIGINT, stop_when_finished)
    try:
        server.run_until_idle()
    finally:
        server.server_close()
        server.worker.close()
        path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["status", "stop", "serve"])
    parser.add_argument("--home", type=Path, default=installation_home())
    parser.add_argument("--config", help=argparse.SUPPRESS)
    parser.add_argument("--lock-fd", type=int, action="append", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        client = SharedClient(home=args.home)
        if args.command == "serve":
            serve(
                args.home,
                json.loads(args.config) if args.config else client.configuration(),
                lock_fds=args.lock_fd,
            )
        else:
            print(
                json.dumps(client.status() if args.command == "status" else client.stop(), indent=2)
            )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
