"""Agent-neutral stdio MCP adapter. Defaults to the installation's shared model process."""

import argparse
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from ..runtime import EngineWorker
from .contracts import (
    BatchRequest,
    ClassifyRequest,
    HealthRequest,
    InspectRequest,
    MediaItem,
    Policy,
    Question,
    VideoRequest,
)
from .settings import load_settings


def create_server(client=None, *, model=None, roots=None):
    @asynccontextmanager
    async def lifespan(server):
        try:
            yield {}
        finally:
            if client is None:
                target.close()

    target = client or EngineWorker(model, roots=roots)
    server = MCPServer("visual-decider", lifespan=lifespan)

    def call(operation, request):
        try:
            return target.call(operation, **request.model_dump())
        except (OSError, ValueError, RuntimeError) as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(structured_output=True)
    def classify_image(
        path: str, question: str, choices: list[str], policy: Policy | None = None
    ) -> dict[str, Any]:
        """Score exactly the supplied question/choices on a local image. Not calibrated probability."""
        return call(
            "classify_image",
            ClassifyRequest(
                path=path, question=question, choices=choices, policy=policy or Policy()
            ),
        )

    @server.tool(structured_output=True)
    def inspect_image(
        path: str, questions: list[Question], policy: Policy | None = None
    ) -> dict[str, Any]:
        """Score the supplied questions on one local image, reusing its visual features."""
        return call(
            "inspect_image",
            InspectRequest(path=path, questions=questions, policy=policy or Policy()),
        )

    @server.tool(structured_output=True)
    def analyze_video(
        path: str,
        question: str,
        choices: list[str],
        sample_interval: float = 1.0,
        max_frames: int = 300,
        suppress_duplicates: bool = False,
        policy: Policy | None = None,
    ) -> dict[str, Any]:
        """Apply the exact question to sampled frames. This is not a temporal video-model judgment."""
        return call(
            "analyze_video",
            VideoRequest(
                path=path,
                question=question,
                choices=choices,
                sample_interval=sample_interval,
                max_frames=max_frames,
                suppress_duplicates=suppress_duplicates,
                policy=policy or Policy(),
            ),
        )

    @server.tool(structured_output=True)
    def analyze_batch(
        files: list[str | MediaItem] | None = None,
        folder: str | None = None,
        questions: list[Question] | None = None,
        recursive: bool = False,
        sample_interval: float = 1.0,
        max_frames: int = 300,
        max_total_frames: int = 1000,
        max_files: int = 128,
        max_decisions: int = 4096,
        policy: Policy | None = None,
    ) -> dict[str, Any]:
        """Batch a folder or file list with shared/per-file questions. Shares visual encodes and decisions;
        decodes each video once for all questions. Returns ordered per-file results/errors and budgets.
        """
        return call(
            "analyze_batch",
            BatchRequest(
                files=files,
                folder=folder,
                questions=questions,
                recursive=recursive,
                sample_interval=sample_interval,
                max_frames=max_frames,
                max_total_frames=max_total_frames,
                max_files=max_files,
                max_decisions=max_decisions,
                policy=policy or Policy(),
            ),
        )

    @server.tool(structured_output=True)
    def model_health() -> dict[str, Any]:
        """Load/reuse the model and test fresh vision/scoring on two synthetic images."""
        return call("model_health", HealthRequest())

    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="Use an already-running loopback HTTP service instead")
    parser.add_argument("--model")
    parser.add_argument("--root", action="append")
    parser.add_argument(
        "--in-process", action="store_true", help="Load a separate model in this process"
    )
    args = parser.parse_args()
    settings = load_settings()
    if args.url:
        from .client import Client

        server = create_server(Client(args.url))
    elif args.in_process:
        server = create_server(
            model=args.model or settings.get("model"), roots=args.root or settings["roots"]
        )
    else:
        from .shared import SharedClient

        server = create_server(SharedClient(model=args.model, roots=args.root))
    server.run()


if __name__ == "__main__":
    main()
