"""Offline installation diagnostics and a model smoke test using the shared engine."""

import argparse
import json
from importlib.metadata import version
from pathlib import Path

from ..models.download import DEFAULT_MODEL, ensure_model
from .settings import installation_home, load_settings
from .shared import SharedClient


def check_health(*, home=None, inference=True):
    home = Path(home or installation_home()).expanduser().resolve()
    report = {
        "status": "error",
        "version": version("visual-decider"),
        "home": str(home),
        "inference_tested": False,
        "checks": [],
    }
    stage = "configuration"
    hints = {
        "configuration": f"Check {home / 'config.json'} or rerun the installer.",
        "model_files": "Rerun the installer to provision complete weights; this check is offline.",
        "service": "Check the shared engine log, then restart your agent after upgrading.",
        "inference": "Inspect the error and engine log; close memory-heavy apps if memory is exhausted.",
    }
    try:
        settings = load_settings(home)
        report["checks"].append({"stage": stage, "status": "ok", "settings": settings})
        stage = "model_files"
        snapshot = ensure_model(settings.get("model", DEFAULT_MODEL), download=False)
        report["checks"].append({"stage": stage, "status": "ok", "snapshot": str(snapshot)})
        stage = "service"
        client = SharedClient(home=home)
        report["log"] = str(client.runtime / "engine.log")
        if inference:
            client.ensure_running(client.configuration())
        details = client.status()
        report["log"] = str(client.runtime / "engine.log")
        report["checks"].append({"stage": stage, "status": "ok", "details": details})
        stage = "inference"
        if inference:
            result = client.call("model_health")
            report["inference_tested"] = True
            report["checks"].append({"stage": stage, **result})
            report["service"] = client.status()
            if result["status"] != "ok":
                report["hint"] = "The model failed the synthetic color test. Inspect its decisions."
                return report
        else:
            report["checks"].append({"stage": stage, "status": "skipped"})
        report["status"] = "ok" if inference else "preflight_ok"
    except Exception as exc:
        report["checks"].append(
            {"stage": stage, "status": "error", "error": f"{type(exc).__name__}: {exc}"}
        )
        report["hint"] = hints[stage]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path)
    parser.add_argument(
        "--no-inference",
        action="store_true",
        help="Check cached files/status without loading weights",
    )
    args = parser.parse_args()
    result = check_health(home=args.home, inference=not args.no_inference)
    print(json.dumps(result, indent=2, allow_nan=False))
    raise SystemExit(1 if result["status"] == "error" else 0)


if __name__ == "__main__":
    main()
