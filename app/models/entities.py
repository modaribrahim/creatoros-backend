from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.core.database import Base


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    channel_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        Index(
            "ix_comments_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    comment_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    video_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("videos.video_id"), index=True
    )
    author: Mapped[str | None] = mapped_column(String(256), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    embedding: Mapped[list[float]] = mapped_column(
        Vector(settings.embedding_dim), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), index=True)
    aggregate: Mapped[dict | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_token_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    verification_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class RefreshToken(Base):
    """Server-side refresh token ledger: enables logout + rotation detection."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        UniqueConstraint(
            "family_id", "token_hash", name="uq_refresh_token_family_hash"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), index=True)
    family_id: Mapped[str] = mapped_column(String(64), index=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ProjectField(Base):
    """Immutable snapshot of the field config chosen at project setup."""

    __tablename__ = "project_fields"
    __table_args__ = (
        UniqueConstraint("project_id", "field_id", name="uq_project_field"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id"), index=True
    )
    field_id: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class ProjectVideo(Base):
    __tablename__ = "project_videos"
    __table_args__ = (
        UniqueConstraint("project_id", "video_id", name="uq_project_video"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id"), index=True
    )
    video_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Run(Base):
    """A single analysis experiment for one video inside a project."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"))
    video_id: Mapped[str] = mapped_column(String(64))
    job_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("jobs.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="pending")
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    changed_count: Mapped[int] = mapped_column(Integer, default=0)
    existing_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CommentInsight(Base):
    __tablename__ = "comment_insights"
    __table_args__ = (
        UniqueConstraint("project_id", "video_id", name="uq_project_video_insight"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"))
    video_id: Mapped[str] = mapped_column(String(64))
    raw_data: Mapped[dict] = mapped_column("raw_data", Text)
    aggregate: Mapped[dict] = mapped_column("aggregate", Text)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="completed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id"), nullable=True
    )
    video_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    analyzed_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AnalysisField(Base):
    __tablename__ = "analysis_fields"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(16))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id"), nullable=True, index=True
    )


class AnalysisFieldOption(Base):
    __tablename__ = "analysis_field_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    field_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("analysis_fields.id"), index=True
    )
    value: Mapped[str] = mapped_column(String(128))


class CommentRecord(Base):
    __tablename__ = "comment_records"
    __table_args__ = (
        UniqueConstraint("project_id", "comment_id", name="uq_project_comment"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"))
    video_id: Mapped[str] = mapped_column(String(64))
    comment_id: Mapped[str] = mapped_column(String(64))
    parent_comment_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    run_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("runs.id"), nullable=True
    )
    field_ids: Mapped[str] = mapped_column(Text)
    record: Mapped[dict] = mapped_column("record", Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), index=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(160), default="New chat")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("chat_sessions.id"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
