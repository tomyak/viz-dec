"""Explicit model provisioning. Inference itself only opens validated local weights."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

DEFAULT_MODEL = "google/gemma-4-E4B-it"
PINNED_REVISIONS = {
    DEFAULT_MODEL: "ee0ef6023621cff504d758262d4e04895a5af4a2",
    "mlx-community/gemma-4-e4b-it-4bit": "475b9088d29754a3379866cf5aeb6b41acd313c2",
    "mlx-community/gemma-4-e2b-it-4bit": "238767527555cb75a05732a84dff5d6ba0dd6809",
    "mlx-community/gemma-4-26B-A4B-it-4bit": "0d77464eeb233a2da68ebf9d7dc4edaac7db956d",
}


def validate_snapshot(path: str | Path) -> Path:
    path = Path(path).expanduser().resolve(strict=True)
    config = json.loads((path / "config.json").read_text())
    if config.get("model_type") != "gemma4" or not config.get("vision_config"):
        raise ValueError("Expected a Gemma 4 multimodal checkpoint")
    if not (path / "tokenizer.json").is_file():
        raise FileNotFoundError("Model snapshot lacks tokenizer.json")
    index = path / "model.safetensors.index.json"
    if index.exists():
        mapping = json.loads(index.read_text()).get("weight_map", {})
        if not mapping:
            raise ValueError("Model weight index is empty")
        names = set(mapping.values())
        if any(not isinstance(n, str) or Path(n).name != n for n in names):
            raise ValueError("Invalid model shard filename")
        shards = [path / n for n in names]
    else:
        shards = [path / "model.safetensors"]
    # Read only headers, not multi-gigabyte tensor data; reject missing/truncated shards.
    for shard in shards:
        size = shard.stat().st_size
        with shard.open("rb") as stream:
            header_size = int.from_bytes(stream.read(8), "little")
            if not 2 <= header_size <= min(100_000_000, size - 8):
                raise ValueError(f"Invalid safetensors header: {shard.name}")
            header = json.loads(stream.read(header_size))
        tensors = [v for k, v in header.items() if k != "__metadata__"]
        if not tensors:
            raise ValueError(f"Empty model shard: {shard.name}")
        ends = []
        for tensor in tensors:
            start, end = tensor["data_offsets"]
            if not 0 <= start <= end <= size - 8 - header_size:
                raise ValueError(f"Truncated model shard: {shard.name}")
            ends.append(end)
        if max(ends) != size - 8 - header_size:
            raise ValueError(f"Model shard size mismatch: {shard.name}")
    return path


def ensure_model(model=DEFAULT_MODEL, *, revision=None, download=False) -> Path:
    candidate = Path(model).expanduser()
    if candidate.is_dir() or candidate.is_absolute() or str(model).startswith((".", "~")):
        if revision is not None:
            raise ValueError(
                "--revision requires a Hugging Face model ID, not a local snapshot path"
            )
        return validate_snapshot(candidate)
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import LocalEntryNotFoundError

    revision = revision or PINNED_REVISIONS.get(model)
    options = dict(
        repo_id=model,
        revision=revision,
        allow_patterns=["*.json", "*.jinja", "*.model", "*.safetensors", "*.txt"],
    )
    try:
        return validate_snapshot(snapshot_download(**options, local_files_only=True))
    except (LocalEntryNotFoundError, FileNotFoundError, ValueError, KeyError):
        if not download:
            raise FileNotFoundError(
                f"Complete cached weights unavailable for {model}. "
                f"Run visual-decider-model --model {model} to download them."
            ) from None
    if os.getenv("HF_HUB_OFFLINE", "").lower() in {"1", "true", "yes"}:
        raise RuntimeError(
            "HF_HUB_OFFLINE blocks installation downloads; pre-provision the snapshot"
        )
    try:
        path = snapshot_download(
            **options,
            local_files_only=False,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Could not download {model}. Check network access and, for gated Gemma weights, "
            "accept the model license on Hugging Face and authenticate with hf auth login "
            "or HF_TOKEN. No image data is involved in model downloads."
        ) from exc
    return validate_snapshot(path)


def main():
    parser = argparse.ArgumentParser(
        description="Reuse cached Gemma weights or download missing files"
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--revision")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    try:
        print(ensure_model(args.model, revision=args.revision, download=not args.offline))
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
