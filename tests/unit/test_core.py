import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from visual_decider.cache import VisualCache
from visual_decider.image import load_image, local_path
from visual_decider.policy import DecisionPolicy
from visual_decider.scoring import (
    aggregate,
    continuation_ids,
    label_ids,
    logsumexp,
    normalize,
    rotations,
    validate,
)


@given(
    st.lists(
        st.floats(min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False),
        min_size=2,
        max_size=10,
    )
)
def test_normalization(xs):
    p = normalize(xs)
    assert sum(p) == pytest.approx(1, abs=1e-10)
    assert all(0 <= x <= 1 + 1e-12 for x in p)


@given(st.permutations([0, 1, 2, 3]))
def test_mapping(order):
    values = [1.0, 7.0, -2.0, 3.0]
    scores, _ = aggregate([[values[i] for i in order]], [order])
    assert scores == pytest.approx(normalize(values))


@pytest.mark.parametrize(
    "question,choices",
    [
        ("", ["a", "b"]),
        ("x", []),
        ("x", ["a"]),
        ("x", ["a", " a "]),
        ("x", ["", "b"]),
        ("x", [1, 2]),
        ("x", "ab"),
        ("x", ["a"] * 11),
    ],
)
def test_validation(question, choices):
    with pytest.raises(ValueError):
        validate(question, choices)


@pytest.mark.parametrize("xs", [[], [math.nan, 1], [math.inf, 1], [-math.inf, -math.inf]])
def test_invalid_math(xs):
    with pytest.raises(ValueError):
        normalize(xs)


def test_lse():
    assert logsumexp([math.log(0.2), math.log(0.3)]) == pytest.approx(math.log(0.5))
    assert normalize([-math.inf, 0]) == [0, 1]


def test_rotations():
    for n in range(2, 11):
        orders = rotations(n)
        assert all(sorted(row) == list(range(n)) for row in orders)
        assert all(sorted(row[i] for row in orders) == list(range(n)) for i in range(n))


def test_logmean_removes_additive_label_bias():
    semantic = [1.0, 4.0, 2.0]
    bias = [9.0, -3.0, 2.0]
    orders = rotations(3)
    raw = [[semantic[i] + bias[j] for j, i in enumerate(order)] for order in orders]
    scores, agreement = aggregate(raw, orders, "logmean")
    assert scores == pytest.approx(normalize(semantic))
    assert agreement < 1


def test_cache():
    c = VisualCache(2, 10)
    c.put("a", 1, 4)
    c.put("b", 2, 4)
    assert c.get("a") == 1
    c.put("c", 3, 4)
    assert c.get("b") is None
    assert c.bytes == 8
    c.put("a", 4, 2)
    assert c.bytes == 6
    c.put("big", 5, 11)
    assert c.get("big") is None
    c.clear()
    assert c.bytes == 0


def test_policy():
    assert DecisionPolicy().assess(0.99, 0.98, True)[0] == "review"
    assert DecisionPolicy(require_consistency=True).assess(0.99, 0.98, None)[0] == "escalate"
    assert DecisionPolicy(minimum_margin=0.2).assess(0.7, 0.3, False)[0] == "accept"
    with pytest.raises(ValueError):
        DecisionPolicy(minimum_score=math.nan)


def test_bad_images(tmp_path):
    p = tmp_path / "bad.png"
    p.write_bytes(b"invalid")
    with pytest.raises(ValueError):
        load_image(p)
    with pytest.raises(FileNotFoundError):
        load_image(tmp_path / "missing")
    with pytest.raises(ValueError):
        load_image("https://example.org/image.png")
    with pytest.raises(PermissionError):
        local_path(p, roots=[tmp_path / "other"])


class Tokenizer:
    all_special_ids = [99]

    def encode(self, s, **kwargs):
        return {
            "p": [1],
            "pA": [1, 2],
            "pB": [1, 3],
            "pbad": [5],
            "pctrl": [1, 99],
            "plong": [1, 4, 5],
        }[s]


def test_candidate_tokens():
    t = Tokenizer()
    assert label_ids(t, "p", 2) == [2, 3]
    assert continuation_ids(t, "p", "long") == [4, 5]
    with pytest.raises(ValueError):
        continuation_ids(t, "p", "bad")
    with pytest.raises(ValueError):
        continuation_ids(t, "p", "ctrl")


def test_optional_calibration():
    from visual_decider.calibration import TemperatureCalibration

    d = {
        "model": "fixture",
        "method": "label",
        "question": "x",
        "choices": [{"choice": "a", "score": 0.99}, {"choice": "b", "score": 0.01}],
    }
    c = TemperatureCalibration.fit([d] * 4, ["a", "b", "a", "b"], "held-out-fixture")
    assert c.temperature > 1
    assert c.apply(d)["choices"][0]["score"] < 0.99
    with pytest.raises(ValueError):
        c.apply({**d, "model": "other"})


def test_label_collisions_and_multitoken():
    class Collision(Tokenizer):
        def encode(self, s, **kw):
            return [1] if s == "p" else [1, 2]

    with pytest.raises(RuntimeError):
        label_ids(Collision(), "p", 2)

    class Multi(Tokenizer):
        def encode(self, s, **kw):
            return [1] if s == "p" else [1, 2, 3]

    with pytest.raises(RuntimeError):
        label_ids(Multi(), "p", 2)


def test_image_limits_and_animation(tmp_path, monkeypatch):
    from PIL import Image

    from visual_decider import image

    p = tmp_path / "x.png"
    Image.new("RGB", (20, 20), "white").save(p)
    monkeypatch.setattr(image, "MAX_PIXELS", 100)
    with pytest.raises(ValueError, match="pixel limit"):
        image.load_image(p)
    with pytest.raises(ValueError, match="byte limit"):
        local_path(p, max_bytes=1)
    p = tmp_path / "x.gif"
    Image.new("RGB", (5, 5), "white").save(
        p, save_all=True, append_images=[Image.new("RGB", (5, 5), "black")]
    )
    with pytest.raises(ValueError, match="Animated"):
        image.load_image(p)


def test_symlink_cannot_escape_roots(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"x")
    link = allowed / "link.png"
    link.symlink_to(outside)
    with pytest.raises(PermissionError):
        local_path(link, roots=[allowed])


def test_generator_normalization_and_ties():
    assert normalize(x for x in [0.0, 0.0]) == pytest.approx([0.5, 0.5])
    scores, agreement = aggregate([[0.0, 0.0], [0.0, 0.0]], [[0, 1], [1, 0]])
    assert scores == pytest.approx([0.5, 0.5])
    assert agreement == 0


@pytest.mark.parametrize("limits", [(-1, 100), (1, -1), (True, 10)])
def test_invalid_cache_limits(limits):
    with pytest.raises(ValueError):
        VisualCache(*limits)


def test_calibration_bound_to_snapshot():
    from visual_decider.calibration import TemperatureCalibration

    d = {
        "model": "fixture",
        "model_snapshot": "abc",
        "prompt_version": "v1",
        "method": "label",
        "question": "x",
        "choices": [{"choice": "a", "score": 0.8}, {"choice": "b", "score": 0.2}],
    }
    artifact = TemperatureCalibration.fit([d, d], ["a", "b"], "held-out")
    with pytest.raises(ValueError, match="mismatch"):
        artifact.apply({**d, "model_snapshot": "def"})
    with pytest.raises(ValueError, match="distribution"):
        artifact.apply({**d, "choices": [{"choice": "a", "score": float("nan")}]})
