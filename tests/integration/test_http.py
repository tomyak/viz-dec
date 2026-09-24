import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_pipeline import Backend

from visual_decider import Analyzer
from visual_decider.adapters.client import Client
from visual_decider.adapters.http import create_app


def test_http_errors_and_batch(tmp_path):
    image = tmp_path / "x.png"
    Image.new("RGB", (24, 24), "white").save(image)
    analyzer = Analyzer(backend=Backend(), roots=[tmp_path])
    with TestClient(
        create_app(analyzer_factory=lambda: analyzer), base_url="http://127.0.0.1"
    ) as client:
        assert client.get("/health").status_code == 200
        data = {"path": str(image), "question": "Brightness?", "choices": ["Light", "Dark"]}
        response = client.post("/classify_image", json=data)
        assert response.status_code == 200 and response.json()["winner"] == "Light"
        assert (
            client.post(
                "/inspect_image",
                json={
                    "path": str(image),
                    "questions": [{"question": "Brightness?", "choices": ["Light", "Dark"]}],
                },
            ).status_code
            == 200
        )
        assert (
            client.post("/classify_image", json={**data, "choices": ["Light", "Light"]}).status_code
            == 400
        )
        assert (
            client.post(
                "/classify_image", json={**data, "path": str(tmp_path / "missing")}
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/classify_image", json=data, headers={"origin": "https://evil.example"}
            ).status_code
            == 403
        )
        assert client.post("/classify_image", content=b"x" * 65537).status_code == 413
        assert client.post("/classify_image", json={**data, "choices": []}).status_code == 422
        assert client.get("/health", headers={"host": "evil.example"}).status_code == 400
        assert analyzer.backend.encodes == 1


def test_no_remote_client():
    with pytest.raises(ValueError):
        Client("https://cloud.example")
    with pytest.raises(ValueError):
        Client("http://127.0.0.1.evil.example")


def test_backend_failure_is_explicit(tmp_path):
    class Broken(Backend):
        def score(self, *args):
            raise RuntimeError("backend does not expose required scoring logits")

    p = tmp_path / "x.png"
    Image.new("RGB", (16, 16), "white").save(p)
    with TestClient(
        create_app(analyzer_factory=lambda: Analyzer(backend=Broken(), roots=[tmp_path])),
        base_url="http://127.0.0.1",
    ) as client:
        r = client.post(
            "/classify_image", json={"path": str(p), "question": "x", "choices": ["a", "b"]}
        )
        assert r.status_code == 500
        assert "scoring logits" in r.text


def test_missing_service_explains_separate_process(monkeypatch):
    import httpx

    def refused(*args, **kwargs):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(httpx.Client, "post", refused)
    with pytest.raises(RuntimeError, match="Shared HTTP mode"):
        Client().call("classify_image", path="x.png", question="x", choices=["a", "b"])
