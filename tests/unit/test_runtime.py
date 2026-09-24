from threading import Event, get_ident

import pytest

from visual_decider.runtime import EngineWorker, QueueFullError


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
