# Visual Decider

Ask **Claude Code** or **Codex** questions about images and videos using a local AI model on your Mac.

[![Set up Claude Code](https://img.shields.io/badge/Set_up-Claude_Code-D97757?style=for-the-badge)](#claude-code)
[![Set up Codex](https://img.shields.io/badge/Set_up-Codex-167D66?style=for-the-badge)](#codex)

**You need:** an Apple Silicon Mac (M1 or newer), 8 GB+ memory, Git, Python 3, and your agent’s CLI installed.

The install command picks a model for your Mac, downloads missing weights, installs the skill, and runs a health check. Existing model choices and complete cached weights are reused.

## Claude Code

**1. Copy this into Terminal:**

```bash
curl -fsSL https://raw.githubusercontent.com/tomyak/viz-dec/v0.4.1/install.sh | bash -s -- --agents claude --integration skill --check-model
```

**2. Restart Claude Code.** Drag in a photo (or paste its full file path), then ask:

```text
Use visual-decider on this image. Is there one person or two people?
```

Claude uses the local model and reports its answer.

## Codex

**1. Copy this into Terminal** with the Codex CLI installed:

```bash
curl -fsSL https://raw.githubusercontent.com/tomyak/viz-dec/v0.4.1/install.sh | bash -s -- --agents codex --integration skill --check-model
```

**2. Restart Codex.** Drag in a photo (or paste its full file path), then ask:

```text
Use visual-decider on this image. Is there one person or two people?
```

Codex uses the local model and reports its answer.

## Try more

Attach a video and ask:

```text
Use visual-decider on this video. Is a person visible in the room?
```

Attach several images and ask:

```text
Use visual-decider to batch these images. For each image, is a person visible?
```

Photos and videos in your home folder work by default. The model is shared across agent sessions and stops after five idle minutes. Video answers come from sampled frames; brief events between frames can be missed.

## Check that it works

```bash
"$HOME/.local/share/visual-decider/bin/visual-decider-health"
```

Look for `"status": "ok"` at the top. To update or repair an installation, rerun your agent’s install command above.

## More documentation

- [Installation options and troubleshooting](docs/INSTALLATION.md) — MCP, plugins, models, and access to other folders.
- [Usage guide](docs/USAGE.md) — batches, multiple questions, CLI, and Python.
- [Private corporate distribution](docs/CORPORATE.md).
- [Development](docs/DEVELOPMENT.md) and [architecture](ARCHITECTURE.md).

[MIT license](LICENSE) · [Releases](https://github.com/tomyak/viz-dec/releases) · [Validation](docs/VALIDATION.md)
