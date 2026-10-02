"""Small in-memory TTL + LRU cache for upstream JSON. Failures are never cached; 'not found' only briefly."""
from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable

MISS = object()
NOT_FOUND = object()  # marker for a cached 404


class TTLCache:
    def __init__(self, ttl: float = 3600.0, maxsize: int = 1024, clock: Callable[[], float] = time.monotonic):
        self.ttl, self.maxsize, self._clock = ttl, maxsize, clock
        self._data: OrderedDict = OrderedDict()

    @property
    def enabled(self) -> bool:
        return self.ttl > 0 and self.maxsize > 0

    def get(self, key):
        if not self.enabled or key not in self._data:
            return MISS
        expires, value = self._data[key]
        if self._clock() >= expires:
            del self._data[key]
            return MISS
        self._data.move_to_end(key)
        return value

    def set(self, key, value, ttl: float | None = None) -> None:
        if not self.enabled:
            return
        self._data[key] = (self._clock() + (self.ttl if ttl is None else ttl), value)
        self._data.move_to_end(key)
        while len(self._data) > self.maxsize:
            self._data.popitem(last=False)

    def __len__(self) -> int:
        return len(self._data)
