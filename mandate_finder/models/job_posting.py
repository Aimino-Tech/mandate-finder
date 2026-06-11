import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class EmploymentType(str, enum.Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    TEMPORARY = "temporary"
    INTERNSHIP = "internship"
    MINI_JOB = "mini_job"
    TRAINEE = "trainee"
    OTHER = "other"


class JobPosting(Base):
    __tablename__ = "job_postings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ba_job_id = Column(String(128), unique=True, nullable=False, index=True)
    title = Column(String(512), nullable=False)
    company_name = Column(String(256), nullable=False)
    location_city = Column(String(128))
    location_state = Column(String(128))
    description = Column(Text)
    occupation_code = Column(String(32), index=True)
    employment_type: Column[Enum] = Column(Enum(EmploymentType), default=EmploymentType.OTHER)
    source_url = Column(String(1024))
    posted_at = Column(DateTime(timezone=True))
    last_modified = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
