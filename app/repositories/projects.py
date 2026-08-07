import json
from uuid import uuid4

from sqlalchemy import and_, cast, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AnalysisField,
    AnalysisFieldOption,
    Comment,
    CommentInsight,
    CommentRecord,
    Project,
    ProjectField,
    ProjectVideo,
    Run,
)


class ProjectRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # projects ------------------------------------------------------------
    async def create_project(self, name: str, user_id: str) -> Project:
        project = Project(id=str(uuid4()), name=name, user_id=user_id)
        self.session.add(project)
        await self.session.commit()
        return project

    async def get_project(
        self, project_id: str, owner_id: str | None = None
    ) -> Project | None:
        stmt = select(Project).where(Project.id == project_id)
        if owner_id is not None:
            stmt = stmt.where(Project.user_id == owner_id)
        return await self.session.scalar(stmt)

    async def list_projects(self, user_id: str) -> list[Project]:
        result = await self.session.scalars(
            select(Project)
            .where(Project.user_id == user_id)
            .order_by(Project.created_at.desc())
        )
        return list(result.all())

    async def set_project_aggregate(self, project_id: str, aggregate: dict) -> None:
        project = await self.session.get(Project, project_id)
        if project:
            project.aggregate = json.dumps(aggregate)
            await self.session.commit()

    # field snapshot --------------------------------------------------------
    async def set_project_fields(self, project_id: str, field_ids: list[str]) -> None:
        for fid in field_ids:
            self.session.add(
                ProjectField(project_id=project_id, field_id=fid, enabled=True)
            )
        await self.session.commit()

    async def has_project_fields(self, project_id: str) -> bool:
        return bool(
            await self.session.scalar(
                select(ProjectField.id)
                .where(ProjectField.project_id == project_id)
                .limit(1)
            )
        )

    async def get_project_field_ids(self, project_id: str) -> list[str]:
        result = await self.session.scalars(
            select(ProjectField.field_id).where(ProjectField.project_id == project_id)
        )
        return list(result.all())

    async def get_project_fields(self, project_id: str) -> list[dict]:
        field_ids = await self.get_project_field_ids(project_id)
        if not field_ids:
            return []
        fields = (
            await self.session.scalars(
                select(AnalysisField).where(AnalysisField.id.in_(field_ids))
            )
        ).all()
        options = (
            await self.session.scalars(
                select(AnalysisFieldOption).where(
                    AnalysisFieldOption.field_id.in_(field_ids)
                )
            )
        ).all()
        by_id: dict[str, list[str]] = {}
        for opt in options:
            by_id.setdefault(opt.field_id, []).append(opt.value)
        return [
            {
                "id": f.id,
                "name": f.name,
                "type": f.type,
                "enabled": True,
                "options": by_id.get(f.id, []),
            }
            for f in fields
        ]

    # videos ---------------------------------------------------------------
    async def add_project_video(self, project_id: str, video_id: str) -> None:
        self.session.add(ProjectVideo(project_id=project_id, video_id=video_id))
        await self.session.commit()

    async def has_project_video(self, project_id: str, video_id: str) -> bool:
        return bool(
            await self.session.scalar(
                select(ProjectVideo.id).where(
                    ProjectVideo.project_id == project_id,
                    ProjectVideo.video_id == video_id,
                )
            )
        )

    async def get_project_videos(self, project_id: str) -> list[ProjectVideo]:
        result = await self.session.scalars(
            select(ProjectVideo).where(ProjectVideo.project_id == project_id)
        )
        return list(result.all())

    # runs -----------------------------------------------------------------
    async def create_run(self, project_id: str, video_id: str, job_id: str) -> Run:
        run = Run(
            id=str(uuid4()),
            project_id=project_id,
            video_id=video_id,
            job_id=job_id,
            status="pending",
        )
        self.session.add(run)
        await self.session.commit()
        return run

    async def get_run(self, run_id: str) -> Run | None:
        return await self.session.get(Run, run_id)

    async def get_project_runs(self, project_id: str) -> list[Run]:
        result = await self.session.scalars(
            select(Run)
            .where(Run.project_id == project_id)
            .order_by(Run.created_at.desc())
        )
        return list(result.all())

    async def update_run(
        self,
        run_id: str,
        status: str,
        fetched_count: int = 0,
        new_count: int = 0,
        changed_count: int = 0,
        existing_count: int = 0,
    ) -> None:
        run = await self.session.get(Run, run_id)
        if run:
            run.status = status
            run.fetched_count = fetched_count
            run.new_count = new_count
            run.changed_count = changed_count
            run.existing_count = existing_count
            await self.session.commit()

    # records --------------------------------------------------------------
    async def get_analyzed_comment_ids(
        self, project_id: str, video_id: str
    ) -> set[str]:
        result = await self.session.scalars(
            select(CommentRecord.comment_id).where(
                CommentRecord.project_id == project_id,
                CommentRecord.video_id == video_id,
            )
        )
        return set(result.all())

    async def bulk_insert_records(
        self,
        project_id: str,
        video_id: str,
        run_id: str,
        records: list[dict],
        field_ids: list[str],
    ) -> None:
        if not records:
            return
        self.session.add_all(
            [
                CommentRecord(
                    project_id=project_id,
                    video_id=video_id,
                    comment_id=r["comment_id"],
                    run_id=run_id,
                    field_ids=",".join(field_ids),
                    record=json.dumps(r),
                )
                for r in records
            ]
        )
        await self.session.commit()

    async def get_records(self, project_id: str, video_id: str) -> list[CommentRecord]:
        result = await self.session.scalars(
            select(CommentRecord).where(
                CommentRecord.project_id == project_id,
                CommentRecord.video_id == video_id,
            )
        )
        return list(result.all())

    async def get_all_project_records(self, project_id: str) -> list[CommentRecord]:
        result = await self.session.scalars(
            select(CommentRecord).where(CommentRecord.project_id == project_id)
        )
        return list(result.all())

    async def top_comments(
        self, project_id: str, video_id: str | None, limit: int
    ) -> list[dict]:
        """Like-count-ranked comments, used when embeddings are unavailable."""
        base = (
            select(CommentRecord, Comment.text, Comment.author, Comment.like_count)
            .join(Comment, Comment.comment_id == CommentRecord.comment_id)
            .where(CommentRecord.project_id == project_id)
        )
        if video_id:
            base = base.where(CommentRecord.video_id == video_id)
        base = base.order_by(Comment.like_count.desc()).limit(limit)
        rows = (await self.session.execute(base)).all()
        return [
            {
                "comment_id": rec.comment_id,
                "author": author,
                "text": text,
                "score": float(like_count or 0),
                "fields": json.loads(rec.record),
            }
            for rec, text, author, like_count in rows
        ]

    # insights -------------------------------------------------------------
    async def store_insight(
        self, project_id: str, video_id: str, aggregate: dict, comment_count: int
    ) -> None:
        row = await self.session.scalar(
            select(CommentInsight).where(
                CommentInsight.project_id == project_id,
                CommentInsight.video_id == video_id,
            )
        )
        data = json.dumps(aggregate)
        if row:
            row.aggregate = data
            row.comment_count = comment_count
            row.status = "completed"
        else:
            self.session.add(
                CommentInsight(
                    project_id=project_id,
                    video_id=video_id,
                    raw_data=json.dumps({}),
                    aggregate=data,
                    comment_count=comment_count,
                    status="completed",
                )
            )
        await self.session.commit()

    async def get_insight(
        self, project_id: str, video_id: str
    ) -> CommentInsight | None:
        return await self.session.scalar(
            select(CommentInsight).where(
                CommentInsight.project_id == project_id,
                CommentInsight.video_id == video_id,
            )
        )

    # semantic search --------------------------------------------------------
    async def semantic_search(
        self,
        project_id: str,
        video_id: str | None,
        query_vector: list[float] | None,
        filters: list[dict] | None,
        limit: int,
    ) -> list[dict]:
        """Hybrid retrieval over a project's analyzed comments.

        - `filters`      -> exact pre-filter on stored fields (sentiment, ...)
        - `query_vector` -> rank candidates by cosine similarity
        - filter-only    -> rank by like_count (score = normalized likes)
        When filters AND a vector are present, filtered candidates and a
        pure-semantic set are merged so neither path hides relevant comments.
        """
        base = (
            select(CommentRecord, Comment.text, Comment.author, Comment.embedding)
            .join(Comment, Comment.comment_id == CommentRecord.comment_id)
            .where(CommentRecord.project_id == project_id)
        )
        if video_id:
            base = base.where(CommentRecord.video_id == video_id)

        merged: dict[str, dict] = {}

        async def _collect(stmt, score_fn):
            rows = (await self.session.execute(stmt)).all()
            for rec, text, author, embedding in rows:
                merged.setdefault(
                    rec.comment_id,
                    {
                        "comment_id": rec.comment_id,
                        "author": author,
                        "text": text,
                        "score": score_fn(embedding),
                        "fields": json.loads(rec.record),
                    },
                )

        if filters:
            filtered = base.where(and_(*[_filter_clause(f) for f in filters]))
            if query_vector is not None:
                filtered = filtered.order_by(
                    Comment.embedding.cosine_distance(query_vector)
                )
            else:
                filtered = filtered.order_by(Comment.like_count.desc())
            await _collect(filtered.limit(limit), _similarity_fn(query_vector))

        if query_vector is not None:
            semantic = base.order_by(
                Comment.embedding.cosine_distance(query_vector)
            ).limit(limit)
            await _collect(semantic, _similarity_fn(query_vector))

        return sorted(merged.values(), key=lambda r: r["score"], reverse=True)[:limit]


def _similarity_fn(query_vector):
    def _score(embedding) -> float:
        if embedding is None or query_vector is None:
            return 0.0
        return round(_cosine(embedding, query_vector), 4)

    return _score


def _cosine(a: list[float], b: list[float]) -> float:
    import math

    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _filter_clause(f: dict):
    field = cast(CommentRecord.record, JSONB)[f["field"]]
    value = f["value"]
    op = f.get("op", "eq")
    if op == "gte":
        return field.as_float() >= float(value)
    if op == "lte":
        return field.as_float() <= float(value)
    return field.as_string() == str(value)
