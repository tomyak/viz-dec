#!/usr/bin/env bash
# Works from a checkout or through curl | bash. Credentials stay in Git/HF helpers.
set -euo pipefail
install_home="${VISUAL_DECIDER_HOME:-$HOME/.local/share/visual-decider}"
repo="${VISUAL_DECIDER_REPOSITORY:-https://github.com/tomyak/viz-dec.git}"
ref="${VISUAL_DECIDER_REF:-v0.2.1}"
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  echo 'The bundled MLX backend requires Apple Silicon macOS.' >&2
  exit 1
fi
command -v python3 >/dev/null || { echo 'Install Python 3 before running this installer.' >&2; exit 1; }
script_dir=''
if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
fi
if [[ -z "$script_dir" || ! -f "$script_dir/scripts/install.py" ]]; then
  command -v git >/dev/null || { echo 'Install Git before running this installer.' >&2; exit 1; }
  checkout="$(mktemp -d)"
  trap 'rm -rf -- "$checkout"' EXIT
  git clone --depth 1 --branch "$ref" -- "$repo" "$checkout/source"
  script_dir="$checkout/source"
fi
if command -v uv >/dev/null; then
  uv_bin="$(command -v uv)"
else
  python3 -m venv "$install_home/bootstrap"
  "$install_home/bootstrap/bin/python" -m pip install --disable-pip-version-check 'uv==0.10.10'
  uv_bin="$install_home/bootstrap/bin/uv"
fi
"$uv_bin" run --no-project --no-config --python 3.12 python "$script_dir/scripts/install.py" --source "$script_dir" --uv "$uv_bin" "$@"
