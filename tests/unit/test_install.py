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
    monkeypatch.setenv("VISUAL_DECIDER_HOME", str(home))
    monkeypatch.setattr(installer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(installer.platform, "machine", lambda: "arm64")
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
    assert json.loads((home / "config.json").read_text())["model"] == str(weights)
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
