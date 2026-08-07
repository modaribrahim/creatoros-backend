import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.celery_app import celery_app
from app.core.config import settings
from app.repositories.comments import CommentRepository
from app.repositories.projects import ProjectRepository
from app.services.aggregator import aggregate_records
from app.services.base_task import AsyncTask
from app.services.chunk_analyzer import analyze_comments
from app.services.fields import seed_fields
from app.services.incremental import plan_incremental
from app.services.openrouter import embed
from app.services.youtube import fetch_comments

logger = logging.getLogger(__name__)


def _session_factory():
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    return engine, async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )


def _records_as_dicts(records) -> list[dict]:
    return [json.loads(r.record) for r in records]


async def _report_progress(
    comments_repo, job_id: str, fetched: int, analyzed: int
) -> None:
    await comments_repo.update_job_progress(job_id, fetched=fetched, analyzed=analyzed)


async def analyze_project_video_pipeline(
    project_id: str, video_id: str, job_id: str, run_id: str
) -> dict:
    engine, session_factory = _session_factory()
    try:
        async with session_factory() as session:
            comments_repo = CommentRepository(session)
            projects_repo = ProjectRepository(session)

            await comments_repo.update_job_status(job_id, "running")
            await session.commit()

            await seed_fields(session)
            fields = await projects_repo.get_project_fields(project_id)
            field_ids = [f["id"] for f in fields]

            await comments_repo.upsert_video(video_id)
            await session.commit()

            fetched = await fetch_comments(video_id)
            logger.info(
                "job %s: fetched %d comments+replies for video %s",
                job_id,
                len(fetched),
                video_id,
            )
            await comments_repo.update_job_progress(job_id, fetched=len(fetched))
            rows = [dict(c, video_id=video_id) for c in fetched]
            await comments_repo.bulk_insert_comments(rows)
            await session.commit()

            analyzed_ids = await projects_repo.get_analyzed_comment_ids(
                project_id, video_id
            )
            stored = await comments_repo.get_comments_by_video(video_id)
            stored_likes = {c.comment_id: c.like_count for c in stored}
            plan = plan_incremental(fetched, analyzed_ids, stored_likes)
            logger.info(
                "job %s: plan new=%d changed=%d reuse=%d",
                job_id,
                len(plan["new_ids"]),
                len(plan["changed_ids"]),
                len(plan["reuse_ids"]),
            )

            items = [
                (
                    c["comment_id"],
                    c["text"],
                    c.get("parent_id"),
                    c.get("parent_text"),
                )
                for c in fetched
                if c["comment_id"] in set(plan["to_analyze"])
            ]

            new_items = [
                (cid, text)
                for cid, text, _, _ in items
                if cid in set(plan["new_ids"])
            ]
            if new_items:
                try:
                    vectors = await embed([t for _, t in new_items])
                    for (cid, _), vec in zip(new_items, vectors):
                        await comments_repo.set_comment_embedding(cid, vec)
                    await session.commit()
                    logger.info(
                        "job %s: embedded %d new comments",
                        job_id,
                        len(new_items),
                    )
                except Exception as exc:  # noqa: BLE001 - embeddings are best-effort
                    logger.warning("embedding failed, continuing: %s", exc)

            records, record_field_ids = await analyze_comments(
                items,
                fields,
                on_progress=lambda done, total: _report_progress(
                    comments_repo, job_id, len(fetched), done
                ),
            )
            await comments_repo.update_job_progress(
                job_id, fetched=len(fetched), analyzed=len(records)
            )
            logger.info("job %s: analyzed %d/%d comments", job_id, len(records), len(items))

            if records:
                await projects_repo.bulk_insert_records(
                    project_id, video_id, run_id, records, record_field_ids
                )
                await session.commit()

            all_records = _records_as_dicts(
                await projects_repo.get_records(project_id, video_id)
            )
            aggregate = aggregate_records(all_records, field_ids)
            aggregate["field_ids"] = field_ids
            await projects_repo.store_insight(
                project_id, video_id, aggregate, comment_count=len(all_records)
            )
            await session.commit()

            project_records = _records_as_dicts(
                await projects_repo.get_all_project_records(project_id)
            )
            project_aggregate = aggregate_records(project_records, field_ids)
            await projects_repo.set_project_aggregate(project_id, project_aggregate)
            await session.commit()

            await projects_repo.update_run(
                run_id,
                "completed",
                fetched_count=len(fetched),
                new_count=len(plan["new_ids"]),
                changed_count=len(plan["changed_ids"]),
                existing_count=len(plan["reuse_ids"]),
            )
            await comments_repo.update_job_status(job_id, "completed")
            await session.commit()
            return {
                "job_id": job_id,
                "status": "completed",
                "fetched": len(fetched),
                "new": len(plan["new_ids"]),
                "changed": len(plan["changed_ids"]),
                "reused": len(plan["reuse_ids"]),
            }
    finally:
        await engine.dispose()


async def _mark_failed(job_id: str, error: str) -> None:
    engine, session_factory = _session_factory()
    try:
        async with session_factory() as session:
            await CommentRepository(session).update_job_status(
                job_id, "failed", error=error
            )
            await session.commit()
    finally:
        await engine.dispose()


class AnalyzeProjectVideoTask(AsyncTask):
    name = "analyze_project_video"

    async def _run(
        self, project_id: str, video_id: str, job_id: str, run_id: str
    ) -> dict:
        try:
            return await analyze_project_video_pipeline(
                project_id, video_id, job_id, run_id
            )
        except Exception as exc:
            await _mark_failed(job_id, str(exc))
            raise


analyze_project_video = celery_app.register_task(AnalyzeProjectVideoTask())
