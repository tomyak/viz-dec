# Private corporate distribution

The public upstream is MIT-licensed. A corporation can maintain a private fork or internal Git mirror containing the engine, lockfile, installer, and both plugin catalogs. Keep model licensing and access approvals separate from the code license. No employee needs to copy a skill file.

## Approved release installation

Authenticate through your organization's normal GitHub CLI, SSH agent, or Git credential helper. Clone an approved immutable tag or commit from the private repository, then invoke its installer. Example one-shell-command installation using GitHub CLI:

```bash
gh repo clone YOUR_ORG/viz-dec "$HOME/visual-decider-install" -- --branch v0.2.0 --depth 1 && bash "$HOME/visual-decider-install/install.sh" --agents both --allow-root "$HOME/Work/Media"
```

Replace the organization and tag. For GitHub Enterprise, use your normal enterprise Git URL and credential helper:

```bash
git clone --branch v0.2.0 --depth 1 git@github.company.example:AI/viz-dec.git "$HOME/visual-decider-install" && bash "$HOME/visual-decider-install/install.sh" --agents both
```

The installer registers a durable local marketplace copied from the approved source. Runtime paths do not depend on the checkout, and auto-refresh does not silently select a newer GitHub release. Remove the temporary checkout after successful installation if desired. Updates require running the approved version's installer. IT can deploy this same command using an existing endpoint-management system.

Do not embed credentials in URLs, manifests, shell arguments, lockfiles, or configuration. Use Git/Hugging Face authentication helpers or managed environment injection. The installer does not serialize `HF_TOKEN` or Git tokens. Review the contents of internal logs under your usual retention policy.

## Model provisioning and offline environments

The installer first checks for a complete cached checkpoint. The default Google E4B and optional MLX Community 26B quantization are pinned to commit IDs in `visual_decider/models/download.py`. If absent/incomplete, provisioning downloads the model. Gated repositories require prior authorization and license acceptance on Hugging Face.

For an internal model mirror, provision a vetted Gemma 4 multimodal snapshot on the endpoint and pass its absolute path:

```bash
bash install.sh --agents both --model /opt/company/models/gemma4-approved --allow-root "$HOME/Work/Media"
```

Configuration records the resolved local snapshot, so subsequent inference does not resolve mutable remote branches. Snapshot validation checks architecture, tokenizer presence, referenced shards, and safetensors byte ranges. It detects missing/truncated weights; it is **not** a cryptographic attestation of arbitrary local weights. IT should verify mirror checksums and approved provenance before deployment. Remote model code is disabled.

For an air-gapped install, pre-provision uv, Python 3.12, the locked wheel/build caches or an approved package mirror, and the model snapshot. Run `bash install.sh --offline --model /opt/company/models/gemma4-approved`. The shell bootstrap can need network access if uv/Python are absent; provision them first for a fully offline bootstrap. `HF_HUB_OFFLINE=1` also blocks model downloads. Standard uv index/certificate settings can point to your approved package infrastructure; do not modify the lockfile casually.

## File access and agent boundaries

MCP defaults to the user's home directory. Restrict roots with repeated `--allow-root` options, or deliberately allow all readable local files with `--allow-root /`. Symlinks are resolved before enforcing roots. Direct Python callers choose their own roots. No server can override filesystem permissions.

The core and MLX backend do not import Codex or Claude libraries. A single MCP implementation and shared skill sit behind separate native metadata. MCP sends local paths and structured decisions, not image bytes. The hosting coding agent may independently upload attachments or retain tool results according to its own settings; local inference does not change those policies.

The default plugin has no network listener or login service. Each agent-owned MCP process can retain its own model, so capacity-plan for concurrent sessions. Optional HTTP sharing must remain loopback-only and is intended for a trusted single-user machine. It does not provide tenant isolation or authentication.

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

Reference: [Codex plugins](https://developers.openai.com/plugins/build/plugins), [Claude Code plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces), [Claude plugin reference](https://code.claude.com/docs/en/plugins-reference).
