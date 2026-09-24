"""Wall-clock timing for operations on an already constructed analyzer."""

import time
from functools import wraps


def timed_execution(operation):
    @wraps(operation)
    def measured(*args, **kwargs):
        start = time.perf_counter()
        result = operation(*args, **kwargs)
        elapsed = 1000 * (time.perf_counter() - start)
        # Direct Python callers load the model before calling the analyzer.
        # EngineWorker replaces these fields with its queue/load/request timings.
        return {
            **result,
            "model_cached": True,
            "timing": {
                "queue_ms": 0.0,
                "model_load_ms": 0.0,
                "execution_ms": elapsed,
                "total_ms": elapsed,
            },
        }

    return measured
