from pydantic import BaseModel, HttpUrl, validator
from typing import Optional

def validate_url_scheme(url: Optional[str]) -> Optional[str]:
    if not url:
        return url
    if not (url.startswith("http://") or url.startswith("https://")):
        return f"https://{url}"
    return url

class ProjectCreate(BaseModel):
    team_id: str
    event_id: str
    track_id: str
    title: str
    summary: Optional[str] = ""
    description: Optional[str] = None
    repo_url: Optional[str] = None
    demo_url: Optional[str] = None
    live_url: Optional[str] = None
    thumbnail_url: Optional[str] = None

    _validate_repo_url = validator('repo_url', allow_reuse=True)(validate_url_scheme)
    _validate_demo_url = validator('demo_url', allow_reuse=True)(validate_url_scheme)
    _validate_live_url = validator('live_url', allow_reuse=True)(validate_url_scheme)

class ProjectUpdate(BaseModel):
    track_id: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    repo_url: Optional[str] = None
    demo_url: Optional[str] = None
    live_url: Optional[str] = None
    thumbnail_url: Optional[str] = None

    _validate_repo_url = validator('repo_url', allow_reuse=True)(validate_url_scheme)
    _validate_demo_url = validator('demo_url', allow_reuse=True)(validate_url_scheme)
    _validate_live_url = validator('live_url', allow_reuse=True)(validate_url_scheme)

class VisibilityUpdate(BaseModel):
    visible: bool
