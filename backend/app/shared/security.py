import hashlib
import secrets
from datetime import datetime, timezone
from argon2 import PasswordHasher

_ph = PasswordHasher()

def hash_password(pw: str) -> str:
    return _ph.hash(pw)

def verify_password(hash_: str, pw: str) -> bool:
    try:
        return _ph.verify(hash_, pw)
    except Exception:
        return False

def new_session_token() -> str:
    return secrets.token_urlsafe(32)

def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()

def utcnow() -> datetime:
    return datetime.now(timezone.utc)
