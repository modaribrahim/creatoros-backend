import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Comment, CommentInsight, CommentRecord, Job, Project, Video


class CommentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert_video(
        self, video_id: str, title: str | None = None, channel_name: str | None = None
    ) -> None:
        stmt = pg_insert(Video).values(
            video_id=video_id, title=title, channel_name=channel_name
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Video.video_id],
            set_={"title": title, "channel_name": channel_name},
        )
        await self.session.execute(stmt)

    async def bulk_insert_comments(self, comments: list[dict]) -> None:
        if not comments:
            return
        rows = [
            {
                "comment_id": c["comment_id"],
                "video_id": c["video_id"],
                "author": c.get("author"),
                "text": c["text"],
                "like_count": c.get("like_count", 0),
                "published_at": (
                    datetime.fromisoformat(c["published_at"])
                    if c.get("published_at")
                    else None
                ),
            }
            for c in comments
        ]
        stmt = pg_insert(Comment).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Comment.comment_id],
            set_={"like_count": pg_insert(Comment).excluded.like_count},
        )
        await self.session.execute(stmt)

    async def set_comment_embedding(
        self, comment_id: str, embedding: list[float]
    ) -> None:
        stmt = (
            update(Comment)
            .where(Comment.comment_id == comment_id)
            .values(embedding=embedding)
        )
        await self.session.execute(stmt)

    async def store_insight(
        self,
        video_id: str,
        aggregate: dict,
        comment_count: int,
        status: str = "completed",
    ) -> None:
        stmt = pg_insert(CommentInsight).values(
            video_id=video_id,
            raw_data=json.dumps({}),
            aggregate=json.dumps(aggregate),
            comment_count=comment_count,
            status=status,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[CommentInsight.video_id],
            set_={
                "aggregate": json.dumps(aggregate),
                "comment_count": comment_count,
                "status": status,
            },
        )
        await self.session.execute(stmt)

    async def get_comments_by_video(self, video_id: str) -> list[Comment]:
        result = await self.session.execute(
            select(Comment).where(Comment.video_id == video_id)
        )
        return list(result.scalars().all())

    async def get_insight(self, video_id: str) -> CommentInsight | None:
        return await self.session.scalar(
            select(CommentInsight).where(CommentInsight.video_id == video_id)
        )

    async def create_job(
        self, job_id: str, video_id: str, project_id: str | None = None
    ) -> None:
        stmt = (
            pg_insert(Video)
            .values(video_id=video_id)
            .on_conflict_do_nothing(index_elements=[Video.video_id])
        )
        await self.session.execute(stmt)
        self.session.add(
            Job(id=job_id, project_id=project_id, video_id=video_id, status="pending")
        )
        await self.session.commit()

    async def create_job_pending_return_id(
        self, video_id: str, project_id: str | None = None
    ) -> str:
        job_id = str(uuid4())
        await self.create_job(job_id, video_id, project_id)
        return job_id

    async def update_job_status(
        self, job_id: str, status: str, error: str | None = None
    ) -> None:
        job = await self.session.get(Job, job_id)
        if job:
            job.status = status
            job.error = error
            await self.session.commit()

    async def get_job(self, job_id: str) -> Job | None:
        return await self.session.get(Job, job_id)

    async def get_owned_job(self, job_id: str, user_id: str) -> Job | None:
        """Return a job only if it belongs to a project owned by user_id."""
        return await self.session.scalar(
            select(Job)
            .join(Project, Project.id == Job.project_id)
            .where(Job.id == job_id, Project.user_id == user_id)
        )

    async def clear_records(self, video_id: str) -> None:
        await self.session.execute(
            CommentRecord.__table__.delete().where(CommentRecord.video_id == video_id)
        )

    async def bulk_insert_records(
        self, video_id: str, records: list[dict], field_ids: list[str]
    ) -> None:
        if not records:
            return
        field_ids_csv = ",".join(field_ids)
        stmt = pg_insert(CommentRecord).values(
            [
                {
                    "video_id": video_id,
                    "comment_id": record["comment_id"],
                    "field_ids": field_ids_csv,
                    "record": json.dumps(record),
                }
                for record in records
            ]
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=[CommentRecord.comment_id])
        await self.session.execute(stmt)

    async def get_records(self, video_id: str) -> list[CommentRecord]:
        result = await self.session.execute(
            select(CommentRecord).where(CommentRecord.video_id == video_id)
        )
        return list(result.scalars().all())

    async def comment_count(self, video_id: str) -> int:
        return (
            await self.session.scalar(
                select(func.count(Comment.id)).where(Comment.video_id == video_id)
            )
            or 0
        )
