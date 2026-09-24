"""Exercise installer ordering without network, model weights, or agent configuration writes."""

import importlib.util
import json
import shutil
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
        return SimpleNamespace(stdout="", returncode=0)

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


@pytest.fixture
def skill_install(tmp_path, monkeypatch):
    home = tmp_path / "install home's space"
    weights = tmp_path / "weights"
    weights.mkdir()
    source = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("VISUAL_DECIDER_HOME", str(home))
    monkeypatch.setattr(installer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(installer.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(installer, "physical_memory", lambda: 18 * installer.GIB)
    monkeypatch.setattr(installer.shutil, "which", lambda name: f"/bin/{name}")
    commands, registrations, plugins = [], {}, set()

    def run(command, **kwargs):
        command = [str(c) for c in command]
        commands.append(command)
        stdout, returncode = "", 0
        if command[0].endswith("visual-decider-model"):
            stdout = str(weights)
        if command[1:3] == ["mcp", "get"]:
            path = registrations.get(command[0])
            if path is None and command[0] == "codex" and "codex" in plugins:
                path = "/bin/sh"  # Codex also reports plugin-provided MCP servers here.
            if path is None:
                stdout, returncode = "No MCP server named visual-decider", 1
            elif command[0] == "codex":
                stdout = json.dumps({"transport": {"command": path}})
            else:
                stdout = f"Scope: User config (available in all your projects)\nCommand: {path}"
        if command[1:3] == ["plugin", "list"]:
            entry = {
                "pluginId": "visual-decider@visual-decider",
                "id": "visual-decider@visual-decider",
                "enabled": True,
                "scope": "user",
            }
            values = [entry] if command[0] in plugins else []
            stdout = json.dumps({"installed": values} if command[0] == "codex" else values)
        if command[1:3] in (["plugin", "add"], ["plugin", "install"]):
            plugins.add(command[0])
        if command[1:3] in (["plugin", "remove"], ["plugin", "disable"]):
            plugins.remove(command[0])
        if command[1:3] == ["mcp", "add-json"]:
            registrations[command[0]] = json.loads(command[-1])["command"]
        if command[1:3] == ["mcp", "add"]:
            registrations[command[0]] = command[-1]
        if command[1:3] == ["mcp", "remove"]:
            registrations.pop(command[0])
        return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)

    monkeypatch.setattr(installer, "run", run)
    args = Namespace(
        source=source,
        uv="uv",
        agents="both",
        allow_root=None,
        model=None,
        revision=None,
        offline=True,
        integration="skill",
        codex_skills_dir=tmp_path / "codex-skills",
        claude_skills_dir=tmp_path / "claude-skills",
    )
    return args, home, commands, registrations


def test_skill_modes_repeat_migrate_and_remember(skill_install):
    args, home, commands, registrations = skill_install
    # Adopt/fix the exact leading-space legacy command that caused ENOENT.
    registrations["claude"] = " " + str(home / "versions/0.3.0/bin/visual-decider-mcp")
    installer.install(args)
    assert not registrations
    for agent in ("claude", "codex"):
        skill = installer.skill_path(agent, args)
        assert skill.is_symlink() and (skill / "SKILL.md").is_file()
        assert json.loads((skill / "runtime.json").read_text())["home"] == str(home)
        assert (skill / "scripts/run.py").exists()
    assert not any(c[1:3] == ["plugin", "marketplace"] for c in commands)
    args.integration = "skill-mcp"
    installer.install(args)
    assert registrations == {a: str(home / "bin/visual-decider-mcp") for a in ("claude", "codex")}
    args.integration = None
    directories = (args.codex_skills_dir, args.claude_skills_dir)
    args.codex_skills_dir = args.claude_skills_dir = None
    installer.install(args)
    assert (args.codex_skills_dir, args.claude_skills_dir) == directories
    state = json.loads((home / "installation.json").read_text())
    assert state["integrations"] == {"claude": "skill-mcp", "codex": "skill-mcp"}
    assert len(registrations) == 2
    args.integration = "mcp"
    installer.install(args)
    assert all(not installer.skill_path(a, args).exists() for a in ("claude", "codex"))
    args.integration = "plugin"
    installer.install(args)
    assert not registrations
    args.integration = "skill"
    installer.install(args)
    assert not registrations
    assert all(installer.skill_path(a, args).exists() for a in ("claude", "codex"))
    assert all(
        not c[0].endswith(("visual-decider-service", "visual-decider-health")) for c in commands
    )


def test_foreign_skill_and_mcp_are_not_overwritten(skill_install):
    args, home, commands, registrations = skill_install
    skill = installer.skill_path("codex", args)
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("user work")
    with pytest.raises(ValueError, match="unmanaged skill"):
        installer.install(args)
    assert (skill / "SKILL.md").read_text() == "user work" and not commands
    shutil.rmtree(skill)
    registrations["codex"] = "/another/install/visual-decider-mcp"
    with pytest.raises(ValueError, match="unmanaged codex MCP"):
        installer.install(args)
    assert registrations["codex"] == "/another/install/visual-decider-mcp"


def test_stable_launcher_binds_home_and_preserves_arguments(tmp_path):
    home = tmp_path / "home's space"
    target = home / "versions/1.0.0"
    (target / "bin").mkdir(parents=True)
    script = target / "bin/visual-decide"
    script.write_text('#!/bin/sh\nprintf "%s\\n" "$VISUAL_DECIDER_HOME" "$@"\n')
    script.chmod(0o755)
    installer.install_launchers(home, target)
    result = subprocess.run(
        [str(home / "bin/visual-decide"), "a b", "$(echo no)", "it's ok"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.splitlines() == [str(home), "a b", "$(echo no)", "it's ok"]
    timestamp = (home / "bin/visual-decide").stat().st_mtime_ns
    installer.install_launchers(home, target)
    assert (home / "bin/visual-decide").stat().st_mtime_ns == timestamp


def test_claude_already_enabled_is_success_but_other_failures_are_not(monkeypatch):
    monkeypatch.setattr(
        installer,
        "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=1,
            stderr="",
            stdout='{"failureCode":"already_in_goal_state"}',
        ),
    )
    installer.enable_claude_plugin()
    monkeypatch.setattr(
        installer,
        "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=1,
            stderr="organization policy",
            stdout='{"failureCode":"blocked"}',
        ),
    )
    with pytest.raises(ValueError, match="organization policy"):
        installer.enable_claude_plugin()
