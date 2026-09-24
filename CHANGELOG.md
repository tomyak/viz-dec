# Changelog

## 0.5.1 — 2026-09-24

- Discover and reuse an existing engine across the normal OS user temp directory, the current `TMPDIR`, and Claude's standard sandbox temp directory. Discovery is read-only; new engines still write only under the caller's temp directory, and the installation lifetime lock prevents duplicate models.
- Report socket-access denials immediately and include the bounded startup log on child-process failures. Health reports include the installed version and the discovered engine's log location.
- Recommend skill-with-MCP installation in the Claude/Codex quick starts, requiring no marketplace. Clarify that Bash socket permissions are separate from writable temp paths and that idle shutdown cannot grant access.

## 0.5.0 — 2026-09-24

- Return `model_cached` and per-request model-load, execution, queue, and total times for image, video, batch, and model-health decisions. Shared/HTTP clients also report round-trip time; batches report execution time per file.
- Keep resident-model reuse distinct from image-feature `cache_hit` and on-disk model files. Cold loading is charged once, even when several requests arrive together.
- Respect the sandbox's `TMPDIR` for runtime sockets/logs. Recover the normal user temp directory on macOS when MCP hosts omit the environment variable; reject overly long socket paths explicitly.
- Replace writable runtime lock files with an inherited read-only installation-directory lock, preventing duplicate models across different temp roots. Honor existing legacy locks during upgrades. No sandbox allowlist change or login service is installed.

## 0.4.1 — 2026-09-24

- Fix standalone skill/MCP installation on older Claude Code versions without `plugin list` or `--json` support. Use the documented user `enabledPlugins` setting to retire only the visual-decider plugin; preserve unrelated settings, permissions, and symlinks.
- Keep project-scoped plugin conflicts explicit and report policy/permission failures instead of treating them as missing CLI features.
- Recognize the older `No MCP server found with name` response during direct MCP discovery.

## 0.4.0 — 2026-09-24

- Add standalone skill, skill plus MCP, and direct MCP installation for Claude Code and Codex, without marketplace registration or manual skill copying. Preserve the selected integration per agent on repeat installs.
- Add stable, installation-bound launchers under `bin/`, including correctly quoted MCP registration for paths with spaces. Mode switches retire this package's old user integration and protect unrelated skills/MCP commands.
- Make the shared skill work through either MCP or CLI, including efficient multi-question batches. Publish a standalone skill archive alongside the native plugin archive.
- Add offline `visual-decider-health` diagnostics for configuration, cached model files, shared service, and fresh synthetic vision/scoring. Expose `model_health` through MCP and HTTP; checks share the existing model and queue.
- Add optional installer `--check-model`; ordinary installation still does not load weights. `--no-inference` offers a nonloading preflight check.

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
