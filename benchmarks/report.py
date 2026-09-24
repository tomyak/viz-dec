import json
import statistics
from pathlib import Path

models = [
    json.loads(Path("benchmarks", name).read_text()) for name in ("e4b.json", "26b-4bit.json")
]
s = [
    "# Measured results — 2026-09-24",
    "",
    "All model weights were already cached. No model training or image upload was used. Results are synthetic regression evidence, not a deployment accuracy/calibration study. Four seeded distinct random orderings per fixture, nine fixtures, five methods: 180 decisions per model.",
    "",
    "## Runtime comparison",
    "",
    "| Metric | E4B BF16 | 26B-A4B 4-bit |",
    "|---|---:|---:|",
]
for title, key, source in [
    ("Load seconds", "load_seconds", "runtime"),
    ("Peak MLX GB", "peak_memory_bytes", "runtime"),
    ("Image encode seconds", "image_encode_seconds", "performance"),
    ("First question seconds", "first_question_seconds", "performance"),
    ("Cached question seconds", "subsequent_question_seconds", "performance"),
    ("Decisions/sec (four rotations)", "decisions_per_second", "performance"),
    ("Three cached questions seconds", "batch_three_seconds", "performance"),
    ("Three independent encodes seconds", "independent_three_seconds", "performance"),
]:
    values = [d[source][key] / (1e9 if key.endswith("bytes") else 1) for d in models]
    s.append(f"| {title} | {values[0]:.3f} | {values[1]:.3f} |")
s += [
    "",
    "Load measurements use a warm filesystem cache. First/subsequent question timings use the same login fixture with four choices after the experiment has warmed the runtime. Peak memory is MLX allocator peak, not total process RSS. Timings are single-machine observations, not latency percentiles.",
    "",
    "## Method cost across all fixtures",
    "",
    "| Method | E4B mean seconds | 26B mean seconds |",
    "|---|---:|---:|",
]
for method in ("label", "label_permute", "label_logmean", "candidate", "candidate_permute"):
    times = [
        statistics.mean(r["mean_seconds"] for r in d["rows"] if r["method"] == method)
        for d in models
    ]
    s.append(f"| {method} | {times[0]:.3f} | {times[1]:.3f} |")
s += [
    "",
    "## Bias evidence",
    "",
    "All eight unambiguous fixtures had the expected winner for all tested methods and orderings on both models (32/32 obvious-case decisions per method/model). This easy set cannot establish an accuracy advantage.",
    "",
    "The ambiguous gray-circle fixture is the informative order-bias case. Winner stability is the largest share of tested orders selecting one winner; score deviation is the largest per-choice population standard deviation.",
    "",
    "| Model / method | Winner stability | Max score std |",
    "|---|---:|---:|",
]
for d in models:
    for r in d["rows"]:
        if r["fixture"] == "ambiguous":
            s.append(
                f"| {d['model']} / {r['method']} | {r['winner_stability']:.2f} | {r['max_score_std']:.5f} |"
            )
s += [
    "",
    "E4B naive labels changed winners; arithmetic and geometric rotations retained one winner and reduced score variance. The 26B model was already stable on this example, and arithmetic averaging slightly increased its tiny score variance. Candidate C is order invariant by design because options never enter its prompt; that is not empirical evidence of better understanding. The ambiguous fixture has no correct label and can yield high preferences even when the content is underdetermined. No universal threshold is warranted.",
    "",
    "Keep B as the correctness baseline. Expose logmean and candidate methods as measured alternatives; choose on a representative task-specific held-out set. E4B is the current default because the larger cached model showed no benefit on obvious fixtures and costs more for label permutations.",
    "",
    "## Reproduction and gaps",
    "",
    "Raw results: [E4B](e4b.json), [26B](26b-4bit.json). Run `benchmarks/evaluate.py`; recorded snapshots make model identity explicit. E2B/E4B-quantized/31B cache directories contained references without local weight snapshots, so those variants were not downloaded or benchmarked. Google 26B BF16 weights are present but were not run; the practical 26B comparison used the quantized snapshot.",
    "",
    "These are original synthetic drawings, not photographs. Real screenshots/documents, prompt-paraphrase stress, 2–10-way task quality, calibrated error rates, and noisy real-world video remain evaluation work. Unit tests cover 2–10-way mappings; model evaluation uses the fixture choice sets.",
]
if Path("benchmarks/extended.json").exists():
    ext = json.loads(Path("benchmarks/extended.json").read_text())
    s += [
        "",
        "## Video and memory",
        "",
        f"Verified hardware: `{ext['hardware'].replace(chr(10), ' / ')}` (model name / RAM bytes).",
        "",
        "Eight-second synthetic video: empty room → dog → person → empty room, transitions at 2/4/6 seconds. Both paths recovered the four expected sampled intervals.",
        "",
        "| Duplicate filter | Wall seconds | Sampled frames/sec | Classified frames |",
        "|---|---:|---:|---:|",
    ]
    for r in ext["runs"]:
        s.append(
            f"| {r['filtering']} | {r['seconds']:.3f} | {r['frames_per_second']:.2f} | {r['result']['frames_classified']} |"
        )
    s += [
        "",
        f"Cache growth run ended at {ext['cache_growth'][-1]['cache']['entries']} entries and {ext['cache_growth'][-1]['cache']['bytes'] / 1e6:.2f} MB of cached state. Raw allocator observations are in [extended.json](extended.json). Thumbnail filtering is lossy and off by default; throughput changes include fewer language-model passes, not just vision reuse.",
    ]
Path("benchmarks/REPORT.md").write_text("\n".join(s) + "\n")
