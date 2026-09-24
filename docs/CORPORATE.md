# Private corporate distribution

The public upstream is MIT-licensed. A corporation can maintain a private fork or internal Git mirror containing the engine, lockfile, installer, and both plugin catalogs. Keep model licensing and access approvals separate from the code license. No employee needs to copy a skill file.

## Approved release installation

Authenticate through your organization's normal GitHub CLI, SSH agent, or Git credential helper. Clone an approved immutable tag or commit from the private repository, then invoke its installer. Example one-shell-command installation using GitHub CLI:

```bash
gh repo clone YOUR_ORG/viz-dec "$HOME/visual-decider-install" -- --branch v0.4.1 --depth 1 && bash "$HOME/visual-decider-install/install.sh" --agents both --allow-root "$HOME/Work/Media"
```

Replace the organization and tag. For GitHub Enterprise, use your normal enterprise Git URL and credential helper:

```bash
git clone --branch v0.4.1 --depth 1 git@github.company.example:AI/viz-dec.git "$HOME/visual-decider-install" && bash "$HOME/visual-decider-install/install.sh" --agents both
```

The installer registers a durable local marketplace copied from the approved source. Runtime paths do not depend on the checkout, and auto-refresh does not silently select a newer GitHub release. Remove the temporary checkout after successful installation if desired. Updates require running the approved version's installer. IT can deploy this same command using an existing endpoint-management system.

If marketplace registration is unavailable, add `--integration skill` to install the personal skill using CLI access, `--integration skill-mcp` for that skill plus direct MCP, or `--integration mcp` for direct MCP alone. These modes use no marketplace registration and install the same locked runtime and selected model. They still obey managed agent policies. The installer links managed skills into `~/.agents/skills` (Codex) and `~/.claude/skills` (Claude Code), with directory overrides for managed deployments. Neither staff nor IT needs to manually copy SKILL.md. The shared launcher binds custom installation paths and preserves argument boundaries.

Integration mode is remembered per agent. Switching retires this package's user plugin/direct MCP/skill as applicable; unrelated same-name configuration is refused and project-scoped conflicts need explicit project cleanup. Restart existing agent sessions after switching. Repeated registration uses one MCP name per agent, not new numbered servers.

Standalone Claude installation supports older CLIs without `plugin list` or its `--json` option. For these specific capability errors, the installer atomically sets only `enabledPlugins["visual-decider@visual-decider"]` to `false` in `CLAUDE_CONFIG_DIR/settings.json` (default `~/.claude/settings.json`). It preserves unrelated settings and file permissions, respects settings symlinks, and detects current-project plugin conflicts. Invalid JSON, permission errors, policy failures, and detected concurrent settings edits stop installation rather than being silently bypassed.

Do not embed credentials in URLs, manifests, shell arguments, lockfiles, or configuration. Use Git/Hugging Face authentication helpers or managed environment injection. The installer does not serialize `HF_TOKEN` or Git tokens. Review the contents of internal logs under your usual retention policy.

## Model provisioning and offline environments

The installer first checks for a complete cached checkpoint. All automatic model choices and the optional MLX Community 26B quantization are pinned to commit IDs in `visual_decider/models/download.py`. If absent/incomplete, provisioning downloads the model. Gated repositories require prior authorization and license acceptance on Hugging Face.

For an internal model mirror, provision a vetted Gemma 4 multimodal snapshot on the endpoint and pass its absolute path:

```bash
bash install.sh --agents both --model /opt/company/models/gemma4-approved --allow-root "$HOME/Work/Media"
```

Configuration records the resolved local snapshot, so subsequent inference does not resolve mutable remote branches. Snapshot validation checks architecture, tokenizer presence, referenced shards, and safetensors byte ranges. It detects missing/truncated weights; it is **not** a cryptographic attestation of arbitrary local weights. IT should verify mirror checksums and approved provenance before deployment. Remote model code is disabled.

