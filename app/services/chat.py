import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.chat import ChatRepository
from app.repositories.projects import ProjectRepository
from app.schemas.chat import ChatReply
from app.services.aggregator import aggregate_records
from app.services.openrouter import chat_message, embed

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are CreatorOS Chat, an assistant that helps a creator understand their
YouTube comments. You have tools to read a project's analytics and to search its
analyzed comments.

Rules:
- Only access the project(s) the user owns. The tools verify ownership; if a tool
  returns an ownership/not-found error, say you could not find that project.
- When you reference specific comments, cite them by their text or score so the
  user can find them. Never invent comment text, counts, or statistics.
- Prefer exact data from tools over guessing. If a tool does not answer the
  question, say what you found and what you could not determine.
- Keep answers concise and concrete; a few short paragraphs max unless asked.
- You are not allowed to run SQL or query the raw database; use only the tools."""

TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "get_project_analytics",
            "description": (
                "Return aggregate analytics for a project: number of videos, "
                "number of analyzed comments, field distributions, sentiment, "
                "priority/churn/purchase-intent counts, and field coverage."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The project id to analyze.",
                    }
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_videos",
            "description": "List the video ids that belong to a project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The project id to list videos for.",
                    }
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_video_insights",
            "description": (
                "Return the analysis insights for a single video in a project: "
                "comment count, aggregate metrics, field coverage, and a few "
                "sample comments with their fields."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The project the video belongs to.",
                    },
                    "video_id": {
                        "type": "string",
                        "description": "The video id (YouTube id).",
                    },
                },
                "required": ["project_id", "video_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_comments",
            "description": (
                "Semantic search over a project's analyzed comments. Use when the "
                "user asks a topic/content question (e.g. 'what do people say "
                "about pricing?') that needs reading actual comments."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The natural-language question or topic.",
                    },
                    "project_id": {
                        "type": "string",
                        "description": "The project to search.",
                    },
                    "video_id": {
                        "type": "string",
                        "description": "Optional: restrict to one video.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max comments to return (default 8).",
                    },
                },
                "required": ["query", "project_id"],
            },
        },
    },
]


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


async def _guard(db: AsyncSession, user_id: str, project_id: str | None) -> dict:
    """Return the project dict or an error payload."""
    if not project_id:
        return {"error": "project_id is required"}
    project = await ProjectRepository(db).get_project(project_id, user_id)
    if not project:
        return {"error": "project not found or not owned by this user"}
    return {"project": project}


async def _analytics(db: AsyncSession, user_id: str, args: dict) -> str:
    repo = ProjectRepository(db)
    checked = await _guard(db, user_id, args.get("project_id"))
    if "error" in checked:
        return json.dumps(checked)
    project = checked["project"]
    pid = project.id
    videos = await repo.get_project_videos(pid)
    records = await repo.get_all_project_records(pid)
    field_ids = await repo.get_project_field_ids(pid)
    return json.dumps(
        {
            "project_id": pid,
            "project_name": project.name,
            "video_count": len(videos),
            "videos": [v.video_id for v in videos],
            "comment_count": len(records),
            "aggregate": json.loads(project.aggregate) if project.aggregate else {},
            "coverage": _coverage(records, field_ids),
        }
    )


async def _videos(db: AsyncSession, user_id: str, args: dict) -> str:
    repo = ProjectRepository(db)
    checked = await _guard(db, user_id, args.get("project_id"))
    if "error" in checked:
        return json.dumps(checked)
    videos = await repo.get_project_videos(checked["project"].id)
    return json.dumps(
        [{"video_id": v.video_id, "added_at": v.created_at.isoformat()} for v in videos]
    )


async def _insights(db: AsyncSession, user_id: str, args: dict) -> str:
    repo = ProjectRepository(db)
    checked = await _guard(db, user_id, args.get("project_id"))
    if "error" in checked:
        return json.dumps(checked)
    pid, video_id = checked["project"].id, args.get("video_id")
    if not video_id:
        return json.dumps({"error": "video_id is required"})
    insight = await repo.get_insight(pid, video_id)
    if not insight:
        return json.dumps(
            {"error": "no completed analysis for this video in the project"}
        )
    records = await repo.get_records(pid, video_id)
    field_ids = await repo.get_project_field_ids(pid)
    return json.dumps(
        {
            "project_id": pid,
            "video_id": video_id,
            "comment_count": insight.comment_count,
            "status": insight.status,
            "aggregate": json.loads(insight.aggregate),
            "coverage": _coverage(records, field_ids),
            "sample_records": [json.loads(r.record) for r in records[:5]],
        }
    )


async def _search(db: AsyncSession, user_id: str, args: dict) -> str:
    repo = ProjectRepository(db)
    checked = await _guard(db, user_id, args.get("project_id"))
    if "error" in checked:
        return json.dumps(checked)
    pid = checked["project"].id
    query = (args.get("query") or "").strip()
    if not query:
        return json.dumps({"error": "query is required"})
    fields = await repo.get_project_fields(pid)
    if not fields:
        return json.dumps({"error": "project has no analyzed comments yet"})

    video_id = args.get("video_id")
    limit = int(args.get("limit") or settings.chat_rag_limit)
    try:
        vector = (await embed([query]))[0]
        hits = await repo.semantic_search(pid, video_id, vector, None, limit)
    except Exception as exc:  # noqa: BLE001 - embeddings are best-effort
        logger.warning("chat semantic search degraded to like-ranked: %s", exc)
        hits = await repo.top_comments(pid, video_id, limit)
    return json.dumps(hits)


TOOL_HANDLERS = {
    "get_project_analytics": _analytics,
    "get_project_videos": _videos,
    "get_video_insights": _insights,
    "search_comments": _search,
}


def _conversation(history) -> list[dict]:
    return [
        {"role": m.role, "content": m.content}
        for m in history
        if m.role in ("user", "assistant")
    ]


async def _system_prompt(db: AsyncSession, user_id: str, session_row) -> str:
    prompt = SYSTEM_PROMPT
    if session_row.project_id:
        project = await ProjectRepository(db).get_project(
            session_row.project_id, user_id
        )
        if project:
            prompt += (
                f"\n\nYou are currently scoped to project {project.id} "
                f"(name: {project.name!r}). Use project_id {project.id!r} in your "
                "tool calls unless the user explicitly mentions a different project."
            )
        else:
            prompt += (
                f"\n\nThis chat's project ({session_row.project_id}) was not found "
                "or is not owned by the user; tell them you cannot access it."
            )
    return prompt


async def send_message(
    db: AsyncSession, session_row, user_id: str, content: str
) -> ChatReply:
    repo = ChatRepository(db)
    if session_row.title == "New chat":
        await repo.set_title(session_row.id, content[:60])

    await repo.add_message(session_row.id, "user", content)
    messages = [
        {"role": "system", "content": await _system_prompt(db, user_id, session_row)}
    ]
    messages += _conversation(await repo.get_messages(session_row.id))

    tools_used: list[str] = []
    reply = "I couldn't complete that in the allowed number of tool calls."
    for _ in range(settings.chat_tool_limit):
        message = await chat_message(messages, tools=TOOL_DEFS)
        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            reply = (message.content or "").strip()
            break

        messages.append(
            {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments or "",
                        },
                    }
                    for tc in tool_calls
                ],
            }
        )
        for tc in tool_calls:
            handler = TOOL_HANDLERS.get(tc.function.name)
            if not handler:
                result = json.dumps({"error": f"unknown tool {tc.function.name}"})
            else:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = await handler(db, user_id, args)
            tools_used.append(tc.function.name)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    await repo.add_message(session_row.id, "assistant", reply)
    return ChatReply(content=reply, tools_used=sorted(set(tools_used)))
