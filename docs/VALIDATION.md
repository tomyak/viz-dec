# Validation record — 2026-09-24

Local hardware: Apple M3 Max, 128 GiB RAM.

## 0.3.0 model selection and shared-process validation

- Unit/integration suite: **75 passed**, 11 opt-in model tests skipped. Includes memory tier boundaries, automatic/explicit selection and legacy migration, concurrent installer rejection, unchanged settings on repeat install, and real child-process/socket tests for concurrent startup, lazy loading, reuse, crash recovery, configuration replacement, busy-service protection, idle shutdown, and invalid requests.
- Real Gemma suites: **11 passed each for E4B BF16, E4B 4-bit, and E2B 4-bit**. All models match the eight labeled synthetic fixture winners in both choice orders. Quantized and BF16 matmul kernels can differ between full-sequence and incremental evaluation; the regression now additionally checks independently prefetched incremental KV branches to `1e-4` and bounds full-forward discrepancy at `0.25` mean log-likelihood per token.
- A fresh nine-image batch measured **6.049 GB peak MLX allocation / 6.122 GB peak RSS** for E4B 4-bit and **4.448 GB / 4.581 GB** for E2B 4-bit. Evidence: `benchmarks/memory-e4b-4bit.json`, `benchmarks/memory-e2b-4bit.json`; reproduce with `benchmarks/memory.py`. These are measurements on a 128 GiB M3 Max, not tests on an actual 8/18 GiB Mac, worst-case memory bounds, or broad accuracy claims.
- Two real offline installer runs in an isolated installation, with memory detection simulated at 18 GiB, selected E4B 4-bit, reused dependencies and the complete model cache, preserved the configuration timestamp, and started no model process.
- Two simultaneous MCP clients using that installation's exact plugin launcher and an installed CLI command shared **one real Gemma PID and visual cache**. The service survived individual client exits and accepted the explicit stop command. Reproduce with `benchmarks/shared_smoke.py --home /path/to/isolated/install`.
- The cached-model lookup and download now use identical required-file patterns. Both newly downloaded quantized snapshots passed subsequent offline validation without downloading intentionally excluded repository documentation.
- Real installed MCP smoke tests passed image, inspect, sampled video, and mixed batch calls with E4B 4-bit. Two installer runs against the normal installation upgraded/reused both native agent registrations under the same names, without duplicate registrations.

## 0.2.0 baseline

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

## 0.2.1 installer compatibility check

The installer now writes `VISUAL_DECIDER_HOME` explicitly into the installed MCP configuration. A fresh installation into a directory containing spaces passed all four real MCP tool calls, including the mixed batch, when launched with the MCP SDK's filtered environment. The 54-test suite and native manifest validators passed again. Both agent plugins were upgraded through their normal CLI commands.
