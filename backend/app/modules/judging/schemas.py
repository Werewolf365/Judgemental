from pydantic import BaseModel, Field, field_validator
from typing import Optional


class CriterionIn(BaseModel):
    name: str = Field(max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    weight: Optional[float] = None
    display_order: int = Field(default=0, ge=-1000000, le=1000000)

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("Criterion name is required")
        return v

    @field_validator("weight")
    @classmethod
    def _weight(cls, v):
        if v is None:
            return None
        if not (0 < v <= 100):
            raise ValueError("weight must be more than 0 and at most 100")
        return v


class JudgingConfigIn(BaseModel):
    judging_open: Optional[str] = None
    judging_close: Optional[str] = None
    judges_per_project: Optional[int] = Field(default=None, ge=1, le=10)
    rolling_judging: Optional[bool] = None


class JudgeAssignIn(BaseModel):
    """Identify the account to roster. Exactly one of email/user_id."""
    email: Optional[str] = Field(default="", max_length=320)
    user_id: Optional[str] = Field(default=None, max_length=64)

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        v = (v or "").strip().lower()
        if v and ("@" not in v or v.startswith("@") or v.endswith("@")):
            raise ValueError("Enter a valid email address")
        return v

    @field_validator("user_id")
    @classmethod
    def _user_id(cls, v):
        return (v or "").strip() or None
