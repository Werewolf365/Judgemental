import os
from datetime import datetime, timezone

def utcnow() -> datetime:
    fake = os.getenv("FAKE_NOW_UTC")
    if fake:
        try:
            dt = datetime.fromisoformat(fake.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass
    return datetime.now(timezone.utc)
