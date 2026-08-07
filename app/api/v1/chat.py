from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError
from app.repositories.chat import ChatRepository
from app.repositories.projects import ProjectRepository
from app.schemas.chat import (
    ChatMessageOut,
    ChatReply,
    ChatRequest,
    ChatSessionCreate,
    ChatSessionOut,
)
from app.services import chat as chat_service

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat/sessions", response_model=ChatSessionOut, status_code=201)
async def create_session(
    body: ChatSessionCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    if body.project_id:
        project = await ProjectRepository(db).get_project(body.project_id, user["id"])
        if not project:
            raise NotFoundError("project not found")
    session = await ChatRepository(db).create_session(
        user["id"], body.project_id, body.title
    )
    return ChatSessionOut(
        id=session.id,
        project_id=session.project_id,
        title=session.title,
        created_at=session.created_at,
    )


@router.get("/chat/sessions", response_model=list[ChatSessionOut])
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    sessions = await ChatRepository(db).list_sessions(user["id"])
    return [
        ChatSessionOut(
            id=s.id, project_id=s.project_id, title=s.title, created_at=s.created_at
        )
        for s in sessions
    ]


@router.get("/chat/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
async def list_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    repo = ChatRepository(db)
    session = await repo.get_session(session_id, user["id"])
    if not session:
        raise NotFoundError("chat session not found")
    return [
        ChatMessageOut(
            id=m.id,
            session_id=m.session_id,
            role=m.role,
            content=m.content,
            created_at=m.created_at,
        )
        for m in await repo.get_messages(session_id)
    ]


@router.post("/chat/sessions/{session_id}/messages", response_model=ChatReply)
async def send_message(
    session_id: str,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    repo = ChatRepository(db)
    session = await repo.get_session(session_id, user["id"])
    if not session:
        raise NotFoundError("chat session not found")
    return await chat_service.send_message(db, session, user["id"], body.content)
