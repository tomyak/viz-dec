"""Exercise installer ordering without network, model weights, or agent configuration writes."""

import importlib.util
import json
import subprocess
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "installer", Path(__file__).resolve().parents[2] / "scripts/install.py"
)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def test_install_downloads_before_registering_and_excludes_unrelated_files(tmp_path, monkeypatch):
    source, home, weights = tmp_path / "source", tmp_path / "install home", tmp_path / "weights"
    source.mkdir()
    weights.mkdir()
    (source / "pyproject.toml").write_text('[project]\nversion = "0.2.0"\n')
    for folder in ["plugins", ".agents", ".claude-plugin", ".local"]:
        (source / folder).mkdir()
        (source / folder / "sentinel").write_text("fixture")
    plugin = source / "plugins/visual-decider"
    plugin.mkdir()
    (plugin / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"visual-decider": {"command": "/bin/sh"}}})
    )
    monkeypatch.setenv("VISUAL_DECIDER_HOME", str(home))
    monkeypatch.setattr(installer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(installer.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(installer, "physical_memory", lambda: 18 * installer.GIB)
    monkeypatch.setattr(installer.shutil, "which", lambda name: f"/bin/{name}")
    commands = []

    def run(command, **kwargs):
        commands.append([str(x) for x in command])
        if str(command[0]).endswith("visual-decider-model"):
            assert "--offline" not in command
            return SimpleNamespace(stdout=str(weights))
        if command[0] in ("codex", "claude"):
            assert (home / "config.json").exists()
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(installer, "run", run)
    args = Namespace(
        source=source,
        uv="uv",
        agents="both",
        allow_root=[str(tmp_path)],
        model=None,
        revision=None,
        offline=False,
    )
    installer.install(args)
    assert commands[0][:2] == ["uv", "sync"]
    assert "--frozen" in commands[0] and "--no-editable" in commands[0]
    assert commands[1][0].endswith("visual-decider-model")
    assert not (home / "marketplace/.local").exists()
    launcher = json.loads((home / "marketplace/plugins/visual-decider/.mcp.json").read_text())
    assert launcher["mcpServers"]["visual-decider"]["env"]["VISUAL_DECIDER_HOME"] == str(home)

    assert json.loads((home / "config.json").read_text())["model"] == str(weights)
    assert commands[1][2] == installer.MEDIUM_MODEL
    # Repeated installation retains settings and automatic selection, provisions
    # the same model, and never launches a model server as part of installation.
    old_settings = (home / "config.json").stat().st_mtime_ns
    installer.install(args)
    assert (home / "config.json").stat().st_mtime_ns == old_settings
    assert len([c for c in commands if c[0].endswith("visual-decider-model")]) == 2
    assert all("visual-decider-service" not in c[0] for c in commands)
    # Provisioning failure must never register plugins or overwrite previous settings.
    old = (home / "config.json").read_text()

    def failed(command, **kwargs):
        if str(command[0]).endswith("visual-decider-model"):
            raise subprocess.CalledProcessError(1, command)
        assert command[0] == "uv"

    monkeypatch.setattr(installer, "run", failed)
    with pytest.raises(subprocess.CalledProcessError):
        installer.install(args)
    assert (home / "config.json").read_text() == old


@pytest.mark.parametrize(
    "gib,expected",
    [
        (8, installer.SMALL_MODEL),
        (12, installer.SMALL_MODEL),
        (16, installer.MEDIUM_MODEL),
        (18, installer.MEDIUM_MODEL),
        (24, installer.MEDIUM_MODEL),
        (31, installer.MEDIUM_MODEL),
        (32, installer.BF16_MODEL),
        (128, installer.BF16_MODEL),
    ],
)
def test_memory_tiers(gib, expected, monkeypatch):
    monkeypatch.setattr(installer, "physical_memory", lambda: gib * installer.GIB)
    model, selection = installer.select_model(None, {}, {})
    assert model == expected and selection["mode"] == "auto"


def test_migration_and_explicit_preferences(monkeypatch):
    monkeypatch.setattr(installer, "physical_memory", lambda: 18 * installer.GIB)
    legacy = {"model": "/cache/models--google--gemma-4-E4B-it/snapshots/abc"}
    assert installer.select_model(None, legacy, {})[0] == installer.MEDIUM_MODEL
    assert installer.select_model(None, legacy, {"mode": "explicit"})[0] == legacy["model"]
    custom = {"model": "/corporate/approved-weights"}
    assert installer.select_model(None, custom, {})[0] == custom["model"]
    assert installer.select_model("auto", custom, {"mode": "explicit"})[0] == installer.MEDIUM_MODEL
    assert installer.select_model(None, legacy, {"mode": "auto"})[0] == installer.MEDIUM_MODEL
    # Explicit overrides must work even when memory detection is unavailable.
    monkeypatch.setattr(installer, "physical_memory", lambda: pytest.fail("No detection needed"))
    assert installer.select_model("custom/repo", {}, {}) == ("custom/repo", {"mode": "explicit"})


@pytest.mark.parametrize("value", ["", "garbage", "0", "-1"])
def test_memory_detection_fails_closed(value, monkeypatch):
    monkeypatch.setattr(installer.subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout=value))
    with pytest.raises(ValueError, match="--model"):
        installer.physical_memory()


def test_insufficient_memory(monkeypatch):
    monkeypatch.setattr(installer, "physical_memory", lambda: 4 * installer.GIB)
    with pytest.raises(ValueError, match="at least 8"):
        installer.select_model(None, {}, {})


def test_concurrent_install_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(installer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(installer.platform, "machine", lambda: "arm64")
    monkeypatch.setenv("VISUAL_DECIDER_HOME", str(tmp_path))
    with (tmp_path / "install.lock").open("a") as lock:
        installer.fcntl.flock(lock, installer.fcntl.LOCK_EX | installer.fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="Another installer"):
            installer.install(Namespace())
