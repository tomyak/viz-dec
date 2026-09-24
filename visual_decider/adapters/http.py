"""Loopback-only persistent inference process with a single GPU worker."""

import argparse
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

from ..runtime import EngineWorker, QueueFullError
from .contracts import BatchRequest, ClassifyRequest, HealthRequest, InspectRequest, VideoRequest


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > 65536:
                return await JSONResponse({"detail": "Request exceeds 64 KiB"}, status_code=413)(
                    scope, receive, send
                )
            if not message.get("more_body"):
                break
        sent = False

        async def replay():
            nonlocal sent
            if sent:
                return await receive()
            sent = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)


def create_app(model=None, roots=None, analyzer_factory=None):
    @asynccontextmanager
    async def lifespan(app):
        worker = EngineWorker(
            model, roots=roots if roots is not None else [Path.cwd()], factory=analyzer_factory
        )
        app.state.worker = worker
        try:
            app.state.model_info = await asyncio.wrap_future(worker.submit("health"))
            yield
        finally:
            worker.close()

    app = FastAPI(title="Local Visual Decision Engine", lifespan=lifespan)
    app.add_middleware(BodyLimit)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])

    @app.middleware("http")
    async def deny_browser_origins(request: Request, call_next):
        if request.headers.get("origin"):
            return JSONResponse({"detail": "Browser-origin requests are disabled"}, status_code=403)
        return await call_next(request)

    async def submit(operation, request):
        try:
            # Shield the concurrent future: a disconnected client does not free an occupied slot.
            future = app.state.worker.submit(operation, **request.model_dump())
            return await asyncio.shield(asyncio.wrap_future(future))
        except QueueFullError as exc:
            raise HTTPException(503, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except (ValueError, KeyError) as exc:
            raise HTTPException(400, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(500, f"Inference failed: {exc}") from exc

    @app.get("/health")
    async def health():
        # Liveness must not wait behind a long video job.
        return {"status": "ready", **app.state.model_info}

    @app.post("/classify_image")
    async def classify_image(request: ClassifyRequest):
        return await submit("classify_image", request)

    @app.post("/model_health")
    async def model_health(request: HealthRequest):
        return await submit("model_health", request)

    @app.post("/inspect_image")
    async def inspect_image(request: InspectRequest):
        return await submit("inspect_image", request)

    @app.post("/analyze_video")
    async def analyze_video(request: VideoRequest):
        return await submit("analyze_video", request)

    @app.post("/analyze_batch")
    async def analyze_batch(request: BatchRequest):
        return await submit("analyze_batch", request)

    return app


def main():
    import uvicorn

    from .settings import load_settings

    p = argparse.ArgumentParser()
    p.add_argument("--model")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument(
        "--root", action="append", help="Allowed local file root; defaults to installed settings"
    )
    args = p.parse_args()
    settings = load_settings()
    uvicorn.run(
        create_app(args.model or settings.get("model"), args.root or settings["roots"]),
        host="127.0.0.1",
        port=args.port,
        workers=1,
    )


if __name__ == "__main__":
    main()
