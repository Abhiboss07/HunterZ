"""Database models and dataclasses for HunterZ."""
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Return current UTC datetime (modern Python 3.12+ safe)."""
    return datetime.now(timezone.utc)


class JobModel(BaseModel):
    id: Optional[int] = None
    external_id: str
    title: str
    company: str
    location: str
    url: str
    source: str  # "greenhouse", "lever", "ashby", "linkedin", "startup_portal"
    posted_at: datetime
    discovered_at: datetime = Field(default_factory=utc_now)
    description: Optional[str] = ""
    match_score: int = 0
    status: str = "NEW"  # "NEW", "MATCHED", "APPLIED", "IGNORED", "REJECTED"


class ApplicationModel(BaseModel):
    id: Optional[int] = None
    job_id: int
    company: str
    title: str
    url: str
    resume_pdf_path: str
    resume_tex_path: Optional[str] = None
    applied_at: datetime = Field(default_factory=utc_now)
    status: str = "SUBMITTED"  # "SUBMITTED", "INTERVIEW", "REJECTED", "OFFER"
    submission_method: str = "DIRECT_REST"  # "DIRECT_REST", "BROWSER", "MANUAL"
    response_notes: Optional[str] = None
    rejection_reason: Optional[str] = None
    tailored_bio: Optional[str] = None
    provided_details: Optional[str] = None


class DirectOutreachModel(BaseModel):
    id: Optional[int] = None
    job_id: int
    company: str
    title: str
    recruiter_email: str
    email_subject: str
    email_body: str
    resume_pdf_path: str
    sent_at: datetime = Field(default_factory=utc_now)
    status: str = "SENT"  # "SENT", "OPENED", "REPLIED"
    notes: Optional[str] = None
