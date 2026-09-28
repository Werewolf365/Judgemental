from pydantic import BaseModel, field_validator
from typing import Optional

MAX_PASSWORD_LEN = 128

def _pw_ok(v: str) -> str:
    if len(v) < 8:
        raise ValueError("password must be at least 8 characters")
    if len(v) > MAX_PASSWORD_LEN:
        raise ValueError("password is too long")
    return v

def _email_ok(v: str) -> str:
    v = v.strip()
    # Local-first: accept reserved/test domains (local.test, example.org).
    # email-validator rejects those, so validate shape only.
    if "@" not in v or "." not in v.split("@")[-1]:
        raise ValueError("Enter a valid email address.")
    return v

class RegisterIn(BaseModel):
    email: str
    password: str
    display_name: str = ""
    role: str = "PARTICIPANT"

    @field_validator("email")
    @classmethod
    def em(cls, v):
        return _email_ok(v)

    @field_validator("password")
    @classmethod
    def pw(cls, v):
        return _pw_ok(v)

class LoginIn(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def em(cls, v):
        return _email_ok(v)

    @field_validator("password")
    @classmethod
    def pw(cls, v):
        return _pw_ok(v)

class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    role: str
