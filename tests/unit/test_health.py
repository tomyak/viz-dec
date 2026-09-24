import json
from types import SimpleNamespace

import pytest

from visual_decider.adapters import health
from visual_decider.classifier import Analyzer


class ColorBackend:
    def __init__(self, broken=False):
        self.encodes = 0
        self.broken = broken

    def encode(self, image):
        self.encodes += 1
        return image.getpixel((0, 0)), 1

    def score(self, state, question, choices, method):
        expected = "Red" if self.broken or state[0] == 255 else "Blue"
        return [10 if c == expected else 0 for c in choices], {}

    def info(self):
        return {"vision_encodes": self.encodes}


def test_health_uses_fresh_vision_every_time_and_detects_ignored_input():
    backend = ColorBackend()
    analyzer = Analyzer(backend=backend)
    for _ in range(2):
        result = analyzer.model_health()
        assert result["status"] == "ok"
        assert all(not c["decision"]["cache_hit"] for c in result["checks"])
    assert backend.encodes == 4
    assert Analyzer(backend=ColorBackend(broken=True)).model_health()["status"] == "error"


def test_missing_weights_never_starts_engine(tmp_path, monkeypatch):
    (tmp_path / "config.json").write_text(json.dumps({"model": str(tmp_path / "missing")}))
    monkeypatch.setattr(health, "SharedClient", lambda **kw: pytest.fail("Must not start"))
    report = health.check_health(home=tmp_path)
    assert report["status"] == "error"
    assert report["checks"][-1]["stage"] == "model_files"
    assert not report["inference_tested"]


@pytest.mark.parametrize("failure", [None, "socket", "inference", "wrong_answer"])
def test_health_stages_and_nonloading_preflight(tmp_path, monkeypatch, failure):
    calls = []

    def ensure(model, *, download):
        assert not download
        return tmp_path

    def start(config):
        calls.append("start")
        if failure == "socket":
            raise ConnectionError("unreachable")

    def call(operation):
        assert operation == "model_health"
        calls.append("inference")
        if failure == "inference":
            raise RuntimeError("GPU failed")
        return {"status": "error" if failure == "wrong_answer" else "ok"}

    monkeypatch.setattr(health, "ensure_model", ensure)
    monkeypatch.setattr(
        health,
        "SharedClient",
        lambda **kw: SimpleNamespace(
            runtime=tmp_path,
            status=lambda: {"status": "stopped"},
            configuration=lambda: {},
            ensure_running=start,
            call=call,
        ),
    )
    preflight = health.check_health(home=tmp_path, inference=False)
    assert preflight["status"] == "preflight_ok" and not calls
    assert not preflight["inference_tested"]
    report = health.check_health(home=tmp_path)
    assert report["status"] == ("error" if failure else "ok")
    if failure:
        assert report["checks"][-1]["stage"] == ("service" if failure == "socket" else "inference")
        assert report["hint"]


def test_health_cli_failure_is_json_and_nonzero(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["visual-decider-health"])
    monkeypatch.setattr(health, "check_health", lambda **kw: {"status": "error"})
    with pytest.raises(SystemExit) as error:
        health.main()
    assert error.value.code == 1
    assert json.loads(capsys.readouterr().out)["status"] == "error"
