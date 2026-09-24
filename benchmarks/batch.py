"""Compare repeated inspect calls with a content-deduplicating batch on real Gemma."""

import json
import time
from pathlib import Path

from visual_decider import Analyzer

analyzer = Analyzer()
files = ["tests/fixtures/login.png", "tests/fixtures/error.png", "tests/fixtures/login.png"]
questions = [
    {
        "question": "What state is the UI in?",
        "choices": ["Login page", "Error dialog", "Dashboard"],
    },
    {"question": "Is an error visible?", "choices": ["Yes", "No"]},
]
analyzer.inspect_image(files[0], questions)  # Warm model/kernels, outside timed region.
analyzer.cache.clear()
start = time.perf_counter()
before = analyzer.backend.encodes
naive = [analyzer.inspect_image(path, questions) for path in files]
naive_time = time.perf_counter() - start
naive_encodes = analyzer.backend.encodes - before
analyzer.cache.clear()
start = time.perf_counter()
batched = analyzer.analyze_batch(files=files, questions=questions)
batch_time = time.perf_counter() - start
for expected, actual in zip(naive, batched["results"]):
    assert [x["winner"] for x in expected["decisions"]] == [
        x["winner"] for x in actual["result"]["decisions"]
    ]
report = dict(
    model=analyzer.backend.name,
    snapshot=analyzer.backend.identity,
    files=files,
    questions=questions,
    repeated_inspect_seconds=naive_time,
    batch_seconds=batch_time,
    speedup=naive_time / batch_time,
    repeated_inspect_encodes=naive_encodes,
    batch_summary=batched["summary"],
    note="One warmed local run, three images including one duplicate; no universal speedup claim.",
)
Path("benchmarks/batch.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
