import json
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from visual_decider import Analyzer

analyzer = Analyzer()
path = Path("tests/fixtures/sequence.avi")
writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (448, 336))
assert writer.isOpened()
for name in ("empty_room", "dog", "person", "empty_room"):
    frame = cv2.cvtColor(np.asarray(Image.open(f"tests/fixtures/{name}.png")), cv2.COLOR_RGB2BGR)
    for _ in range(20):
        writer.write(frame)
writer.release()
report = {
    "hardware": subprocess.check_output(
        ["sysctl", "-n", "machdep.cpu.brand_string", "hw.memsize"], text=True
    ).strip(),
    "runs": [],
}
for filtering in [False, True]:
    analyzer.cache.clear()
    before = analyzer.backend.encodes
    start = time.perf_counter()
    r = analyzer.analyze_video(
        path, "What is depicted?", ["Dog", "Person", "Empty room"], suppress_duplicates=filtering
    )
    elapsed = time.perf_counter() - start
    assert [e["choice"] for e in r["events"]] == ["Empty room", "Dog", "Person", "Empty room"]
    assert [(e["start"], e["end"]) for e in r["events"]] == [(0, 2), (2, 4), (4, 6), (6, 8)]
    report["runs"].append(
        dict(
            filtering=filtering,
            seconds=elapsed,
            frames_per_second=len(r["samples"]) / elapsed,
            classified_frames_per_second=r["frames_classified"] / elapsed,
            encodes=analyzer.backend.encodes - before,
            result=r,
        )
    )
# Exercise LRU past capacity while observing live MLX memory.
report["cache_growth"] = []
for row in json.loads(Path("tests/fixtures/manifest.json").read_text()):
    analyzer.classify(row["path"], row["question"], row["choices"], method="label")
    report["cache_growth"].append(analyzer.info())
Path("benchmarks/extended.json").write_text(json.dumps(report, indent=2) + "\n")
print(
    json.dumps(
        {
            "hardware": report["hardware"],
            "video_seconds": [r["seconds"] for r in report["runs"]],
            "cache": analyzer.info(),
        },
        indent=2,
    )
)
