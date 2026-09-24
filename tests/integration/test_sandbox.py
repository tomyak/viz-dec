"""The daemon must work with writes restricted to TMPDIR, including its lifetime lock."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS Seatbelt sandbox")
def test_daemon_inherits_writable_tmpdir_with_read_only_installation(tmp_path):
    home = tmp_path / "installation"
    home.mkdir()
    (home / "config.json").write_text(json.dumps({"model": "fake", "roots": ["/"]}))
    server = tmp_path / "server.py"
    server.write_text("""
import argparse, json, os
from visual_decider.adapters.shared import serve
p = argparse.ArgumentParser()
p.add_argument("command")
p.add_argument("--home")
p.add_argument("--config")
p.add_argument("--lock-fd", type=int, action="append")
a = p.parse_args()
class Engine:
    def classify_image(self, path, **kwargs):
        return {"winner": "Yes", "pid": os.getpid()}
serve(a.home, json.loads(a.config), lock_fds=a.lock_fd, factory=Engine, idle_seconds=2)
""")
    runner = tmp_path / "client.py"
    runner.write_text("""
import json, subprocess, sys, time
from visual_decider.adapters.shared import SharedClient
original = subprocess.Popen
def spawn(command, **kwargs):
    return original([command[0], sys.argv[2], *command[3:]], **kwargs)
subprocess.Popen = spawn
client = SharedClient(home=sys.argv[1])
try:
    payload = dict(path="/test.png", question="Visible?", choices=["Yes", "No"])
    cold = client.call("classify_image", **payload)
    warm = client.call("classify_image", **payload)
    assert cold["pid"] == warm["pid"]
    assert not cold["model_cached"] and warm["model_cached"]
    assert warm["timing"]["model_load_ms"] == 0
    print(json.dumps({"runtime": str(client.runtime), "winner": warm["winner"]}))
finally:
    client.stop()
    deadline = time.monotonic() + 10
    while client.status()["status"] != "stopped" and time.monotonic() < deadline:
        time.sleep(0.02)
    assert client.status()["status"] == "stopped"
""")
    with tempfile.TemporaryDirectory(prefix="vds-", dir="/tmp") as directory:
        writable = str(Path(directory).resolve())
        profile = (
            "(version 1)(allow default)(deny file-write*)"
            f'(allow file-write* (subpath {json.dumps(writable)}) (literal "/dev/null"))'
        )
        run = subprocess.run(
            [
                "/usr/bin/sandbox-exec",
                "-p",
                profile,
                sys.executable,
                str(runner),
                str(home),
                str(server),
            ],
            env={**os.environ, "TMPDIR": writable, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
            timeout=45,
        )
        assert run.returncode == 0, run.stderr
        result = json.loads(run.stdout)
        assert Path(result["runtime"]).parent == Path(writable)
        assert result["winner"] == "Yes"
        assert not (Path(result["runtime"]) / "engine.lock").exists()
        assert sorted(p.name for p in home.iterdir()) == ["config.json"]
