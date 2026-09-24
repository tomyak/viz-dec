"""Install one locked runtime with native plugins, standalone skills, or direct MCP."""

import argparse
import fcntl
import json
import os
import platform
import shlex
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

GIB = 1024**3
BF16_MODEL = "google/gemma-4-E4B-it"
SMALL_MODEL = "mlx-community/gemma-4-e2b-it-4bit"
MEDIUM_MODEL = "mlx-community/gemma-4-e4b-it-4bit"


def physical_memory():
    try:
        result = subprocess.run(
            ["/usr/sbin/sysctl", "-n", "hw.memsize"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        memory = int(result.stdout.strip())
        if memory <= 0:
            raise ValueError("Nonpositive memory size")
        return memory
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise ValueError("Cannot detect physical memory; specify --model explicitly") from exc


def select_model(request, previous, selection):
    """Preserve explicit choices; automatic choices adapt to physical, not free, RAM."""
    if request and request != "auto":
        return request, {"mode": "explicit"}
    if request is None and previous.get("model"):
        if selection.get("mode") == "explicit":
            return previous["model"], selection
        if not selection:
            # Older installers did not record intent. Only migrate the old default;
            # preserve custom models/snapshots whose provenance cannot be established.
            old = previous["model"]
            parts = Path(old).parts
            legacy_default = old == BF16_MODEL or (
                "models--google--gemma-4-E4B-it" in parts and "snapshots" in parts
            )
            if not legacy_default:
                return old, {"mode": "explicit"}
    memory = physical_memory()
    if memory < 8 * GIB:
        raise ValueError("Automatic selection requires at least 8 GiB RAM; use --model to override")
    model = (
        BF16_MODEL if memory >= 32 * GIB else MEDIUM_MODEL if memory >= 16 * GIB else SMALL_MODEL
    )
    return model, {"mode": "auto", "memory_bytes": memory, "model_id": model}


def run(args, **kwargs):
    print("+ " + " ".join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=kwargs.pop("check", True), **kwargs)


def write_launcher(path, content):
    marker = "# Managed by visual-decider installer\n"
    if path.is_symlink() or (path.exists() and marker not in path.read_text()):
        raise ValueError(f"Refusing to replace an unmanaged launcher: {path}")
    content = "#!/bin/sh\n" + marker + content
    if path.exists() and path.read_text() == content:
        return
    temporary = path.with_suffix(".tmp")
    temporary.write_text(content)
    temporary.chmod(0o755)
    temporary.replace(path)


def install_launchers(home, target):
    (home / "bin").mkdir(exist_ok=True)
    for name in (
        "visual-decide",
        "visual-decider-model",
        "visual-decider-mcp",
        "visual-decider-http",
        "visual-decider-service",
        "visual-decider-health",
    ):
        write_launcher(
            home / "bin" / name,
            f"export VISUAL_DECIDER_HOME={shlex.quote(str(home))}\n"
            f'exec {shlex.quote(str(target / "bin" / name))} "$@"\n',
        )


def skill_path(agent, args):
    override = getattr(args, f"{agent}_skills_dir", None)
    directory = override or (
        Path.home() / ".agents/skills"
        if agent == "codex"
        else Path(os.getenv("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))) / "skills"
    )
    return Path(directory).expanduser().absolute() / "visual-decider"


def owned_skill(path, home):
    return path.is_symlink() and path.resolve().is_relative_to(home / "skills")


def install_skill(source, home, version):
    target = home / "skills" / version / "visual-decider"
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="skill-", dir=home) as temp:
        stage = Path(temp) / "visual-decider"
        shutil.copytree(source / "plugins/visual-decider/skills/visual-decider", stage)
        write_json(stage / "runtime.json", {"home": str(home)})
        if target.exists():
            shutil.rmtree(target)
        stage.rename(target)
    return target


def link_skill(path, target, home):
    if (path.exists() or path.is_symlink()) and not owned_skill(path, home):
        raise ValueError(f"Refusing to replace an unmanaged skill: {path}")
    if path.is_symlink() and path.resolve() == target:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".visual-decider-install")
    # Do not remove arbitrary pre-existing files at the staging name.
    temporary.symlink_to(target, target_is_directory=True)
    temporary.replace(path)


def existing_mcp(agent, home):
    command = [agent, "mcp", "get", "visual-decider"]
    if agent == "codex":
        command.append("--json")
    result = run(command, check=False, capture_output=True, text=True, timeout=30)
    if result.returncode:
        if "No MCP server named" in result.stderr + result.stdout:
            return False
        raise ValueError(
            f"Cannot inspect {agent} MCP registration: {result.stderr or result.stdout}"
        )
    if agent == "codex":
        transport = json.loads(result.stdout)["transport"]
        path = transport.get("command", "").strip()
    else:
        lines = [line.strip() for line in result.stdout.splitlines()]
        if not any(line.startswith("Scope: User config") for line in lines):
            raise ValueError("A project-scoped Claude MCP named visual-decider already exists")
        path = next(
            (
                line.removeprefix("Command:").strip()
                for line in lines
                if line.startswith("Command:")
            ),
            "",
        )
    candidate = Path(path)
    # Do not resolve the executable's symlinks: ownership is its registered installation path.
    if (
        not candidate.is_absolute()
        or ".." in candidate.parts
        or candidate.name != "visual-decider-mcp"
        or not (
            candidate.parent == home / "bin"
            or (candidate.is_relative_to(home / "versions") and candidate.parent.name == "bin")
        )
    ):
        raise ValueError(f"Refusing to replace an unmanaged {agent} MCP: {path!r}")
    return True


def remove_mcp(agent):
    run(
        [agent, "mcp", "remove", "visual-decider"]
        + (["--scope", "user"] if agent == "claude" else [])
    )


def register_mcp(agent, home):
    command = str(home / "bin/visual-decider-mcp")
    if agent == "claude":
        run(
            [
                agent,
                "mcp",
                "add-json",
                "--scope",
                "user",
                "visual-decider",
                json.dumps({"type": "stdio", "command": command}),
            ]
        )
    else:
        run([agent, "mcp", "add", "visual-decider", "--", command])


def remove_plugin_integration(agent):
    """Switch only this package's user integration; no marketplace access needed."""
    result = run([agent, "plugin", "list", "--json"], capture_output=True, text=True, timeout=30)
    plugins = json.loads(result.stdout)
    if agent == "codex":
        active = any(
            p.get("pluginId") == "visual-decider@visual-decider" for p in plugins["installed"]
        )
    else:
        matching = [
            p
            for p in plugins
            if p.get("id") == "visual-decider@visual-decider" and p.get("enabled")
        ]
        if any(p.get("scope") != "user" for p in matching):
            raise ValueError(
                "Disable the project/local visual-decider plugin before switching modes"
            )
        active = bool(matching)
    if active:
        run(
            [
                agent,
                "plugin",
                "remove" if agent == "codex" else "disable",
                "visual-decider@visual-decider",
                "--json",
            ]
            + (["--scope", "user"] if agent == "claude" else [])
        )


def enable_claude_plugin():
    result = run(
        [
            "claude",
            "plugin",
            "enable",
            "visual-decider@visual-decider",
            "--scope",
            "user",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        try:
            already_enabled = (
                json.loads(result.stdout).get("failureCode") == "already_in_goal_state"
            )
        except ValueError:
            already_enabled = False
        if not already_enabled:
            raise ValueError(f"Could not enable Claude plugin: {result.stderr or result.stdout}")


def selected_agents(request):
    agents = [name for name in ("codex", "claude") if shutil.which(name)]
    if request == "auto":
        if not agents:
            raise ValueError(
                "Install Codex or Claude Code first, or use --agents none for CLI/Python only"
            )
        return agents
    wanted = [] if request == "none" else ["codex", "claude"] if request == "both" else [request]
    for name in wanted:
        if name not in agents:
            raise ValueError(
                f"{name} CLI is not on PATH; install it or select another --agents option"
            )
    return wanted


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, indent=2) + "\n"
    if path.exists() and path.read_text() == content:
        return
    temporary = path.with_suffix(".tmp")
    temporary.write_text(content)
    temporary.replace(path)


def install(args):
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise ValueError("The bundled MLX backend requires Apple Silicon macOS")
    home = (
        Path(os.environ.get("VISUAL_DECIDER_HOME", "~/.local/share/visual-decider"))
        .expanduser()
        .resolve()
    )
    home.mkdir(parents=True, exist_ok=True)
    with (home / "install.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(
                "Another installer is running for this installation; retry when it finishes"
            ) from None
        install_locked(args, home)


def install_locked(args, home):
    source = args.source.resolve()
    version = tomllib.loads((source / "pyproject.toml").read_text())["project"]["version"]
    agents = selected_agents(args.agents)
    settings_path = home / "config.json"
    previous = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    state_path = home / "installation.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    integrations = state.get("integrations", {})
    skill_directories = state.get("skill_directories", {})
    for agent in agents:
        if not getattr(args, f"{agent}_skills_dir", None) and agent in skill_directories:
            setattr(args, f"{agent}_skills_dir", Path(skill_directories[agent]))
    modes = {
        agent: getattr(args, "integration", None) or integrations.get(agent, "plugin")
        for agent in agents
    }
    for agent, mode in modes.items():
        path = skill_path(agent, args)
        if "skill" in mode and (path.exists() or path.is_symlink()) and not owned_skill(path, home):
            raise ValueError(f"Refusing to replace an unmanaged skill: {path}")
    selection = (
        state.get("model_selection", {}) if state.get("model") == previous.get("model") else {}
    )
    model, selection = select_model(args.model, previous, selection)
    if args.revision and (not args.model or args.model == "auto"):
        raise ValueError("--revision requires an explicit --model Hugging Face ID")
    reason = (
        f"{selection['memory_bytes'] / GIB:g} GiB physical RAM"
        if selection["mode"] == "auto"
        else "explicit selection"
    )
    print(f"Model: {model} ({reason})", flush=True)
    roots = args.allow_root or previous.get("roots", [str(Path.home())])
    if not roots or any(not Path(root).expanduser().is_absolute() for root in roots):
        raise ValueError("--allow-root values must be absolute paths")
    roots = [str(Path(root).expanduser().resolve()) for root in roots]
    target = home / "versions" / version
    env = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(target)}
    env.pop("VIRTUAL_ENV", None)
    sync = [
        args.uv,
        "sync",
        "--project",
        source,
        "--frozen",
        "--all-extras",
        "--no-dev",
        "--no-editable",
        "--python",
        "3.12",
    ]
    if args.offline:
        sync.append("--offline")
    run(sync, env=env)
    provision = [target / "bin/visual-decider-model", "--model", model]
    if args.revision:
        provision += ["--revision", args.revision]
    if args.offline:
        provision.append("--offline")
    result = run(provision, stdout=subprocess.PIPE, text=True)
    snapshot = result.stdout.strip()
    if not Path(snapshot).is_dir():
        raise ValueError("Model provisioner did not return a valid snapshot directory")
    # The download checkout may be temporary. Copy only the plugin allowlist.
    home.mkdir(parents=True, exist_ok=True)
    market = home / "marketplace"
    with tempfile.TemporaryDirectory(prefix="market-", dir=home) as staging:
        stage = Path(staging)
        for folder in ("plugins", ".agents", ".claude-plugin"):
            shutil.copytree(source / folder, stage / folder)
        # MCP hosts may strip arbitrary inherited environment variables. Bind the
        # installed launcher explicitly while keeping the published manifest portable.
        launcher_path = stage / "plugins/visual-decider/.mcp.json"
        launcher = json.loads(launcher_path.read_text())
        launcher["mcpServers"]["visual-decider"].setdefault("env", {})["VISUAL_DECIDER_HOME"] = str(
            home
        )
        write_json(launcher_path, launcher)
        market.mkdir(exist_ok=True)
        for folder in ("plugins", ".agents", ".claude-plugin"):
            if (market / folder).exists():
                shutil.rmtree(market / folder)
            shutil.move(stage / folder, market / folder)
    write_json(settings_path, {"model": snapshot, "roots": roots})
    install_launchers(home, target)
    state = {
        "version": version,
        "model": snapshot,
        "model_selection": selection,
        "integrations": integrations,
        "skill_directories": skill_directories,
    }
    write_json(state_path, state)
    skill = (
        install_skill(source, home, version) if any("skill" in m for m in modes.values()) else None
    )
    for agent, mode in modes.items():
        path = skill_path(agent, args)
        if mode != "plugin":
            # Codex mcp get also exposes servers supplied by enabled plugins.
            # Retire our plugin first so we inspect only the direct registration.
            remove_plugin_integration(agent)
            registered = existing_mcp(agent, home)
            if "skill" in mode:
                link_skill(path, skill, home)
                skill_directories[agent] = str(path.parent)
            if registered:
                remove_mcp(agent)
            if mode in ("skill-mcp", "mcp"):
                register_mcp(agent, home)
            if mode == "mcp" and owned_skill(path, home):
                path.unlink()
            integrations[agent] = mode
            write_json(state_path, state)
            continue
        if integrations.get(agent) in ("mcp", "skill-mcp") and existing_mcp(agent, home):
            remove_mcp(agent)
        run([agent, "plugin", "marketplace", "add", market])
        if agent == "codex":
            run([agent, "plugin", "add", "visual-decider@visual-decider", "--json"])
        else:
            run(
                [
                    agent,
                    "plugin",
                    "install",
                    "visual-decider@visual-decider",
                    "--scope",
                    "user",
                    "--json",
                ]
            )
            run(
                [
                    agent,
                    "plugin",
                    "update",
                    "visual-decider@visual-decider",
                    "--scope",
                    "user",
                    "--json",
                ]
            )
            enable_claude_plugin()
        if owned_skill(path, home):
            path.unlink()
        integrations[agent] = mode
        write_json(state_path, state)
    print(
        f"Installed visual-decider {version} at {target}\nModel: {snapshot}\nAllowed roots: {roots}"
    )
    print("Restart existing agent sessions once after upgrading. No login service was installed.")
    print("Agent sessions share one model per installation; it stops after 5 idle minutes.")
    print(f"CLI: {home}/bin/visual-decide")
    print(f"Model health check: {home}/bin/visual-decider-health")
    if getattr(args, "check_model", False):
        run([home / "bin/visual-decider-health"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--uv", default="uv")
    parser.add_argument(
        "--agents", choices=["auto", "both", "codex", "claude", "none"], default="auto"
    )
    parser.add_argument(
        "--integration",
        choices=["plugin", "skill", "skill-mcp", "mcp"],
        help="Agent integration; defaults to the previous choice per agent, otherwise plugin",
    )
    parser.add_argument("--codex-skills-dir", type=Path, help="Override ~/.agents/skills")
    parser.add_argument("--claude-skills-dir", type=Path, help="Override ~/.claude/skills")
    parser.add_argument(
        "--check-model",
        action="store_true",
        help="Run model inference health check after installation",
    )
    parser.add_argument(
        "--model", help="Hugging Face ID, local snapshot, or auto to reselect for this Mac"
    )
    parser.add_argument("--revision", help="Model revision; known models default to pinned commits")
    parser.add_argument(
        "--allow-root", action="append", help="Readable media root (repeatable); default home"
    )
    parser.add_argument(
        "--offline", action="store_true", help="Require cached dependencies and complete model"
    )
    try:
        install(parser.parse_args())
    except subprocess.CalledProcessError as exc:
        parser.exit(
            1, f"Installation failed at {exc.cmd[0]} (exit {exc.returncode}).\n{exc.stderr or ''}\n"
        )
    except subprocess.TimeoutExpired as exc:
        parser.exit(1, f"Installation failed: {exc.cmd[0]} timed out after {exc.timeout}s.\n")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Installation failed: {exc}\n")


if __name__ == "__main__":
    main()
