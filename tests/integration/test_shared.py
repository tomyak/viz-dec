"""Exercise real sockets, child processes, lifetime locks, and model ownership without MLX."""

import json
import os
import signal
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

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
        assert command[1:3] == ["-m", "visual_decider.adapters.shared"]
        return original([command[0], str(script), *command[3:]], **kwargs)

    monkeypatch.setattr(shared.subprocess, "Popen", spawn)
    target = shared.SharedClient(home=home)
    yield target
    try:
        target.stop()
        wait_for(lambda: target.status()["status"] == "stopped")
    finally:
        # Tests use unique runtime directories; never touch another installation.
        for file in target.runtime.iterdir():
            file.unlink(missing_ok=True)
        target.runtime.rmdir()


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
