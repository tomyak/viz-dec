"""Reproducible bias/performance experiment; writes incremental raw evidence."""

import argparse
import itertools
import json
import platform
import random
import statistics
import time
from pathlib import Path

from visual_decider import Analyzer

p = argparse.ArgumentParser()
p.add_argument("--model", default="google/gemma-4-E4B-it")
p.add_argument("--output", default="benchmarks/e4b.json")
p.add_argument("--orders", type=int, default=4)
args = p.parse_args()
a = Analyzer(args.model)
fixtures = json.loads(Path("tests/fixtures/manifest.json").read_text())
report = {"model": args.model, "hardware": platform.platform(), "orders": args.orders, "rows": []}


def persist():
    report["runtime"] = a.info()
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n")


for fixture in fixtures:
    orders = list(itertools.permutations(fixture["choices"]))
    random.Random(20260924).shuffle(orders)
    orders = orders[: args.orders]
    for method in ["label", "label_permute", "label_logmean", "candidate", "candidate_permute"]:
        results = []
        times = []
        for choices in orders:
            start = time.perf_counter()
            r = a.classify_image(fixture["path"], fixture["question"], list(choices), method=method)
            times.append(time.perf_counter() - start)
            results.append(r)
        scores = {
            c: [next(x["score"] for x in r["choices"] if x["choice"] == c) for r in results]
            for c in fixture["choices"]
        }
        winners = [r["winner"] for r in results]
        row = dict(
            fixture=fixture["name"],
            method=method,
            expected=fixture["expected"],
            winners=winners,
            winner_stability=max(winners.count(x) for x in set(winners)) / len(winners),
            accuracy=None
            if fixture["expected"] is None
            else sum(x == fixture["expected"] for x in winners) / len(winners),
            max_score_std=max(statistics.pstdev(s) for s in scores.values()),
            mean_seconds=statistics.mean(times),
            results=results,
        )
        report["rows"].append(row)
        persist()
        print(
            f"{fixture['name']:12} {method:18} stability={row['winner_stability']:.2f} expected={row['accuracy']} sd={row['max_score_std']:.4f} seconds={row['mean_seconds']:.3f}",
            flush=True,
        )
# Warm single-image timing, explicit cache misses, batch versus independent calls.
f = fixtures[4]
qs = [{"question": f["question"], "choices": f["choices"]}] * 3
a.cache.clear()
start = time.perf_counter()
a.classify_image(f["path"], f["question"], f["choices"])
cold = time.perf_counter() - start
state = next(iter(a.cache.entries.values()))[0]
start = time.perf_counter()
a.classify_image(f["path"], f["question"], f["choices"])
warm = time.perf_counter() - start
start = time.perf_counter()
a.inspect_image(f["path"], qs)
batch = time.perf_counter() - start
start = time.perf_counter()
for q in qs:
    a.cache.clear()
    a.classify_image(f["path"], **q)
independent = time.perf_counter() - start
report["performance"] = dict(
    first_question_seconds=cold,
    subsequent_question_seconds=warm,
    image_encode_seconds=state["encode_seconds"],
    preprocess_seconds=state["preprocess_seconds"],
    batch_three_seconds=batch,
    independent_three_seconds=independent,
    decisions_per_second=1 / warm,
)
persist()
