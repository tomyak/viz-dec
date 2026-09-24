# Changelog

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
