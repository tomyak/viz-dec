"""Install the locked engine and register real agent plugins; never copy user skills."""

import argparse
import json
import os
import platform
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path


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
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def install(args):
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise ValueError("The bundled MLX backend requires Apple Silicon macOS")
    source = args.source.resolve()
    version = tomllib.loads((source / "pyproject.toml").read_text())["project"]["version"]
    agents = selected_agents(args.agents)
    home = (
        Path(os.environ.get("VISUAL_DECIDER_HOME", "~/.local/share/visual-decider"))
        .expanduser()
        .resolve()
    )
    settings_path = home / "config.json"
    previous = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    model = args.model or previous.get("model", "google/gemma-4-E4B-it")
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
        market.mkdir(exist_ok=True)
        for folder in ("plugins", ".agents", ".claude-plugin"):
            if (market / folder).exists():
                shutil.rmtree(market / folder)
            shutil.move(stage / folder, market / folder)
    write_json(settings_path, {"model": snapshot, "roots": roots})
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
    print("Start a fresh agent session to discover the plugin. No login service was installed.")
    print(f"CLI: {target}/bin/visual-decide")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--uv", default="uv")
    parser.add_argument(
        "--agents", choices=["auto", "both", "codex", "claude", "none"], default="auto"
    )
    parser.add_argument("--model", help="Hugging Face ID or pre-provisioned snapshot path")
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
