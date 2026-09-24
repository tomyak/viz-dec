# Changelog

## 0.3.0 — 2026-09-24

- Select pinned Gemma models from physical memory: E2B 4-bit on 8–15 GiB, E4B 4-bit on 16–31 GiB, and E4B BF16 on 32+ GiB. Preserve explicit model choices and support `--model auto`.
- Share one on-demand model per installation across MCP and CLI sessions, with a process lifetime lock, crash recovery, serialized inference, private Unix socket, and five-minute idle shutdown. No login service is installed.
- Add `visual-decider-service status` and `stop`; retain deliberate `--in-process` and manual HTTP modes.
- Make repeat installs reuse unchanged configuration and cached models, record selection intent, and reject concurrent installers for the same installation.
- Fix cached provisioning to validate the same required-file patterns used during download.
- Restart existing 0.2.x agent sessions once after upgrading to release their private models.

## 0.2.1 — 2026-09-24

- Bind the installed MCP launcher to its installation directory explicitly, supporting custom paths even when agent hosts filter inherited environment variables.

## 0.2.0 — 2026-09-24

- Publish an agent-independent Python engine with optional MLX, MCP, and HTTP dependencies.
- Add a one-command, locked installer with cached-model validation and automatic model download.
- Ship native Codex and Claude Code plugins with a shared skill and MCP configuration.
- Load models lazily inside the session's MCP process; retain optional manual shared HTTP mode.
- Add bounded folder/file batches, per-file question batches, decoded-content deduplication, and decision memoization.
- Decode each video once for all questions; report decoded timestamps and separate question timelines.
- Fix incomplete snapshot acceptance, numeric edge cases, tie stability, calibration identity, decoder configuration, and input validation.
- Add CI, release artifacts/version checks, MIT licensing, and private-distribution documentation.
- Remove prototype archives, research checkouts, duplicate skills, machine-specific docs, and personal fixtures from the published project.