For an air-gapped install, pre-provision uv, Python 3.12, the locked wheel/build caches or an approved package mirror, and the model snapshot. Run `bash install.sh --offline --model /opt/company/models/gemma4-approved`. The shell bootstrap can need network access if uv/Python are absent; provision them first for a fully offline bootstrap. `HF_HUB_OFFLINE=1` also blocks model downloads. Standard uv index/certificate settings can point to your approved package infrastructure; do not modify the lockfile casually.

## File access and agent boundaries

MCP defaults to the user's home directory. Restrict roots with repeated `--allow-root` options, or deliberately allow all readable local files with `--allow-root /`. Symlinks are resolved before enforcing roots. Direct Python callers choose their own roots. No server can override filesystem permissions.

The core and MLX backend do not import Codex or Claude libraries. A single MCP implementation and shared skill sit behind separate native metadata. MCP sends local paths and structured decisions, not image bytes. The hosting coding agent may independently upload attachments or retain tool results according to its own settings; local inference does not change those policies.

The default plugin has no TCP listener or login service. Agent sessions share one lazy model per installation through an owner-only Unix socket. The engine exits after five idle minutes; active jobs prevent termination. Runtime sockets/locks/logs live in an owner-only `/tmp/visual-decider-UID-HASH` directory. Separate installation homes, direct Python engines, `--in-process`, and manually started HTTP servers can still load separate models. Restart pre-0.3.0 agent sessions after upgrading to release their old private models. Optional HTTP must remain loopback-only and is intended for a trusted single-user machine; it does not provide tenant isolation or authentication.

The installer selects E2B 4-bit for 8–15 GiB, E4B 4-bit for 16–31 GiB, and E4B BF16 for 32+ GiB. For corporate approval, specify an approved model ID plus `--revision`, or a pre-provisioned local snapshot with `--model`. Explicit choices survive upgrades; `--model auto` opts back into hardware selection. The legacy default is migrated automatically, while legacy custom snapshots are preserved. Repeated installation validates/reuses cached required files and registers the same integration name; it does not load weights unless `--check-model` is requested. Concurrent installers for one installation are rejected by a lock.

Use `INSTALL_HOME/bin/visual-decider-health` for offline staged diagnostics and a synthetic vision/scoring test through the shared model. Failed checks produce JSON and exit 1. `--no-inference` is suitable for provisioning checks that must not load GPU weights, but only reports preflight readiness. Neither check downloads weights or uploads media. The synthetic test is not task-specific acceptance testing or cryptographic model attestation.

## Updates, rollback, and removal

Use `scripts/release.py --set-version MAJOR.MINOR.PATCH` in your fork and preserve version consistency. Publish immutable tags through a reviewed release process. Install an approved new tag with the same command; old engine environments remain under `versions/` so existing sessions can finish. Start fresh agent sessions after updates. To roll back, run the previous tag's installer; the matching plugin launcher selects that environment.

Remove integration with the agent CLIs:

```bash
codex plugin remove visual-decider@visual-decider
claude plugin uninstall visual-decider@visual-decider --scope user
codex plugin marketplace remove visual-decider
claude plugin marketplace remove visual-decider
```

After all sessions have stopped, delete only the visual-decider installation directory if no longer needed. Shared Hugging Face caches are intentionally retained. Legacy manually installed `visual-decider` MCP registrations and skill directories should be removed after verifying the plugin, to prevent duplicate tools or conflicting instructions; the installer does not delete unrelated user configuration.

For standalone modes, remove direct servers with `codex mcp remove visual-decider` or `claude mcp remove visual-decider --scope user`, and remove only the managed `visual-decider` symlink from the agent's personal skill directory. Stable `INSTALL_HOME/bin` launchers update on upgrades; shell PATH and directly registered MCP executables do not need version edits.

Reference: [Codex plugins](https://developers.openai.com/plugins/build/plugins), [Claude Code plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces), [Claude plugin reference](https://code.claude.com/docs/en/plugins-reference).
