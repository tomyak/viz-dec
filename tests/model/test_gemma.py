import json
import os
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.model,
    pytest.mark.skipif(
        os.getenv("RUN_MODEL_TESTS") != "1", reason="Set RUN_MODEL_TESTS=1 with Metal access"
    ),
]


@pytest.fixture(scope="module")
def analyzer():
    from visual_decider import Analyzer

    return Analyzer(os.getenv("VISUAL_DECIDER_MODEL"))


@pytest.mark.parametrize(
    "fixture", json.loads(Path("tests/fixtures/manifest.json").read_text()), ids=lambda x: x["name"]
)
def test_broad_behavior(analyzer, fixture):
    for order in (fixture["choices"], list(reversed(fixture["choices"]))):
        r = analyzer.classify_image(fixture["path"], fixture["question"], order)
        assert sum(c["score"] for c in r["choices"]) == pytest.approx(1)
        if fixture["expected"]:
            assert r["winner"] == fixture["expected"]


def test_cached_features_match_fresh(analyzer):
    f = json.loads(Path("tests/fixtures/manifest.json").read_text())[5]
    r = analyzer.classify_image(f["path"], f["question"], f["choices"])
    analyzer.cache.clear()
    fresh = analyzer.classify_image(f["path"], f["question"], f["choices"])
    assert [c["score"] for c in r["choices"]] == pytest.approx(
        [c["score"] for c in fresh["choices"]], abs=1e-4
    )


def test_candidate_cache_matches_full_forward(analyzer):
    from visual_decider.image import load_image
    from visual_decider.scoring import continuation_ids

    backend = analyzer.backend
    mx = backend.mx
    im, _ = load_image("tests/fixtures/error.png")
    state, _ = backend.encode(im)
    choices = ["Error dialog", "Dashboard"]
    question = "What is visible?"
    raw, _ = backend.score(state, question, choices, "candidate")
    prompt = backend.prompt(question, choices, "candidate")
    inputs = backend.inputs(state, prompt)
    n = inputs["input_ids"].shape[1]
    expected = []
    for choice in choices:
        ids = continuation_ids(backend.tokenizer, prompt, choice) + [
            backend.tokenizer.convert_tokens_to_ids("<turn|>")
        ]
        merged = dict(inputs)
        merged["input_ids"] = mx.concatenate([inputs["input_ids"], mx.array([ids[:-1]])], axis=1)
        merged["mm_token_type_ids"] = mx.concatenate(
            [inputs["mm_token_type_ids"], mx.zeros((1, len(ids) - 1), dtype=mx.int32)], axis=1
        )
        logits = backend.model(**merged).logits[0].astype(mx.float32)
        total = sum(
            logits[n - 1 + i, t] - mx.logsumexp(logits[n - 1 + i]) for i, t in enumerate(ids)
        )
        expected.append(total.item())
    # BF16 batched and incremental paths can differ slightly.
    assert raw == pytest.approx(expected, abs=0.25)
