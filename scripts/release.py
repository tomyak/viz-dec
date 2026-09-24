"""Keep the Python package, installers, and both native plugin manifests on one version."""

import argparse
import json
import re
import subprocess
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/visual-decider"
MANIFESTS = [PLUGIN / ".codex-plugin/plugin.json", PLUGIN / ".claude-plugin/plugin.json"]


def version():
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def check(tag=None):
    current = version()
    assert re.fullmatch(r"\d+\.\d+\.\d+", current), "Use a stable semantic version"
    if tag:
        assert tag == f"v{current}", "Tag must match package version"
    for path in MANIFESTS:
        manifest = json.loads(path.read_text())
        assert manifest["name"] == "visual-decider" and manifest["version"] == current, path
        assert manifest["license"] == "MIT", path
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    assert market["plugins"][0]["version"] == current
    assert f"/versions/{current}/bin/visual-decider-mcp" in (PLUGIN / ".mcp.json").read_text()
    assert f":-v{current}" in (ROOT / "install.sh").read_text()
    assert f"## {current} " in (ROOT / "CHANGELOG.md").read_text(), "Add release notes"
    assert (ROOT / "LICENSE").read_text().startswith("MIT License")
    print(f"All release versions match {current}")


def set_version(new):
    if not re.fullmatch(r"\d+\.\d+\.\d+", new):
        raise ValueError("Expected MAJOR.MINOR.PATCH")
    old = version()
    files = [
        ROOT / "pyproject.toml",
        ROOT / "install.sh",
        ROOT / "README.md",
        ROOT / "docs/CORPORATE.md",
        ROOT / ".claude-plugin/marketplace.json",
        PLUGIN / ".mcp.json",
        *MANIFESTS,
    ]
    for path in files:
        path.write_text(path.read_text().replace(old, new))
    subprocess.run(["uv", "lock", "--project", str(ROOT)], check=True)
    print(f"Updated {old} → {new}; add CHANGELOG.md notes and run --check")


def archive():
    check()
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    for kind, root in (("plugin", PLUGIN), ("skill", PLUGIN / "skills/visual-decider")):
        path = output / f"visual-decider-{kind}-v{version()}.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for file in sorted(root.rglob("*")):
                if (
                    file.is_file()
                    and "__pycache__" not in file.parts
                    and file.name != "runtime.json"
                    and file.suffix != ".pyc"
                ):
                    z.write(file, Path("visual-decider") / file.relative_to(root))
            z.write(ROOT / "LICENSE", "visual-decider/LICENSE")
        print(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--set-version")
    group.add_argument("--archive", action="store_true")
    parser.add_argument("--tag")
    args = parser.parse_args()
    if args.set_version:
        set_version(args.set_version)
    elif args.archive:
        archive()
    else:
        check(args.tag)


if __name__ == "__main__":
    main()
