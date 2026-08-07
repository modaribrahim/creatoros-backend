from pydantic import BaseModel


class JobStarted(BaseModel):
    job_id: str
    task_id: str
    status: str = "pending"


class JobStatus(BaseModel):
    job_id: str
    video_id: str
    status: str
    error: str | None = None
    fetched_count: int = 0
    analyzed_count: int = 0
