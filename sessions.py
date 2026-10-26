"""Sessions de navigateur éphémères. Aucun stockage sur disque."""
import secrets
import threading
import time


class Sessions:
    def __init__(self, factory, ttl=120, clock=time.monotonic):
        self.factory, self.ttl, self.clock = factory, ttl, clock
        self.lock = threading.RLock()
        self.items = {}

    def open(self):
        self.expire()
        with self.lock:
            if len(self.items) >= 8:
                raise ValueError('Ferme un onglet Duo avant d’en ouvrir un autre.')
            key = secrets.token_urlsafe(32)
            self.items[key] = (self.factory(), self.clock())
            return key

    def get(self, key):
        self.expire()
        with self.lock:
            item = self.items.get(key)
            if item is None:
                return None
            discussion, unused = item
            self.items[key] = (discussion, self.clock())
            return discussion

    def end(self, key):
        with self.lock:
            item = self.items.pop(key, None)
        if item:
            item[0].dispose()

    def expire(self):
        with self.lock:
            stale = [key for key, (_, seen) in self.items.items() if self.clock() - seen >= self.ttl]
            for key in stale:
                self.end(key)

    def close(self):
        with self.lock:
            for key in list(self.items):
                self.end(key)

    def reap(self):
        while True:
            time.sleep(5)
            self.expire()
