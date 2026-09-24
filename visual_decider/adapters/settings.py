"""Local installation settings; no credentials are stored here."""

import json
import os
from pathlib import Path


def installation_home():
    return Path(
        os.getenv("VISUAL_DECIDER_HOME", str(Path.home() / ".local/share/visual-decider"))
    ).expanduser()


def load_settings(home=None):
    path = (Path(home) if home is not None else installation_home()) / "config.json"
    settings = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(settings, dict) or set(settings) - {"model", "roots"}:
        raise ValueError("Invalid visual-decider config.json")
    settings.setdefault("roots", [str(Path.home())])
    if (
        not isinstance(settings["roots"], list)
        or not settings["roots"]
        or any(
            not isinstance(root, str) or not Path(root).expanduser().is_absolute()
            for root in settings["roots"]
        )
    ):
        raise ValueError("Configured roots must be a nonempty list of absolute paths")
    if "model" in settings and not isinstance(settings["model"], str):
        raise ValueError("Configured model must be a string")
    return settings
