from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class ProjectFieldSetup(BaseModel):
    field_ids: list[str] = Field(min_length=1)


class ProjectVideoAdd(BaseModel):
    video_id: str = Field(min_length=5, max_length=64)


class ProjectFieldOut(BaseModel):
    field_id: str
    enabled: bool


class ProjectVideoOut(BaseModel):
    video_id: str
    added_at: datetime


class ProjectOut(BaseModel):
    id: str
    name: str
    fields: list[ProjectFieldOut]
    videos: list[ProjectVideoOut]
    created_at: datetime


class RunOut(BaseModel):
    id: str
    project_id: str
    video_id: str
    status: str
    fetched_count: int
    new_count: int
    changed_count: int
    existing_count: int
    created_at: datetime


class ProjectAnalyticsOut(BaseModel):
    project_id: str
    video_count: int
    comment_count: int
    aggregate: dict[str, Any]
    coverage: dict[str, dict[str, float]]


class ProjectVideoInsightOut(BaseModel):
    project_id: str
    video_id: str
    comment_count: int
    status: str
    aggregate: dict[str, Any]
    coverage: dict[str, dict[str, float]]
    sample_records: list[dict[str, Any]]
