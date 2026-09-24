# Installation options and troubleshooting

[← Quick start: Claude Code or Codex](../README.md)

The README has the recommended one-command setup for each agent. Use this guide
for model selection, MCP or plugin installation, custom folders, and diagnostics.

## Requirements and installer behavior

Prerequisites: Apple Silicon macOS, at least 8 GiB of unified memory, Git, Python 3, and the CLI for the agent you use. The installer detects physical memory and selects a model, then provisions Python 3.12 with uv if needed.

```bash
curl -fsSL https://raw.githubusercontent.com/tomyak/viz-dec/v0.5.0/install.sh | bash
```

This one command:

- Installs locked dependencies and the engine in `~/.local/share/visual-decider/versions/0.5.0`.
- Chooses a model for the Mac's memory, printing the selection before downloading anything.
- Reuses complete cached Gemma weights or downloads missing weights from Hugging Face. Known models use pinned commit revisions.
- Registers the plugin with every detected supported agent, including MCP configuration and its skill. **No manual SKILL.md copying.**
- Uses your home directory as the default media access root. Shares one on-demand model between agent sessions over an owner-only Unix socket; opens no TCP port and installs no login service.

## Skills, MCP, and plugins

To install the skill for Claude Code **without a marketplace or MCP connection**:

```bash
curl -fsSL https://raw.githubusercontent.com/tomyak/viz-dec/v0.5.0/install.sh | bash -s -- --agents claude --integration skill
```

Use `--agents codex` or `--agents both` for the other agent choices. All modes install the same runtime and download the selected model when absent:

| `--integration` | Agent setup |
|---|---|
| `plugin` | Native plugin with skill and MCP; default on first install |
| `skill` | Personal skill using CLI; no MCP or marketplace registration |
| `skill-mcp` | Personal skill plus a directly registered MCP server |
| `mcp` | Direct MCP only; no skill or marketplace registration |

The installer manages skill links at `~/.agents/skills/visual-decider` for Codex and `~/.claude/skills/visual-decider` for Claude Code (`CLAUDE_CONFIG_DIR` is respected). No skill files need to be copied by hand. `--codex-skills-dir` and `--claude-skills-dir` override these directories. The skill contains instructions and a small launcher; the model stays in the shared runtime, not in each skill.

Omitting `--integration` on later installs retains each selected agent's previous mode. Switching to standalone modes removes/disables this package's user plugin and replaces/removes its direct MCP entry as appropriate. A legacy MCP executable registered under this installation, including accidental leading whitespace, is recognized and repaired. Unrelated skills and MCP registrations with the same name are refused rather than overwritten. Project-scoped integrations need to be removed in that project first. Restart agent sessions after switching modes. Managed organization policies still apply.

