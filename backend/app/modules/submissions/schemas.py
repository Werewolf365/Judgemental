from pydantic import BaseModel, HttpUrl, validator, Field
from typing import Optional

URL_MAX = 2000

def validate_url_scheme(url: Optional[str]) -> Optional[str]:
    if not url:
        return url
    if len(url) > URL_MAX:
        raise ValueError("URL is too long")
    if not (url.startswith("http://") or url.startswith("https://")):
        return f"https://{url}"
    return url

class ProjectCreate(BaseModel):
    team_id: str = Field(max_length=100)
    event_id: str = Field(max_length=100)
    track_id: str = Field(max_length=100)
    title: str = Field(max_length=200)
    summary: Optional[str] = Field(default="", max_length=2000)
    description: Optional[str] = Field(default=None, max_length=10000)
    repo_url: Optional[str] = None
    demo_url: Optional[str] = None
    live_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    custom_data: Optional[dict] = Field(default=None)

    _validate_repo_url = validator('repo_url', allow_reuse=True)(validate_url_scheme)
    _validate_demo_url = validator('demo_url', allow_reuse=True)(validate_url_scheme)
    _validate_live_url = validator('live_url', allow_reuse=True)(validate_url_scheme)

class ProjectUpdate(BaseModel):
    track_id: Optional[str] = Field(default=None, max_length=100)
    title: Optional[str] = Field(default=None, max_length=200)
    summary: Optional[str] = Field(default=None, max_length=2000)
    description: Optional[str] = Field(default=None, max_length=10000)
    custom_data: Optional[dict] = Field(default=None)
    repo_url: Optional[str] = None
    demo_url: Optional[str] = None
    live_url: Optional[str] = None
    thumbnail_url: Optional[str] = None

    _validate_repo_url = validator('repo_url', allow_reuse=True)(validate_url_scheme)
    _validate_demo_url = validator('demo_url', allow_reuse=True)(validate_url_scheme)
    _validate_live_url = validator('live_url', allow_reuse=True)(validate_url_scheme)

class VisibilityUpdate(BaseModel):
    visible: bool
