from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError
from app.repositories.comments import CommentRepository
from app.schemas.job import JobStatus

router = APIRouter(prefix="/api/v1")


@router.get("/jobs/{job_id}", response_model=JobStatus)
async def job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    job = await CommentRepository(db).get_owned_job(job_id, user["id"])
    if not job:
        raise NotFoundError("job not found")
    return JobStatus(
        job_id=job.id, video_id=job.video_id, status=job.status, error=job.error
    )
