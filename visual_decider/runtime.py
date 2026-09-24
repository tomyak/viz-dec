"""Transport-neutral serialized engine lifecycle; no HTTP/MCP dependencies."""

import time
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore

from .classifier import Analyzer
from .policy import DecisionPolicy


class QueueFullError(RuntimeError):
    pass


class EngineWorker:
    def __init__(self, model=None, roots=None, *, factory=None, max_pending=8):
        if not isinstance(max_pending, int) or isinstance(max_pending, bool) or max_pending < 1:
            raise ValueError("max_pending must be a positive integer")
        self._factory = factory or (lambda: Analyzer(model, roots=roots))
        self._engine = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="visual-decider")
        self._slots = BoundedSemaphore(max_pending)

    def _call(self, operation, payload, submitted_at):
        if operation not in {
            "health",
            "model_health",
            "classify_image",
            "inspect_image",
            "analyze_video",
            "analyze_batch",
        }:
            raise ValueError("Unknown engine operation")
        started = time.perf_counter()
        model_cached = self._engine is not None
        if self._engine is None:
            self._engine = self._factory()
        loaded = time.perf_counter() if not model_cached else started
        if operation == "health":
            # Internal startup/liveness metadata is not a measured inference request.
            return self._engine.info()
        if operation == "model_health":
            result = self._engine.model_health()
        else:
            args = dict(payload)
            path = args.pop("path", None)
            policy = args.pop("policy", None)
            args["policy"] = DecisionPolicy(**(policy or {}))
            result = (
                self._engine.analyze_batch(**args)
                if operation == "analyze_batch"
                else getattr(self._engine, operation)(path, **args)
            )
        finished = time.perf_counter()
        return {
            **result,
            "model_cached": model_cached,
            "timing": {
                "queue_ms": 1000 * (started - submitted_at),
                "model_load_ms": 1000 * (loaded - started),
                "execution_ms": 1000 * (finished - loaded),
                "total_ms": 1000 * (finished - submitted_at),
            },
        }

    def submit(self, operation, **payload):
        if not self._slots.acquire(blocking=False):
            raise QueueFullError("Inference queue is full")
        try:
            future = self._executor.submit(self._call, operation, payload, time.perf_counter())
        except BaseException:
            self._slots.release()
            raise
        future.add_done_callback(lambda _: self._slots.release())
        return future

    def call(self, operation, **payload):
        return self.submit(operation, **payload).result()

    def close(self):
        self._executor.shutdown(wait=True, cancel_futures=True)
