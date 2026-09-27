from pydantic import BaseModel
from typing import Optional

class EventIn(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    registration_start: Optional[str] = None
    registration_close: Optional[str] = None
    event_start: Optional[str] = None
    event_end: Optional[str] = None
    submissions_open: Optional[str] = None
    submissions_close: Optional[str] = None
    gallery_visibility: Optional[str] = None

class TrackIn(BaseModel):
    name: str

class PrizeIn(BaseModel):
    name: str
    description: Optional[str] = None
    value_desc: Optional[str] = None
    track_id: Optional[str] = None
    display_order: int = 0

class RegistrationForm(BaseModel):
    fullName: str
    email: str
    phone: str
    age: int
    degree: str
    yearOfStudy: str
    institution: str
    category: str
    tshirtSize: Optional[str] = ""
    dietaryRestrictions: Optional[str] = ""
