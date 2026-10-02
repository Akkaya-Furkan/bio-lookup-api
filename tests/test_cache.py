from bio_lookup.cache import MISS, TTLCache


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_hit_then_expiry():
    clock = Clock()
    c = TTLCache(ttl=10, clock=clock)
    c.set("k", "v")
    assert c.get("k") == "v"
    clock.now = 9.9
    assert c.get("k") == "v"
    clock.now = 10.0
    assert c.get("k") is MISS
    assert len(c) == 0  # expired entries are dropped


def test_per_entry_ttl_overrides_default():
    clock = Clock()
    c = TTLCache(ttl=100, clock=clock)
    c.set("short", 1, ttl=5)
    clock.now = 6
    assert c.get("short") is MISS


def test_evicts_least_recently_used():
    c = TTLCache(ttl=100, maxsize=2)
    c.set("a", 1)
    c.set("b", 2)
    c.get("a")  # a is now fresher than b
    c.set("c", 3)
    assert c.get("b") is MISS and c.get("a") == 1 and c.get("c") == 3


def test_ttl_zero_disables_the_cache():
    c = TTLCache(ttl=0)
    c.set("k", "v")
    assert not c.enabled and c.get("k") is MISS and len(c) == 0
