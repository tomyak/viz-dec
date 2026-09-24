"""Exercise real sockets, child processes, lifetime locks, and model ownership without MLX."""

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from visual_decider.adapters import shared

PAYLOAD = {"path": "/test.png", "question": "Visible?", "choices": ["Yes", "No"]}


def wait_for(predicate):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    pytest.fail("Condition did not become true")


@pytest.fixture
def client(tmp_path, monkeypatch):
    home = tmp_path / "installation with spaces"
    home.mkdir()
    (home / "config.json").write_text(json.dumps({"model": "fake", "roots": ["/"]}))
    script = tmp_path / "fake_service.py"
    script.write_text("""
import argparse, json, os, time
from pathlib import Path
from visual_decider.adapters.shared import serve
p = argparse.ArgumentParser()
p.add_argument("command")
p.add_argument("--home", type=Path)
p.add_argument("--config")
p.add_argument("--lock-fd", type=int, action="append")
a = p.parse_args()
class Engine:
    def __init__(self):
        with (a.home / "loads").open("a") as f:
            f.write(str(os.getpid()) + "\\n")
    def classify_image(self, path, question, **kwargs):
        if question == "Slow?":
            (a.home / "busy").touch()
            time.sleep(1)
        return {"winner": "Yes", "pid": os.getpid()}
    def model_health(self):
        return {"status": "ok", "pid": os.getpid()}
serve(a.home, json.loads(a.config), lock_fds=a.lock_fd, factory=Engine, idle_seconds=2)
""")
    original = subprocess.Popen

    def spawn(command, **kwargs):
        if command[1:3] == ["-m", "visual_decider.adapters.shared"]:
            command = [command[0], str(script), *command[3:]]
        return original(command, **kwargs)

    monkeypatch.setattr(shared.subprocess, "Popen", spawn)
    target = shared.SharedClient(home=home)
    yield target
    try:
        target.stop()
        wait_for(lambda: target.status()["status"] == "stopped")
    finally:
        # Tests use unique runtime directories; never touch another installation.
        if target.runtime.exists():
            for file in target.runtime.iterdir():
                file.unlink(missing_ok=True)
            target.runtime.rmdir()


def test_other_tmpdir_discovers_existing_model_without_writing_there(client, monkeypatch):
    first = client.call("classify_image", **PAYLOAD)
    original_runtime = client.runtime
    monkeypatch.setattr(shared, "user_temp_directory", lambda: original_runtime.parent)
    with tempfile.TemporaryDirectory(prefix="vdc-", dir="/tmp") as temporary:
        monkeypatch.setenv("TMPDIR", temporary)
        other = shared.SharedClient(home=client.home)
        assert not other.runtime.exists()  # Discovery creates no files/directories.
        assert other.status()["pid"] == first["pid"]
        assert other.runtime == original_runtime
        second = other.call("classify_image", **PAYLOAD)
        assert second["pid"] == first["pid"] and second["model_cached"]
        assert list(Path(temporary).iterdir()) == []
        assert len((client.home / "loads").read_text().splitlines()) == 1


def test_concurrent_start_in_different_discoverable_tmpdirs_loads_once(client, monkeypatch):
    with tempfile.TemporaryDirectory(prefix="vdc-", dir="/tmp") as temporary:
        roots = [Path(temporary) / name for name in ("terminal", "sandbox")]
        for root in roots:
            root.mkdir()
        candidates = [shared.runtime_directory(client.home, root=r, create=False) for r in roots]
        monkeypatch.setattr(shared, "runtime_candidates", lambda *args: candidates)
        clients = []
        for root in roots:
            monkeypatch.setenv("TMPDIR", str(root))
            clients.append(shared.SharedClient(home=client.home))
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda c: c.call("classify_image", **PAYLOAD), clients))
            assert results[0]["pid"] == results[1]["pid"]
            assert sum(not r["model_cached"] for r in results) == 1
            assert len((client.home / "loads").read_text().splitlines()) == 1
        finally:
            clients[0].stop()
            wait_for(lambda: clients[0].status()["status"] == "stopped")


def test_discovered_engine_exit_restarts_in_callers_writable_tmpdir(client, monkeypatch):
    first = client.call("classify_image", **PAYLOAD)
    monkeypatch.setattr(shared, "user_temp_directory", lambda: client.startup_runtime.parent)
    with tempfile.TemporaryDirectory(prefix="vdc-", dir="/tmp") as temporary:
        monkeypatch.setenv("TMPDIR", temporary)
        other = shared.SharedClient(home=client.home)
        assert other.status()["pid"] == first["pid"]
        other.stop()
        wait_for(lambda: client.status()["status"] == "stopped")
        try:
            second = other.call("classify_image", **PAYLOAD)
            assert second["pid"] != first["pid"]
            assert other.runtime.parent == Path(temporary)
        finally:
            other.stop()
            wait_for(lambda: other.status()["status"] == "stopped")


