from pydantic import BaseModel, Field, field_validator
from typing import Optional

class EventIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    slug: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=5000)
    registration_start: Optional[str] = None
    registration_close: Optional[str] = None
    event_start: Optional[str] = None
    event_end: Optional[str] = None
    submissions_open: Optional[str] = None
    submissions_close: Optional[str] = None
    gallery_visibility: Optional[str] = None
    timezone: Optional[str] = Field(default=None, max_length=64)
    certificates_enabled: Optional[bool] = None

class TrackIn(BaseModel):
    name: str = Field(max_length=100)

class PrizeIn(BaseModel):
    name: str = Field(max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    value_desc: Optional[str] = Field(default=None, max_length=500)
    track_id: Optional[str] = None
    display_order: int = Field(default=0, ge=-1000000, le=1000000)

class RegistrationForm(BaseModel):
    fullName: str = Field(max_length=200)
    email: str = Field(max_length=320)
    phone: str = Field(max_length=40)
    age: int = Field(ge=1, le=150)
    degree: str = Field(max_length=100)
    yearOfStudy: str = Field(max_length=50)
    institution: str = Field(max_length=300)
    category: str = Field(default="", max_length=100)
    tshirtSize: Optional[str] = Field(default="", max_length=10)
    dietaryRestrictions: Optional[str] = Field(default="", max_length=500)

class OrganizerAssignIn(BaseModel):
    """Identify the account to add. Email is what the console sends; user_id
    is accepted for API callers. Exactly one is required."""
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

FIELD_TYPES = ("text", "textarea", "number", "url", "select")

class FormFieldIn(BaseModel):
    label: str = Field(max_length=200)
    field_type: str = "text"
    required: bool = False
    options: list[str] = Field(default_factory=list)

    @field_validator("field_type")
    @classmethod
    def _type(cls, v):
        v = (v or "").lower()
        if v not in FIELD_TYPES:
            raise ValueError(f"field_type must be one of {', '.join(FIELD_TYPES)}")
        return v

    @field_validator("options")
    @classmethod
    def _options(cls, v, info):
        opts = [str(o).strip() for o in (v or []) if str(o).strip()][:50]
        if info.data.get("field_type") == "select" and not opts:
            raise ValueError("select fields need at least one option")
        return opts
