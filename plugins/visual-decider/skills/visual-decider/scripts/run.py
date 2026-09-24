#!/usr/bin/env python3
"""Forward arguments to the installed runtime, without importing or loading a model."""

import json
import os
import sys
from pathlib import Path


def main():
    binding = Path(__file__).resolve().parents[1] / "runtime.json"
    home = (
        json.loads(binding.read_text())["home"]
        if binding.exists()
        else os.getenv("VISUAL_DECIDER_HOME", "~/.local/share/visual-decider")
    )
    home = Path(home).expanduser().resolve()
    args = sys.argv[1:]
    name = "visual-decide"
    if args and args[0] in ("health", "service"):
        name = f"visual-decider-{args.pop(0)}"
    command = home / "bin" / name
    if not command.is_file():
        raise SystemExit(
            f"Runtime not installed at {home}. Run the visual-decider one-command installer."
        )
    os.execv(str(command), [str(command), *args])


if __name__ == "__main__":
    main()
