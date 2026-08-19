from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class JDParseResult(BaseModel):
    title: str | None = None
    category: Literal['technical', 'general', 'consulting', 'sales', 'planning', 'design', 'other'] | None = None
    category_other: str | None = None
    department: str | None = None
    location: str | None = None
    work_mode: Literal['onsite', 'hybrid', 'remote', 'unknown'] | None = None
    employment_type: Literal['full_time', 'part_time', 'contract', 'internship', 'temporary', 'other'] | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: Literal['hourly', 'monthly', 'yearly'] | None = None
    application_deadline: date | None = None
    description: str | None = None
    requirements: str | None = None
    benefits: str | None = None
    skills: list[str] = Field(default_factory=list)
    experience_requirements: list[str] = Field(default_factory=list)
    education_requirements: list[str] = Field(default_factory=list)
    language_requirements: list[str] = Field(default_factory=list)
    preferred_qualifications: list[str] = Field(default_factory=list)
    confidence: dict[str, float] = Field(default_factory=dict)
    unknown_fields: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    requirement: str
    evidence: str


class JobMatchResult(BaseModel):
    score: int = Field(ge=0, le=100)
    summary: str
    score_reasoning: list[str] = Field(default_factory=list)
    strengths: list[EvidenceItem] = Field(default_factory=list)
    gaps: list[EvidenceItem] = Field(default_factory=list)
    resume_highlights: list[str] = Field(default_factory=list)
    application_recommendation: str
    interview_preparation: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)


class EmailScheduleItem(BaseModel):
    title: str
    event_type: Literal['interview', 'call', 'assessment', 'briefing', 'follow_up', 'other'] = 'other'
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    timezone_name: str = 'Asia/Tokyo'
    location: str | None = None
    meeting_url: str | None = None
    participants: list[str] = Field(default_factory=list)
    summary: str | None = None
    evidence: str
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class EmailTodoItem(BaseModel):
    title: str
    action_type: Literal[
        'resume_submit', 'document_submit', 'assessment', 'form_fill',
        'email_reply', 'schedule_booking', 'follow_up', 'other',
    ] = 'other'
    due_at: datetime | None = None
    timezone_name: str = 'Asia/Tokyo'
    action_url: str | None = None
    notes: str | None = None
    evidence: str
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    is_urgent: bool = False
    is_optional: bool = False


class EmailScheduleResult(BaseModel):
    assistant_reply: str = ''
    assessment: Literal['action_found', 'no_action', 'schedule_found', 'no_schedule', 'needs_info'] = 'needs_info'
    schedule_candidates: list[EmailScheduleItem] = Field(max_length=8)
    todo_candidates: list[EmailTodoItem] = Field(max_length=8)
    candidates: list[EmailScheduleItem] = Field(default_factory=list, max_length=8)


class EmailAssistantResult(BaseModel):
    # Ollama 0.31 rejects string minLength/maxLength while compiling its JSON
    # grammar. Keep the wire schema portable and enforce the same rule after
    # generation with Pydantic instead.
    assistant_reply: str
    assessment: Literal['action_found', 'no_action', 'schedule_found', 'no_schedule', 'needs_info']
    schedule_candidates: list[EmailScheduleItem] = Field(max_length=8)
    todo_candidates: list[EmailTodoItem] = Field(max_length=8)
    candidates: list[EmailScheduleItem] = Field(default_factory=list, max_length=8)

    @field_validator('assistant_reply')
    @classmethod
    def validate_assistant_reply(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('assistant_reply must not be empty')
        if len(value) > 3000:
            raise ValueError('assistant_reply must contain at most 3000 characters')
        return value
