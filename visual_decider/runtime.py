"""Transport-neutral serialized engine lifecycle; no HTTP/MCP dependencies."""

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

    def _call(self, operation, payload):
        if self._engine is None:
            self._engine = self._factory()
        if operation == "health":
            return self._engine.info()
        if operation not in {"classify_image", "inspect_image", "analyze_video", "analyze_batch"}:
            raise ValueError("Unknown engine operation")
        args = dict(payload)
        path = args.pop("path", None)
        policy = args.pop("policy", None)
        args["policy"] = DecisionPolicy(**(policy or {}))
        if operation == "analyze_batch":
            return self._engine.analyze_batch(**args)
        return getattr(self._engine, operation)(path, **args)

    def submit(self, operation, **payload):
        if not self._slots.acquire(blocking=False):
            raise QueueFullError("Inference queue is full")
        try:
            future = self._executor.submit(self._call, operation, payload)
        except BaseException:
            self._slots.release()
            raise
        future.add_done_callback(lambda _: self._slots.release())
        return future

    def call(self, operation, **payload):
        return self.submit(operation, **payload).result()

    def close(self):
        self._executor.shutdown(wait=True, cancel_futures=True)
