import math

from cachetools import TTLCache

TTL_CACHE = TTLCache(maxsize=0, ttl=0)

def configure(app):
    relay_polling_interval = app.config.get('REALY_POLL_INT', 10)

    global TTL_CACHE

    TTL_CACHE = TTLCache(
        maxsize=256,
        ttl=math.floor(relay_polling_interval * 0.85))

    return app


