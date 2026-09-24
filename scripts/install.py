"""Install the locked engine and register real agent plugins; never copy user skills."""

import argparse
import fcntl
import json
import os
import platform
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
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


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
    write_json(state_path, {"version": version, "model": snapshot, "model_selection": selection})
    for agent in agents:
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
    print(
        f"Installed visual-decider {version} at {target}\nModel: {snapshot}\nAllowed roots: {roots}"
    )
    print("Restart existing agent sessions once after upgrading. No login service was installed.")
    print("Agent sessions share one model per installation; it stops after 5 idle minutes.")
    print(f"CLI: {target}/bin/visual-decide")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--uv", default="uv")
    parser.add_argument(
        "--agents", choices=["auto", "both", "codex", "claude", "none"], default="auto"
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
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Installation failed: {exc}\n")


if __name__ == "__main__":
    main()