Older Claude Code versions may report `unknown command 'list'` for `claude plugin list`. Standalone modes handle this automatically through the documented [`enabledPlugins` setting](https://code.claude.com/docs/en/plugins-reference), changing only `visual-decider@visual-decider` to `false` in user settings. You do not need to upgrade Claude Code or use its plugin marketplace for a standalone skill. Other plugin-list failures remain errors.

## Models and downloads

| Physical memory | Automatic model |
|---|---|
| 8–15 GiB | `mlx-community/gemma-4-e2b-it-4bit` |
| 16–31 GiB (including 18 GiB Macs) | `mlx-community/gemma-4-e4b-it-4bit` |
| 32 GiB or more | `google/gemma-4-E4B-it` (BF16) |

These are selection tiers, not measured peak-memory guarantees. macOS, other apps, image sizes, and request sizes still affect available memory. Quantization and the smaller E2B model can change answers. Below 8 GiB, or if memory detection fails, automatic selection stops with an explicit error; an administrator can still choose `--model`. Selection uses physical memory rather than fluctuating free memory so reruns are repeatable.

For gated Google weights, accept access on the [model page](https://huggingface.co/google/gemma-4-E4B-it) and authenticate with `hf auth login` or `HF_TOKEN` before installing. The installer reports an actionable error if access is unavailable. The MIT code license does not license the model weights.

## File access and custom settings

Select agents, a model, or access roots:

```bash
# From a cloned checkout:
bash install.sh --agents both --allow-root /path/to/media
bash install.sh --agents codex --model mlx-community/gemma-4-26B-A4B-it-4bit
bash install.sh --agents claude --allow-root /  # all media readable by your account
bash install.sh --agents none                # engine and CLI only
bash install.sh --model auto                 # reselect automatically, overriding a previous choice
```

Roots can be repeated. Existing roots and explicit model choices are retained unless overridden. Automatic selections are reevaluated on install; an older installation using the original Google E4B default migrates to the appropriate tier. Older custom snapshots are preserved. `--model auto` deliberately resets an explicit choice. Configuration is in `~/.local/share/visual-decider/config.json`; selection and integration provenance is in `installation.json`. Neither contains credentials. Set `VISUAL_DECIDER_HOME` when running the installer to relocate it. Stable launchers under that installation's `bin/` record the location explicitly, including for direct CLI commands.

## Updates and the shared model

Rerunning the installer reuses the versioned environment, complete cached model, settings, and named agent integrations. A per-installation lock prevents concurrent installers from modifying the same setup. Installation validates model files without loading a model or starting a server, unless `--check-model` is requested.

**Restart existing Codex/Claude Code sessions once after upgrading from 0.2.x** to release their old private models and pick up the new MCP adapter. New agent sessions and CLI calls share one model per installation. Simultaneous first requests are protected by a process lifetime lock. The model starts on the first visual request, survives individual agent exits, and shuts down after five minutes with no active requests. Later use restarts it. A crash releases the lock automatically. Model/configuration changes replace an idle service only after the previous process exits; a busy service asks the caller to retry. `--in-process` and manually started HTTP/Python engines are explicit opt-outs and can load additional copies.

To inspect or stop the shared engine (neither command starts a model):

```bash
~/.local/share/visual-decider/bin/visual-decider-service status
~/.local/share/visual-decider/bin/visual-decider-service stop
```

`status` reports the PID, model, loaded state, and active request count. `stop` refuses to interrupt active work. Several lightweight MCP adapter processes are normal; only the shared engine loads weights. Different `VISUAL_DECIDER_HOME` directories intentionally have independent engines.

## Marketplace troubleshooting

The README’s standalone skill setup does not register a marketplace. If you specifically need a local Claude plugin, provision it and load it directly:

```bash
bash install.sh --agents none
claude --plugin-dir "$HOME/.local/share/visual-decider/marketplace/plugins/visual-decider"
```

Local plugin loading still follows your organization's plugin policy.

## Model health check

```bash
~/.local/share/visual-decider/bin/visual-decider-health
# Files and process status only; does not start/load the model:
~/.local/share/visual-decider/bin/visual-decider-health --no-inference
```

The default check validates configuration and local model files, starts/reuses the shared service, then freshly encodes two generated color images and checks their expected answers across choice rotations. It reports stage-specific errors, model metadata, memory counters, timing, and the service PID/log location as JSON. Failures exit with status 1. It never downloads weights; rerun installation to provision missing files. `preflight_ok` with `--no-inference` means inference was skipped. The synthetic smoke test checks basic model operation, not accuracy on your real tasks. Run it after installation or for diagnosis, not before every request. Add `--check-model` to an installation command to run it at the end.


## Sandbox lock-file errors

Release 0.5.0 fixes the error about writing `/tmp/visual-decider-UID-HASH/engine.lock` outside the sandbox. Runtime sockets and logs now respect `$TMPDIR`, and model ownership uses a read-only lock on the existing installation directory. The fix does not change agent sandbox permissions.

From a regular terminal on the affected Mac, stop the old idle runtime **before** upgrading, then install the fix:

```bash
~/.local/share/visual-decider/bin/visual-decider-service stop
curl -fsSL https://raw.githubusercontent.com/tomyak/viz-dec/v0.5.0/install.sh | bash -s -- --agents claude
```

The installer remembers your existing skill/MCP/plugin choice and reuses cached model files. Use `--agents codex` or `--agents both` as appropriate. Restart the agent and retry your original request. If the old service reports busy, let the job finish before stopping it.

Use the same writable `TMPDIR` for sessions that need to discover one another's shared model. If another temp root or an older session still owns the model, the new session waits up to 30 seconds and reports the conflict instead of loading a second copy. Stop that runtime from its original session, or let it exit after five idle minutes. Unix socket/process restrictions imposed separately by an organization still apply; this change addresses filesystem write restrictions.