def test_socket_permission_denial_fails_before_inference_or_duplicate_start(client, monkeypatch):
    client.call("classify_image", **PAYLOAD)
    original = shared.exchange

    def blocked(*args, **kwargs):
        raise PermissionError(1, "Operation not permitted")

    with monkeypatch.context() as patch:
        patch.setattr(shared, "exchange", blocked)
        with pytest.raises(RuntimeError, match="No inference was submitted"):
            client.call("classify_image", **PAYLOAD)
        assert len((client.home / "loads").read_text().splitlines()) == 1
    assert shared.exchange is original


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS Seatbelt sandbox")
@pytest.mark.parametrize("allow_sockets", [True, False])
def test_sandbox_discovers_terminal_model_and_respects_socket_policy(client, allow_sockets):
    first = client.call("classify_image", **PAYLOAD)
    original_runtime = client.runtime
    with tempfile.TemporaryDirectory(prefix="vdc-", dir="/tmp") as temporary:
        writable = str(Path(temporary).resolve())
        profile = (
            "(version 1)(allow default)(deny file-write*)"
            f'(allow file-write* (subpath {json.dumps(writable)}) (literal "/dev/null"))'
        )
        if not allow_sockets:
            profile += "(deny network*)"
        script = (
            "import json,sys; from visual_decider.adapters.shared import SharedClient; "
            "c=SharedClient(home=sys.argv[1]); "
            "r=c.call('classify_image',path='/test.png',question='Visible?',choices=['Yes','No']); "
            "print(json.dumps({'result':r,'runtime':str(c.runtime)}))"
        )
        run = subprocess.run(
            [
                "/usr/bin/sandbox-exec",
                "-p",
                profile,
                sys.executable,
                "-c",
                script,
                str(client.home),
            ],
            env={**os.environ, "TMPDIR": writable, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
            timeout=10,
        )
        if allow_sockets:
            assert run.returncode == 0, run.stderr
            value = json.loads(run.stdout)
            assert value["result"]["pid"] == first["pid"]
            assert value["result"]["model_cached"]
            assert value["runtime"] == str(original_runtime)
        else:
            assert run.returncode == 1
            assert "No inference was submitted" in run.stderr
            assert "Operation not permitted" in run.stderr
        assert list(Path(temporary).iterdir()) == []
        assert len((client.home / "loads").read_text().splitlines()) == 1


def test_simultaneous_start_loads_one_model_and_reuses_it(client):
    config = client.configuration()
    client.ensure_running(config)
    assert not client.status()["loaded"]
    assert not (client.home / "loads").exists()
    client.stop()
    wait_for(lambda: client.status()["status"] == "stopped")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: client.call("classify_image", **PAYLOAD), range(8)))
    pids = {r["pid"] for r in results}
    assert len(pids) == 1
    assert sum(not r["model_cached"] for r in results) == 1
    for result in results:
        timing = result["timing"]
        assert timing["round_trip_ms"] >= timing["total_ms"]
        if result["model_cached"]:
            assert timing["model_load_ms"] == 0
    assert (client.home / "loads").read_text().splitlines() == [str(next(iter(pids)))]
    assert client.call("classify_image", **PAYLOAD)["pid"] in pids
    assert client.status()["loaded"]
    assert client.call("model_health")["pid"] in pids
    assert len((client.home / "loads").read_text().splitlines()) == 1


def test_crash_recovers_without_stale_lock_or_socket(client):
    first = client.call("classify_image", **PAYLOAD)
    os.kill(first["pid"], signal.SIGKILL)
    wait_for(lambda: client.status()["status"] == "stopped")
    second = client.call("classify_image", **PAYLOAD)
    assert first["pid"] != second["pid"]
    assert len((client.home / "loads").read_text().splitlines()) == 2


def test_changed_config_replaces_idle_service(client):
    first = client.call("classify_image", **PAYLOAD)
    (client.home / "config.json").write_text(json.dumps({"model": "other", "roots": ["/"]}))
    second = client.call("classify_image", **PAYLOAD)
    assert second["pid"] != first["pid"]
    assert client.status()["model"] == "other"
    # A replacement owns the same lifetime lock; the former process has exited.
    with pytest.raises(ProcessLookupError):
        os.kill(first["pid"], 0)


def test_busy_service_is_not_stopped_or_replaced(client):
    with ThreadPoolExecutor() as pool:
        pending = pool.submit(client.call, "classify_image", **{**PAYLOAD, "question": "Slow?"})
        wait_for(lambda: (client.home / "busy").exists())
        with pytest.raises(RuntimeError, match="busy"):
            client.stop()
        (client.home / "config.json").write_text(json.dumps({"model": "other", "roots": ["/"]}))
        with pytest.raises(RuntimeError, match="busy"):
            client.call("classify_image", **PAYLOAD)
        assert pending.result()["winner"] == "Yes"


def test_idle_exit_and_later_restart(client):
    first = client.call("classify_image", **PAYLOAD)
    wait_for(lambda: client.status()["status"] == "stopped")
    assert client.call("classify_image", **PAYLOAD)["pid"] != first["pid"]


def test_invalid_request_and_mismatched_configuration_do_not_load_model(client):
    identity = client.ensure_running(client.configuration())
    with pytest.raises(RuntimeError, match="configuration changed"):
        shared.exchange(
            client.socket,
            {"operation": "classify_image", "fingerprint": "stale", "payload": PAYLOAD},
        )
    with pytest.raises(RuntimeError, match="validation"):
        shared.exchange(
            client.socket, {"operation": "classify_image", "fingerprint": identity, "payload": {}}
        )
    assert not client.status()["loaded"]
