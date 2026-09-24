# Measured results — 2026-09-24

All model weights were already cached. No model training or image upload was used. Results are synthetic regression evidence, not a deployment accuracy/calibration study. Four seeded distinct random orderings per fixture, nine fixtures, five methods: 180 decisions per model.

## Runtime comparison

| Metric | E4B BF16 | 26B-A4B 4-bit |
|---|---:|---:|
| Load seconds | 2.202 | 3.884 |
| Peak MLX GB | 16.806 | 16.431 |
| Image encode seconds | 0.139 | 0.444 |
| First question seconds | 0.919 | 1.965 |
| Cached question seconds | 0.771 | 1.532 |
| Decisions/sec (four rotations) | 1.297 | 0.653 |
| Three cached questions seconds | 2.302 | 4.535 |
| Three independent encodes seconds | 2.746 | 5.841 |

Load measurements use a warm filesystem cache. First/subsequent question timings use the same login fixture with four choices after the experiment has warmed the runtime. Peak memory is MLX allocator peak, not total process RSS. Timings are single-machine observations, not latency percentiles.

## Method cost across all fixtures

| Method | E4B mean seconds | 26B mean seconds |
|---|---:|---:|
| label | 0.243 | 0.490 |
| label_permute | 0.790 | 1.436 |
| label_logmean | 0.790 | 1.432 |
| candidate | 0.327 | 0.404 |
| candidate_permute | 1.358 | 1.707 |

## Bias evidence

All eight unambiguous fixtures had the expected winner for all tested methods and orderings on both models (32/32 obvious-case decisions per method/model). This easy set cannot establish an accuracy advantage.

The ambiguous gray-circle fixture is the informative order-bias case. Winner stability is the largest share of tested orders selecting one winner; score deviation is the largest per-choice population standard deviation.

| Model / method | Winner stability | Max score std |
|---|---:|---:|
| google/gemma-4-E4B-it / label | 0.50 | 0.37481 |
| google/gemma-4-E4B-it / label_permute | 1.00 | 0.10064 |
| google/gemma-4-E4B-it / label_logmean | 1.00 | 0.06047 |
| google/gemma-4-E4B-it / candidate | 1.00 | 0.00000 |
| google/gemma-4-E4B-it / candidate_permute | 1.00 | 0.05103 |
| mlx-community/gemma-4-26B-A4B-it-4bit / label | 1.00 | 0.00018 |
| mlx-community/gemma-4-26B-A4B-it-4bit / label_permute | 1.00 | 0.00071 |
| mlx-community/gemma-4-26B-A4B-it-4bit / label_logmean | 1.00 | 0.00001 |
| mlx-community/gemma-4-26B-A4B-it-4bit / candidate | 1.00 | 0.00000 |
| mlx-community/gemma-4-26B-A4B-it-4bit / candidate_permute | 1.00 | 0.00000 |

E4B naive labels changed winners; arithmetic and geometric rotations retained one winner and reduced score variance. The 26B model was already stable on this example, and arithmetic averaging slightly increased its tiny score variance. Candidate C is order invariant by design because options never enter its prompt; that is not empirical evidence of better understanding. The ambiguous fixture has no correct label and can yield high preferences even when the content is underdetermined. No universal threshold is warranted.

Keep B as the correctness baseline. Expose logmean and candidate methods as measured alternatives; choose on a representative task-specific held-out set. E4B is the current default because the larger cached model showed no benefit on obvious fixtures and costs more for label permutations.

## Reproduction and gaps

Raw results: [E4B](e4b.json), [26B](26b-4bit.json). Run `benchmarks/evaluate.py`; recorded snapshots make model identity explicit. E2B/E4B-quantized/31B cache directories contained references without local weight snapshots, so those variants were not downloaded or benchmarked. Google 26B BF16 weights are present but were not run; the practical 26B comparison used the quantized snapshot.

These are original synthetic drawings, not photographs. Real screenshots/documents, prompt-paraphrase stress, 2–10-way task quality, calibrated error rates, and noisy real-world video remain evaluation work. Unit tests cover 2–10-way mappings; model evaluation uses the fixture choice sets.

## Video and memory

Verified hardware: `Apple M3 Max / 137438953472` (model name / RAM bytes).

Eight-second synthetic video: empty room → dog → person → empty room, transitions at 2/4/6 seconds. Both paths recovered the four expected sampled intervals.

| Duplicate filter | Wall seconds | Sampled frames/sec | Classified frames |
|---|---:|---:|---:|
| False | 5.585 | 1.43 | 8 |
| True | 3.606 | 2.22 | 5 |

Cache growth run ended at 4 entries and 34.87 MB of cached state. Raw allocator observations are in [extended.json](extended.json). Thumbnail filtering is lossy and off by default; throughput changes include fewer language-model passes, not just vision reuse.
