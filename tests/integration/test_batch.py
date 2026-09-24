import cv2
import numpy as np
import pytest
from PIL import Image

from visual_decider import Analyzer

QUESTIONS = [
    {"question": "Brightness?", "choices": ["Light", "Dark"]},
    {"question": "Which shade?", "choices": ["Light", "Dark"]},
]


class Backend:
    def __init__(self):
        self.encodes = self.passes = 0

    def encode(self, rgb):
        self.encodes += 1
        return rgb.getpixel((0, 0))[0] > 100, 4

    def score(self, state, question, choices, method):
        self.passes += 1
        return [5.0 if c == ("Light" if state else "Dark") else 0.0 for c in choices], {}

    def info(self):
        return {}


def test_files_share_encodes_and_identical_decisions(tmp_path):
    backend = Backend()
    analyzer = Analyzer(backend=backend)
    paths = [tmp_path / name for name in ("a.png", "b.bmp")]
    for path in paths:
        Image.new("RGB", (32, 32), "white").save(path)
    result = analyzer.analyze_batch(files=[str(p) for p in paths], questions=QUESTIONS)
    assert result["summary"]["succeeded"] == 2
    assert backend.encodes == 1  # Decoded-content dedup, even across image formats.
    assert backend.passes == 4  # Two questions, two cyclic passes, shared across both files.
    assert result["summary"]["decisions_reused"] == 2
    assert result["results"][1]["result"]["decisions"][0]["decision_reused"]


def test_video_decoded_once_for_all_questions(tmp_path, monkeypatch):
    import visual_decider.video as video

    backend = Backend()
    analyzer = Analyzer(backend=backend)
    path = tmp_path / "sequence.avi"
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 64))
    for value in [0] * 20 + [255] * 20:
        out.write(np.full((64, 64, 3), value, dtype=np.uint8))
    out.release()
    original, opens = video.av.open, []

    def tracked(*args, **kwargs):
        opens.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(video.av, "open", tracked)
    result = analyzer.analyze_batch(files=[str(path)], questions=QUESTIONS)
    clip = result["results"][0]["result"]
    assert len(opens) == 1
    assert len(clip["samples"]) == 4 and len(clip["questions"]) == 2
    assert backend.encodes == 2 and backend.passes == 8
    assert [(e["start"], e["end"], e["choice"]) for e in clip["questions"][0]["events"]] == [
        (0, 2, "Dark"),
        (2, 4, "Light"),
    ]
    assert not clip["truncated"]


def test_plan_validation_errors_and_budgets(tmp_path):
    backend = Backend()
    analyzer = Analyzer(backend=backend, roots=[tmp_path])
    path = tmp_path / "a.png"
    Image.new("RGB", (32, 32), "white").save(path)
    with pytest.raises(ValueError):
        analyzer.analyze_batch(
            files=[str(path), {"path": str(path), "questions": []}], questions=QUESTIONS
        )
    assert backend.encodes == 0
    result = analyzer.analyze_batch(
        files=[
            str(tmp_path / "missing.png"),
            {"path": str(path), "questions": QUESTIONS[:1]},
            str(path),
        ],
        questions=QUESTIONS,
        max_decisions=3,
    )
    assert [r["status"] for r in result["results"]] == ["error", "ok", "skipped"]
    assert result["summary"]["decision_budget_used"] == 3


def test_folder_filtering_and_limit(tmp_path):
    analyzer = Analyzer(backend=Backend(), roots=[tmp_path])
    for name in ["b.png", "a.png", ".hidden.png"]:
        Image.new("RGB", (10, 10), "white").save(tmp_path / name)
    (tmp_path / "readme.txt").write_text("ignored")
    result = analyzer.analyze_batch(folder=tmp_path, questions=QUESTIONS)
    assert [r["path"] for r in result["results"]] == [
        str(tmp_path / "a.png"),
        str(tmp_path / "b.png"),
    ]
    with pytest.raises(ValueError, match="max_files"):
        analyzer.analyze_batch(folder=tmp_path, questions=QUESTIONS, max_files=1)
    with pytest.raises(PermissionError):
        analyzer.analyze_batch(folder=tmp_path.parent, questions=QUESTIONS)


def test_total_video_budget_truncates_then_skips(tmp_path):
    analyzer = Analyzer(backend=Backend())
    path = tmp_path / "short.avi"
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 64))
    for _ in range(40):
        out.write(np.zeros((64, 64, 3), dtype=np.uint8))
    out.release()
    result = analyzer.analyze_batch(
        files=[str(path), str(path)], questions=QUESTIONS, max_total_frames=2
    )
    assert result["results"][0]["result"]["truncated"]
    assert result["results"][0]["result"]["analyzed_until"] == 2
    assert result["results"][1]["status"] == "skipped"
    assert result["summary"]["frame_budget_used"] == 2
