"""A tiny thread-safe in-memory store whose items expire when unused."""
import secrets
import threading
import time


class Store:
    def __init__(self, ttl, max_items, max_bytes):
        self.ttl = ttl                  # seconds an item may sit unused
        self.max_items = max_items
        self.max_bytes = max_bytes
        self._items = {}                # token -> {"value", "size", "touched"}
        self._lock = threading.Lock()

    def _purge(self, now):
        for token in [t for t, e in self._items.items() if now - e["touched"] > self.ttl]:
            del self._items[token]
        while self._items and (
            len(self._items) > self.max_items
            or sum(e["size"] for e in self._items.values()) > self.max_bytes
        ):
            del self._items[min(self._items, key=lambda t: self._items[t]["touched"])]

    def put(self, value, size):
        token = secrets.token_urlsafe(16)
        now = time.time()
        with self._lock:
            self._items[token] = {"value": value, "size": size, "touched": now}
            self._purge(now)
        return token

    def get(self, token):
        now = time.time()
        with self._lock:
            self._purge(now)
            entry = self._items.get(token) if isinstance(token, str) else None
            if entry is None:
                return None
            entry["touched"] = now      # using an item keeps it alive
            return entry["value"]
