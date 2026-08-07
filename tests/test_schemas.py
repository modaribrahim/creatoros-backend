import pytest
from pydantic import ValidationError

from app.schemas.field import FieldOut
from app.schemas.job import JobStatus
from app.schemas.project import (
    ProjectCreate,
    ProjectFieldSetup,
    ProjectOut,
    ProjectVideoAdd,
    RunOut,
)


def test_project_create_requires_name():
    assert ProjectCreate(name="Launch").name == "Launch"
    with pytest.raises(ValidationError):
        ProjectCreate(name="")


def test_project_video_add_requires_length():
    assert ProjectVideoAdd(video_id="dQw4w9WgXcQ").video_id == "dQw4w9WgXcQ"
    with pytest.raises(ValidationError):
        ProjectVideoAdd(video_id="ab")


def test_project_field_setup_rejects_empty():
    assert ProjectFieldSetup(field_ids=["intent"]).field_ids == ["intent"]
    with pytest.raises(ValidationError):
        ProjectFieldSetup(field_ids=[])


def test_job_status_optional_error():
    job = JobStatus(job_id="j1", video_id="v1", status="running")
    assert job.error is None


def test_field_out_default_options():
    field = FieldOut(id="intent", name="Intent", type="enum", enabled=True)
    assert field.options == []


def test_run_out_counts():
    run = RunOut(
        id="r1",
        project_id="p1",
        video_id="v1",
        status="completed",
        fetched_count=100,
        new_count=10,
        changed_count=2,
        existing_count=88,
        created_at="2026-08-06T00:00:00Z",
    )
    assert run.new_count + run.changed_count + run.existing_count == run.fetched_count


def test_project_out_fields_and_videos():
    project = ProjectOut(
        id="p1",
        name="Launch",
        fields=[],
        videos=[],
        created_at="2026-08-06T00:00:00Z",
    )
    assert project.videos == []
