from datetime import datetime

from pydantic import BaseModel, Field


class ChatSessionCreate(BaseModel):
    project_id: str | None = Field(default=None)
    title: str | None = Field(default=None, max_length=160)


class ChatSessionOut(BaseModel):
    id: str
    project_id: str | None
    title: str
    created_at: datetime


class ChatMessageOut(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    created_at: datetime


class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class ChatReply(BaseModel):
    content: str
    tools_used: list[str] = Field(default_factory=list)
