# Code review and cleanup — 0.2.0

Concrete findings fixed during the release review:

| Finding | Change and regression evidence |
|---|---|
| MCP discovered tools but failed when its separately launched HTTP process stopped | Session-owned lazy engine; real stdio initialization and inference work without HTTP |
| Adapter-to-adapter coupling and mandatory agent/MLX dependencies | Transport-neutral runtime, optional dependency groups, separate agent metadata; core import check in CI |
| Cached models accepted a partial set of shards | Pinned revisions and safetensors/header/index checks; missing/truncated shard and download/cache tests |
| Decoder modified global OpenCV environment; tiny sample intervals could overflow | Container-scoped PyAV options, bounded index iteration, sequential sampler; subnormal-interval and external-resource tests |
| Batch use required repeated calls and video decoding per question | Shared plan/scorer, content deduplication, decision memo, one decoder pass for all questions; tests assert actual encode/pass/open counts |
| Ties could count as permutation agreement | Only unique row maxima count as agreement; tie regression |
| Probability normalization exhausted generators | Materialize once before normalization; generator regression |
| Invalid cache limits and weak batch validation reached inference | Reject invalid limits and validate complete question plans before encoding |
| Calibration identity omitted exact model/prompt revision | Include snapshot and prompt version, validate score distributions; mismatch and NaN regressions |
| HTTP/client validation and model queue lifecycle lacked clear boundaries | Loopback restrictions, body/host/origin tests, bounded worker, retry and cancellation-slot tests |
| Skill silently encouraged alternate question interpretation and required manual startup | Exact question/choice guidance, explicit prompt-variant attribution, session lifecycle documentation |
| Duplicated skills, prototype/research archives, personal fixtures, absolute user paths | One plugin skill; redundant source copies removed; personal samples preserved only in ignored local storage; benchmark paths sanitized |

The core does not claim general-purpose visual accuracy, probability calibration, temporal action recognition, simultaneous GPU batching, or cross-question language KV sharing. The sampled-video fall question can be sensitive to wording and choice sets. Preserve the original test and report disagreement; do not substitute posture labels and present them as the same question.

Historical scoring-method measurements remain in `benchmarks/`; they were not rewritten as if measured with the new batch/decoder implementation. Synthetic fixtures are regression evidence. New platform, model, dependency, or prompt changes require their own validation.
