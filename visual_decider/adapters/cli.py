"""Command-line adapter for direct local execution or a resident HTTP service."""

import argparse
import json
from pathlib import Path

from ..runtime import EngineWorker
from .settings import load_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="Optional already-running loopback HTTP service")
    parser.add_argument("--model")
    parser.add_argument("--root", action="append")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("image", "video"):
        command = sub.add_parser(name)
        command.add_argument("path")
        command.add_argument("question")
        command.add_argument("choices", nargs="+")
        if name == "video":
            command.add_argument("--sample-interval", type=float, default=1.0)
            command.add_argument("--max-frames", type=int, default=300)
    command = sub.add_parser("inspect")
    command.add_argument("path")
    command.add_argument("questions", help="JSON array of question/choices objects")
    command = sub.add_parser("batch")
    source = command.add_mutually_exclusive_group(required=True)
    source.add_argument("--folder")
    source.add_argument("--files", nargs="+")
    source.add_argument("--manifest", type=Path, help="JSON request with shared/per-file questions")
    question_source = command.add_mutually_exclusive_group()
    question_source.add_argument(
        "--questions", help="JSON array of shared question/choices objects"
    )
    question_source.add_argument("--questions-file", type=Path)
    command.add_argument("--recursive", action="store_true")
    command.add_argument("--sample-interval", type=float)
    command.add_argument("--max-frames", type=int)
    command.add_argument("--max-total-frames", type=int)
    command.add_argument("--max-files", type=int)
    command.add_argument("--max-decisions", type=int)
    args = parser.parse_args()
    worker = None
    try:
        payload = {}
        if args.command == "batch":
            from .contracts import BatchRequest

            payload = json.loads(args.manifest.read_text()) if args.manifest else {}
            if not isinstance(payload, dict):
                raise ValueError("Batch manifest must be a JSON object")
            for key in (
                "folder",
                "files",
                "sample_interval",
                "max_frames",
                "max_total_frames",
                "max_files",
                "max_decisions",
            ):
                if getattr(args, key) is not None:
                    payload[key] = getattr(args, key)
            if args.recursive:
                payload["recursive"] = True
            if args.questions or args.questions_file:
                payload["questions"] = json.loads(
                    args.questions_file.read_text() if args.questions_file else args.questions
                )
            payload = BatchRequest(**payload).model_dump()
        else:
            payload["path"] = args.path
        if args.command == "inspect":
            payload["questions"] = json.loads(args.questions)
        elif args.command in ("image", "video"):
            payload.update(question=args.question, choices=args.choices)
        if args.command == "video":
            payload.update(sample_interval=args.sample_interval, max_frames=args.max_frames)
        operation = {
            "image": "classify_image",
            "inspect": "inspect_image",
            "video": "analyze_video",
            "batch": "analyze_batch",
        }[args.command]
        if args.url:
            from .client import Client

            target = Client(args.url)
        else:
            settings = load_settings()
            worker = target = EngineWorker(
                args.model or settings.get("model"), roots=args.root or settings["roots"]
            )
        print(json.dumps(target.call(operation, **payload), indent=2, allow_nan=False))
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        parser.exit(1, f"{exc}\n")
    finally:
        if worker:
            worker.close()


if __name__ == "__main__":
    main()
