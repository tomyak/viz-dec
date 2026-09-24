import cv2
import numpy as np
import pytest
from PIL import Image

from visual_decider import Analyzer


class Backend:
    def __init__(self):
        self.encodes = 0

    def encode(self, im):
        self.encodes += 1
        return im.getpixel((0, 0))[0] > 100, 4

    def score(self, state, question, choices, method):
        return [5.0 if c == ("Light" if state else "Dark") else 0.0 for c in choices], {}

    def info(self):
        return {"vision_encodes": self.encodes}


@pytest.fixture
def analyzer():
    return Analyzer(backend=Backend(), cache_entries=1)


def test_session_batch_mutation(analyzer, tmp_path):
    p = tmp_path / "image.png"
    Image.new("RGB", (32, 32), "white").save(p)
    session = analyzer.open_image(p)
    assert session.classify("Brightness?", ["Light", "Dark"])["winner"] == "Light"
    result = analyzer.inspect_image(
        p, [{"question": "Brightness?", "choices": ["Light", "Dark"]}] * 2
    )
    assert analyzer.backend.encodes == 1
    assert all(x["cache_hit"] for x in result["decisions"])
    Image.new("RGB", (32, 32), "black").save(p)
    assert session.classify("Brightness?", ["Light", "Dark"])["winner"] == "Dark"
    assert analyzer.backend.encodes == 2


def test_video(analyzer, tmp_path):
    p = tmp_path / "test.avi"
    out = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 64))
    assert out.isOpened()
    for v in [0] * 20 + [255] * 20 + [0] * 20:
        out.write(np.full((64, 64, 3), v, dtype=np.uint8))
    out.release()
    result = analyzer.analyze_video(p, "Brightness?", ["Light", "Dark"], suppress_duplicates=True)
    assert result["frames_classified"] == 3
    assert [(e["start"], e["end"], e["choice"]) for e in result["events"]] == [
        (0, 2, "Dark"),
        (2, 4, "Light"),
        (4, 6, "Dark"),
    ]
    assert len(list(tmp_path.iterdir())) == 1  # no frame temp files
    capped = analyzer.analyze_video(p, "Brightness?", ["Light", "Dark"], max_frames=2)
    assert capped["truncated"] and capped["analyzed_until"] == 2
    with pytest.raises(ValueError):
        analyzer.analyze_video(p, "x", ["a", "b"], float("nan"))


def test_unsupported_video(analyzer, tmp_path):
    p = tmp_path / "bad.mp4"
    p.write_bytes(b"broken")
    with pytest.raises(ValueError):
        analyzer.analyze_video(p, "x", ["a", "b"])


def test_failed_frame_releases_container(analyzer, tmp_path, monkeypatch):
    from fractions import Fraction
    from types import SimpleNamespace

    from visual_decider import video

    p = tmp_path / "clip.avi"
    p.write_bytes(b"fixture")
    stream = SimpleNamespace(
        duration=20,
        average_rate=10,
        time_base=Fraction(1, 10),
        start_time=0,
        codec_context=SimpleNamespace(width=64, height=64),
    )

    class Container:
        closed = False
        streams = SimpleNamespace(video=[stream])

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True

        def seek(self, *args, **kwargs):
            pass

        def decode(self, *args):
            return iter([])

    container = Container()

    def open_container(*args, **kwargs):
        assert kwargs["options"]["protocol_whitelist"] == "file"
        with pytest.raises(ValueError, match="external"):
            kwargs["io_open"]("file:///outside", 0, {})
        return container

    monkeypatch.setattr(video.av, "open", open_container)
    with pytest.raises(ValueError, match="decoding failed"):
        analyzer.analyze_video(p, "x", ["a", "b"])
    assert container.closed


def test_batch_validated_before_encode(analyzer, tmp_path):
    p = tmp_path / "x.png"
    Image.new("RGB", (16, 16), "white").save(p)
    with pytest.raises(ValueError):
        analyzer.inspect_image(
            p, [{"question": "x", "choices": ["a", "b"]}, {"question": "", "choices": ["a", "b"]}]
        )
    assert analyzer.backend.encodes == 0


def test_eviction_reencodes(analyzer, tmp_path):
    files = []
    for i, c in enumerate(["white", "black"]):
        p = tmp_path / f"{i}.png"
        Image.new("RGB", (16, 16), c).save(p)
        files.append(p)
    for p in [*files, files[0]]:
        analyzer.classify(p, "Brightness?", ["Light", "Dark"])
    assert analyzer.backend.encodes == 3


def test_tiny_interval_is_bounded(analyzer, tmp_path, monkeypatch):
    import os

    p = tmp_path / "tiny.avi"
    out = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 64))
    for _ in range(10):
        out.write(np.zeros((64, 64, 3), dtype=np.uint8))
    out.release()
    monkeypatch.setenv("OPENCV_FFMPEG_CAPTURE_OPTIONS", "sentinel")
    result = analyzer.analyze_video(p, "x", ["a", "b"], sample_interval=1e-320, max_frames=2)
    assert result["truncated"] and len(result["samples"]) == 2
    assert os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] == "sentinel"
    assert result["samples"][0]["frame_time_s"] == 0
