"""Measure one model in a fresh process on the synthetic fixture batch (not a RAM guarantee)."""

import argparse
import json
import platform
import resource
from pathlib import Path

from visual_decider import Analyzer

parser = argparse.ArgumentParser()
parser.add_argument("--model", required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
fixtures = json.loads(Path("tests/fixtures/manifest.json").read_text())
analyzer = Analyzer(args.model)
batch = analyzer.analyze_batch(
    files=[
        {"path": f["path"], "questions": [{"question": f["question"], "choices": f["choices"]}]}
        for f in fixtures
    ]
)
report = {
    "model": args.model,
    "hardware": platform.platform(),
    "peak_mlx_bytes": analyzer.info()["peak_memory_bytes"],
    "max_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    * (1 if platform.system() == "Darwin" else 1024),
    "summary": batch["summary"],
    "winners": [r["result"]["decisions"][0]["winner"] for r in batch["results"]],
}
args.output.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
