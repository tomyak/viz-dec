from collections import OrderedDict


class VisualCache:
    """Bounded LRU owned by one serialized analyzer; sessions store keys, not tensors."""

    def __init__(self, max_entries=4, max_bytes=256 * 1024 * 1024):
        if any(
            not isinstance(x, int) or isinstance(x, bool) or x < 0 for x in (max_entries, max_bytes)
        ):
            raise ValueError("Cache limits must be nonnegative")
        self.max_entries, self.max_bytes = max_entries, max_bytes
        self.entries = OrderedDict()
        self.bytes = self.hits = self.misses = 0

    def get(self, key):
        if key not in self.entries:
            self.misses += 1
            return None
        self.hits += 1
        self.entries.move_to_end(key)
        return self.entries[key][0]

    def put(self, key, value, size):
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ValueError("Cache size must be a nonnegative integer")
        if key in self.entries:
            self.bytes -= self.entries.pop(key)[1]
        if size > self.max_bytes or not self.max_entries:
            return
        while self.entries and (
            len(self.entries) >= self.max_entries or self.bytes + size > self.max_bytes
        ):
            self.bytes -= self.entries.popitem(last=False)[1][1]
        self.entries[key] = (value, size)
        self.bytes += size

    def clear(self):
        self.entries.clear()
        self.bytes = 0

    def info(self):
        return dict(entries=len(self.entries), bytes=self.bytes, hits=self.hits, misses=self.misses)
