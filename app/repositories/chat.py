from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatMessage, ChatSession


class ChatRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_session(
        self, user_id: str, project_id: str | None, title: str | None
    ) -> ChatSession:
        session = ChatSession(
            id=str(uuid4()),
            user_id=user_id,
            project_id=project_id,
            title=title or "New chat",
        )
        self.session.add(session)
        await self.session.commit()
        return session

    async def get_session(self, session_id: str, user_id: str) -> ChatSession | None:
        return await self.session.scalar(
            select(ChatSession).where(
                ChatSession.id == session_id, ChatSession.user_id == user_id
            )
        )

    async def list_sessions(self, user_id: str) -> list[ChatSession]:
        result = await self.session.scalars(
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.created_at.desc())
        )
        return list(result.all())

    async def add_message(
        self, session_id: str, role: str, content: str
    ) -> ChatMessage:
        message = ChatMessage(session_id=session_id, role=role, content=content)
        self.session.add(message)
        await self.session.commit()
        return message

    async def get_messages(self, session_id: str) -> list[ChatMessage]:
        result = await self.session.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
        )
        return list(result.all())

    async def set_title(self, session_id: str, title: str) -> None:
        session = await self.session.get(ChatSession, session_id)
        if session:
            session.title = title
            await self.session.commit()

    async def delete_session(self, session_id: str) -> bool:
        session = await self.session.scalar(
            select(ChatSession).where(ChatSession.id == session_id)
        )
        if not session:
            return False
        await self.session.execute(
            delete(ChatMessage).where(ChatMessage.session_id == session_id)
        )
        await self.session.delete(session)
        await self.session.commit()
        return True

    async def delete_message(self, session_id: str, message_id: int) -> bool:
        result = await self.session.execute(
            delete(ChatMessage).where(
                ChatMessage.id == message_id,
                ChatMessage.session_id == session_id,
            )
        )
        await self.session.commit()
        return result.rowcount is not None and result.rowcount > 0
