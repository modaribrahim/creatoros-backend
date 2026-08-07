import json
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import ConflictError, NotFoundError
from app.repositories.comments import CommentRepository
from app.repositories.projects import ProjectRepository
from app.schemas.job import JobStarted
from app.schemas.project import (
    ProjectAnalyticsOut,
    ProjectCreate,
    ProjectFieldOut,
    ProjectFieldSetup,
    ProjectOut,
    ProjectVideoAdd,
    ProjectVideoInsightOut,
    ProjectVideoOut,
    RunOut,
)
from app.schemas.search import SearchHit, SearchRequest, SearchResult
from app.services.aggregator import aggregate_records
from app.services.fields import get_fields
from app.services.jobs import analyze_project_video
from app.services.openrouter import embed
from app.services.search import generate_answer, generate_plan, validate_filters

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    repo = ProjectRepository(db)
    project = await repo.create_project(body.name, user["id"])
    return await _project_out(db, project.id, user["id"])


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    repo = ProjectRepository(db)
    projects = await repo.list_projects(user["id"])
    return [await _project_out(db, p.id, user["id"]) for p in projects]


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    return await _project_out(db, project_id, user["id"])


@router.put("/projects/{project_id}/fields", response_model=list[ProjectFieldOut])
async def setup_project_fields(
    project_id: str,
    body: ProjectFieldSetup,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    repo = ProjectRepository(db)
    project = await repo.get_project(project_id, user["id"])
    if not project:
        raise NotFoundError("project not found")
    if await repo.has_project_fields(project_id):
        raise ConflictError("project fields are locked after setup")
    catalog_ids = {f["id"] for f in await get_fields(db)}
    unknown = set(body.field_ids) - catalog_ids
    if unknown:
        raise NotFoundError(f"unknown fields: {sorted(unknown)}")
    await repo.set_project_fields(project_id, body.field_ids)
    ids = await repo.get_project_field_ids(project_id)
    return [ProjectFieldOut(field_id=fid, enabled=True) for fid in ids]


@router.post(
    "/projects/{project_id}/videos", response_model=JobStarted, status_code=201
)
async def add_project_video(
    project_id: str,
    body: ProjectVideoAdd,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    repo = ProjectRepository(db)
    project = await repo.get_project(project_id, user["id"])
    if not project:
        raise NotFoundError("project not found")
    if not await repo.has_project_fields(project_id):
        raise ConflictError("project fields must be configured first")
    if await repo.has_project_video(project_id, body.video_id):
        raise ConflictError(f"video {body.video_id} already exists in this project")
    await repo.add_project_video(project_id, body.video_id)

    comments_repo = CommentRepository(db)
    job_id = await comments_repo.create_job_pending_return_id(body.video_id, project_id)
    run = await repo.create_run(project_id, body.video_id, job_id)
    task = analyze_project_video.delay(project_id, body.video_id, job_id, run.id)
    return JobStarted(job_id=job_id, task_id=task.id)


@router.get("/projects/{project_id}/runs", response_model=list[RunOut])
async def project_runs(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    repo = ProjectRepository(db)
    if not await repo.get_project(project_id, user["id"]):
        raise NotFoundError("project not found")
    return await repo.get_project_runs(project_id)


@router.get(
    "/projects/{project_id}/videos/{video_id}/insights",
    response_model=ProjectVideoInsightOut,
)
async def project_video_insight(
    project_id: str,
    video_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    repo = ProjectRepository(db)
    if not await repo.get_project(project_id, user["id"]):
        raise NotFoundError("project not found")
    insight = await repo.get_insight(project_id, video_id)
    if not insight:
        raise NotFoundError("insight not found for this video in the project")

    records = await repo.get_records(project_id, video_id)
    field_ids = await repo.get_project_field_ids(project_id)
    coverage = _coverage(records, field_ids)

    return ProjectVideoInsightOut(
        project_id=insight.project_id,
        video_id=insight.video_id,
        comment_count=insight.comment_count,
        status=insight.status,
        aggregate=json.loads(insight.aggregate),
        coverage=coverage,
        sample_records=[json.loads(r.record) for r in records[:5]],
    )


@router.get("/projects/{project_id}/analytics", response_model=ProjectAnalyticsOut)
async def project_analytics(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    repo = ProjectRepository(db)
    project = await repo.get_project(project_id, user["id"])
    if not project:
        raise NotFoundError("project not found")

    videos = await repo.get_project_videos(project_id)
    records = await repo.get_all_project_records(project_id)
    field_ids = await repo.get_project_field_ids(project_id)

    project_aggregate = json.loads(project.aggregate) if project.aggregate else {}
    coverage = _coverage(records, field_ids)

    return ProjectAnalyticsOut(
        project_id=project.id,
        video_count=len(videos),
        comment_count=len(records),
        aggregate=project_aggregate,
        coverage=coverage,
    )


@router.post("/projects/{project_id}/search", response_model=SearchResult)
async def search_comments(
    project_id: str,
    body: SearchRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    repo = ProjectRepository(db)
    project = await repo.get_project(project_id, user["id"])
    if not project:
        raise NotFoundError("project not found")

    fields = await repo.get_project_fields(project_id)
    if not fields:
        raise NotFoundError("project has no analyzed comments yet")

    plan = await generate_plan(body.query, fields)
    filters = validate_filters(plan["filters"], fields)

    query_vector = None
    if plan["search_text"]:
        try:
            query_vector = (await embed([plan["search_text"]]))[0]
        except Exception as exc:  # noqa: BLE001 - semantic ranking is best-effort
            logger.warning("embedding failed for search, filter-only: %s", exc)

    hits = await repo.semantic_search(
        project_id, body.video_id, query_vector, filters, body.limit
    )
    answer = await generate_answer(body.query, hits)

    return SearchResult(
        project_id=project_id,
        query=body.query,
        answer=answer,
        search_text=plan["search_text"],
        filters_used=filters,
        hits=[SearchHit(**h) for h in hits],
    )


# helpers ---------------------------------------------------------------


async def _project_out(db: AsyncSession, project_id: str, owner_id: str) -> ProjectOut:
    repo = ProjectRepository(db)
    project = await repo.get_project(project_id, owner_id)
    if not project:
        raise NotFoundError("project not found")
    fields = await repo.get_project_field_ids(project_id)
    videos = await repo.get_project_videos(project_id)
    return ProjectOut(
        id=project.id,
        name=project.name,
        fields=[ProjectFieldOut(field_id=fid, enabled=True) for fid in fields],
        videos=[
            ProjectVideoOut(video_id=v.video_id, added_at=v.created_at) for v in videos
        ],
        created_at=project.created_at,
    )


def _coverage(records, field_ids: list[str]) -> dict[str, dict[str, float]]:
    agg = aggregate_records([json.loads(r.record) for r in records], field_ids)
    total = max(len(records), 1)
    return {
        fid: {
            "available": round(agg["availability"].get(fid, 0) / total, 4),
            "unavailable": round(1 - agg["availability"].get(fid, 0) / total, 4),
        }
        for fid in field_ids
    }
