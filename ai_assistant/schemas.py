from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


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
