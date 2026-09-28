from pydantic import BaseModel
from typing import List, Optional

class EventOut(BaseModel):
    id: str
    slug: str
    name: str
    description: Optional[str]
    submissions_close: Optional[str]
    status: str

class TrackOut(BaseModel):
    id: str
    name: str

class PrizeOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    value_desc: Optional[str]

class EventDetailsOut(BaseModel):
    id: str
    slug: str
    name: str
    description: Optional[str]
    registration_start: Optional[str]
    registration_close: Optional[str]
    event_start: Optional[str]
    event_end: Optional[str]
    submissions_open: Optional[str]
    submissions_close: Optional[str]
    gallery_visibility: Optional[str] = "PUBLIC"
    voting_enabled: Optional[bool] = False
    voting_close: Optional[str] = None
    voting_mode: Optional[str] = "auth"

class EventResponse(BaseModel):
    event: EventDetailsOut
    tracks: List[TrackOut]
    prizes: List[PrizeOut]

class EventsListResponse(BaseModel):
    events: List[EventOut]

class ProjectGalleryOut(BaseModel):
    id: str
    title: str
    summary: str
    team: str
    team_id: str
    track: str
    track_id: str
    repo_url: Optional[str]
    submitted_at: Optional[str]

class ProjectsListResponse(BaseModel):
    projects: List[ProjectGalleryOut]
    page: int
    page_size: int
    total: int

class CustomFieldOut(BaseModel):
    label: str
    value: str

class ProjectDetailOut(BaseModel):
    id: str
    title: str
    summary: str
    description: Optional[str]
    team: Optional[str]
    members: List[str]
    track: Optional[str]
    repo_url: Optional[str]
    demo_url: Optional[str]
    custom_fields: List[CustomFieldOut] = []
    submitted_at: Optional[str]

class ProjectDetailResponse(BaseModel):
    project: ProjectDetailOut
