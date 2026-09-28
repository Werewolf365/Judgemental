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


class ManualAssignIn(BaseModel):
    """Organizer-picked judge→project assignment from the existing pool."""
    project_id: str = Field(max_length=64)
    judge_user_id: str = Field(max_length=64)

    @field_validator("project_id", "judge_user_id")
    @classmethod
    def _nonempty(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("project_id and judge_user_id are both required")
        return v


class RankSwapIn(BaseModel):
    """Interchange two ranks in the latest Bayesian scoring run."""
    project_a_id: str = Field(max_length=64)
    project_b_id: str = Field(max_length=64)
    reason: Optional[str] = Field(default=None, max_length=500)

    @field_validator("project_a_id", "project_b_id")
    @classmethod
    def _nonempty(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("both project ids are required")
        return v

    @field_validator("reason")
    @classmethod
    def _reason(cls, v):
        return (v or "").strip() or None
