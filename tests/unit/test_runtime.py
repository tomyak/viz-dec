from threading import Event, get_ident

import pytest

from visual_decider.runtime import EngineWorker, QueueFullError


class Clock:
    now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def test_lazy_single_thread_and_bounded_queue():
    entered, release = Event(), Event()
    threads = []

    class Engine:
        def __init__(self):
            threads.append(get_ident())

        def info(self):
            threads.append(get_ident())
            entered.set()
            assert release.wait(5)
            return {"ready": True}

    worker = EngineWorker(factory=Engine, max_pending=1)
    try:
        assert not threads
        first = worker.submit("health")
        assert entered.wait(5)
        with pytest.raises(QueueFullError):
            worker.submit("health")
        # Running work cannot be cancelled to reclaim a slot prematurely.
        assert not first.cancel()
        release.set()
        assert first.result(5)["ready"]
        assert worker.call("health")["ready"]
        assert len(set(threads)) == 1 and threads[0] != get_ident()
    finally:
        release.set()
        worker.close()


def test_failed_initialization_can_retry():
    attempts = []

    def factory():
        attempts.append(1)
        raise FileNotFoundError("missing model")

    worker = EngineWorker(factory=factory, max_pending=1)
    try:
        for _ in range(2):
            with pytest.raises(FileNotFoundError):
                worker.call("health")
        assert len(attempts) == 2
    finally:
        worker.close()


def test_cold_and_queued_requests_charge_model_loading_once(monkeypatch):
    from visual_decider import runtime

    clock = Clock()
    monkeypatch.setattr(runtime.time, "perf_counter", clock)
    entered, release = Event(), Event()
    underlying_result = {"winner": "Yes"}

    class Engine:
        def __init__(self):
            entered.set()
            assert release.wait(5)
            clock.advance(0.5)

        def classify_image(self, path, **kwargs):
            clock.advance(0.2)
            return underlying_result

    worker = EngineWorker(factory=Engine)
    try:
        cold = worker.submit("classify_image", path="test.png")
        assert entered.wait(5)
        queued = worker.submit("classify_image", path="test.png")
        release.set()
        first, second = cold.result(5), queued.result(5)
        assert first["model_cached"] is False
        assert first["timing"] == pytest.approx(
            {
                "queue_ms": 0,
                "model_load_ms": 500,
                "execution_ms": 200,
                "total_ms": 700,
            }
        )
        assert second["model_cached"] is True
        assert second["timing"] == pytest.approx(
            {
                "queue_ms": 700,
                "model_load_ms": 0,
                "execution_ms": 200,
                "total_ms": 900,
            }
        )
        assert underlying_result == {"winner": "Yes"}
    finally:
        release.set()
        worker.close()


@pytest.mark.parametrize(
    "operation",
    [
        "classify_image",
        "inspect_image",
        "analyze_video",
        "analyze_batch",
        "model_health",
    ],
)
def test_every_operation_has_request_timings_and_reuses_model(operation, monkeypatch):
    from visual_decider import runtime

    clock = Clock()
    monkeypatch.setattr(runtime.time, "perf_counter", clock)

    class Engine:
        def __init__(self):
            clock.advance(0.5)

        def execute(self, *args, **kwargs):
            clock.advance(0.25)
            return {"status": "ok"}

        classify_image = inspect_image = analyze_video = analyze_batch = model_health = execute

    worker = EngineWorker(factory=Engine)
    try:
        cold = worker.call(operation, path="test.png")
        warm = worker.call(operation, path="test.png")
        assert not cold["model_cached"] and warm["model_cached"]
        assert cold["timing"]["model_load_ms"] == 500
        assert warm["timing"]["model_load_ms"] == 0
        for result in (cold, warm):
            timing = result["timing"]
            assert timing["execution_ms"] == 250
            assert timing["total_ms"] == sum(
                timing[k] for k in ("queue_ms", "model_load_ms", "execution_ms")
            )
    finally:
        worker.close()


def test_invalid_operation_does_not_load_model():
    worker = EngineWorker(factory=lambda: pytest.fail("Must not load"))
    try:
        with pytest.raises(ValueError, match="Unknown"):
            worker.call("unknown")
    finally:
        worker.close()
