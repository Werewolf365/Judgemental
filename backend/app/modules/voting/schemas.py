from typing import Optional
from pydantic import BaseModel, Field, field_validator

from app.modules.voting.service import COMMENT_VIS, VOTING_MODES


class VotingSettingsIn(BaseModel):
    voting_enabled: Optional[bool] = None
    voting_close: Optional[str] = None
    voting_mode: Optional[str] = None
    comments_visibility: Optional[str] = None

    @field_validator("voting_mode")
    @classmethod
    def _mode(cls, v):
        if v is None:
            return v
        v = v.lower()
        if v not in VOTING_MODES:
            raise ValueError(f"voting_mode must be one of {', '.join(VOTING_MODES)}")
        return v

    @field_validator("comments_visibility")
    @classmethod
    def _vis(cls, v):
        if v is None:
            return v
        v = v.lower()
        if v not in COMMENT_VIS:
            raise ValueError(f"comments_visibility must be one of {', '.join(COMMENT_VIS)}")
        return v


class BallotIn(BaseModel):
    project_id: str = Field(max_length=100)
    votes: int = Field(ge=0, le=10)
    voter_id: Optional[str] = Field(default=None, max_length=64)
    email: Optional[str] = Field(default=None, max_length=320)


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
