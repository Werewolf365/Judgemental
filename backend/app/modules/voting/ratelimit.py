"""In-memory token-bucket rate limits (T3 anti-abuse, first layer).

Why in-memory: the repo bans extra services, and stock uvicorn runs a
single worker — one dict is the whole limiter. If workers are ever added,
each gets its own budget (fail-open direction: slightly generous, never
blocking legit traffic), and a shared store becomes the upgrade path.

Budgets are deliberately generous: they exist to blunt floods and scripts,
not to ration humans. Every refusal is audited (vote.rate_limited /
comment.rate_limited) so organizers see abuse attempts in their audit view.
Env overrides: VOTE_PER_MIN (default 30), COMMENT_PER_MIN (default 20).
"""
import os
import time

_buckets: dict[tuple[str, str], list[float]] = {}


def _budget(route: str) -> tuple[int, int]:
    if route == "comment":
        per_min = int(os.getenv("COMMENT_PER_MIN", "20"))
    else:
        per_min = int(os.getenv("VOTE_PER_MIN", "30"))
    return max(1, per_min), 60


def check(client_key: str, route: str, now: float | None = None) -> tuple[bool, int]:
    """Consume one token. Returns (allowed, retry_after_seconds)."""
    now = now if now is not None else time.monotonic()
    per_min, window = _budget(route)
    key = (client_key or "anon", route)
    hits = [t for t in _buckets.get(key, []) if t > now - window]
    if len(hits) >= per_min:
        retry = max(1, int(hits[0] + window - now))
        _buckets[key] = hits
        return False, retry
    hits.append(now)
    _buckets[key] = hits
    return True, 0


def reset() -> None:
    """Tests only."""
    _buckets.clear()
