import json

import pytest

from visual_decider.models.download import (
    DEFAULT_MODEL,
    PINNED_REVISIONS,
    ensure_model,
    validate_snapshot,
)


def snapshot(path):
    path.mkdir(exist_ok=True)
    (path / "config.json").write_text(
        json.dumps({"model_type": "gemma4", "vision_config": {"x": 1}})
    )
    (path / "tokenizer.json").write_text("{}")
    header = json.dumps({"weight": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}}).encode()
    (path / "model.safetensors").write_bytes(len(header).to_bytes(8, "little") + header + b"\0" * 4)
    return path


def test_snapshot_requires_complete_shards(tmp_path):
    path = snapshot(tmp_path)
    assert validate_snapshot(path) == path
    weights = path / "model.safetensors"
    weights.write_bytes(weights.read_bytes()[:-1])
    with pytest.raises(ValueError, match="Truncated"):
        validate_snapshot(path)
    (path / "model.safetensors.index.json").write_text(
        json.dumps({"weight_map": {"a": "missing.safetensors"}})
    )
    with pytest.raises(FileNotFoundError):
        validate_snapshot(path)
    (path / "model.safetensors.index.json").write_text(
        json.dumps({"weight_map": {"a": "../outside"}})
    )
    with pytest.raises(ValueError, match="filename"):
        validate_snapshot(path)


def test_model_download_and_cached_reuse(tmp_path, monkeypatch):
    import huggingface_hub
    from huggingface_hub.errors import LocalEntryNotFoundError

    calls = []
    path = tmp_path / "weights"

    def download(**kwargs):
        calls.append(kwargs)
        if kwargs["local_files_only"] and not path.exists():
            raise LocalEntryNotFoundError("not cached")
        return str(snapshot(path))

    monkeypatch.setattr(huggingface_hub, "snapshot_download", download)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    assert ensure_model(download=True) == path
    assert [c["local_files_only"] for c in calls] == [True, False]
    assert all(c["revision"] == PINNED_REVISIONS[DEFAULT_MODEL] for c in calls)
    calls.clear()
    assert ensure_model(download=True) == path
    assert len(calls) == 1 and calls[0]["local_files_only"]


def test_missing_model_inference_never_downloads(monkeypatch):
    import huggingface_hub
    from huggingface_hub.errors import LocalEntryNotFoundError

    def missing(**kwargs):
        assert kwargs["local_files_only"]
        raise LocalEntryNotFoundError("not cached")

    monkeypatch.setattr(huggingface_hub, "snapshot_download", missing)
    with pytest.raises(FileNotFoundError, match="visual-decider-model"):
        ensure_model(download=False)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    with pytest.raises(RuntimeError, match="HF_HUB_OFFLINE"):
        ensure_model(download=True)
