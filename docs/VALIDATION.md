# Validation record — 0.2.0, 2026-09-24

Local hardware: Apple M3 Max, 128 GiB RAM.

- Unit/integration suite: **54 passed**, 11 GPU tests skipped by default. Covers mathematical properties, image bounds, cache invalidation, HTTP and MCP contracts, worker lifecycle, model provisioning, and installation ordering.
- Current E4B Metal suite: **11 passed**. Checks expected synthetic fixture winners in both choice orders, cached/fresh visual equivalence, and candidate KV-branch scores against independent full-sequence teacher forcing.
- Real stdio MCP test through the **installed plugin's exact launcher**: initialization, four tools listed, image/inspect/video calls, missing-file error, and mixed image/video batch with per-file question overrides passed. It runs the installed noneditable package with its own session-owned model, without HTTP.
- Batch regressions verify one encode for identical pixels across PNG/BMP, one video container per multi-question request, repeated-decision reuse, prevalidation before encoding, folder filtering/root limits, partial failures, and global sample/decision budgets.
- Both native plugin manifests and shared skill validated. Codex and Claude Code plugin CLI installation succeeded; a repeat install succeeded without duplicating registrations.
- Fresh noneditable engine installation into a path containing spaces succeeded with cached dependencies/model and `--offline`. The normal installer reused the complete cached E4B snapshot. Unit tests exercise the missing-cache download branch and provisioning-failure ordering; an unnecessary second model download was not performed.
- Ruff lint/format, release-version checks, and wheel/sdist builds passed locally. GitHub CI runs Linux/macOS non-model tests and core-only import checks; the tag workflow builds release artifacts/checksums.
- Old direct MCP registrations and duplicated user skills were removed after validating the plugin; legacy skills were backed up locally. No login service was installed. The obsolete manually launched development HTTP process was stopped.

`benchmarks/batch.json` records a new warmed comparison against repeated `inspect_image` calls using the same resident model. It checks winner equivalence and actual encode/decision reuse. The earlier 180-decision-per-model scoring study and 26B model tests remain historical evidence in `benchmarks/REPORT.md`; they do not imply a fresh 26B rerun after this release's decoder changes.

No new frontier-agent conversation was launched to test automatic skill selection. Fresh sessions are needed to discover the installed plugin. An upstream Transformers audio mel-filter warning appears at model load; it did not prevent the image/video tests. Audio is outside this API.

Synthetic fixtures and local smoke tests do not establish real-world accuracy, calibrated error rates, precise OCR, or temporal action recognition. Scores can remain confidently wrong. GPU tensor batching and cross-question language-KV sharing are not implemented; shared encodes, decoder work, and bounded decision memoization are implemented and tested.
