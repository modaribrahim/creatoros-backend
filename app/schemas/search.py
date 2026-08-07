from typing import Any

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    video_id: str | None = Field(default=None, max_length=64)
    limit: int = Field(default=10, ge=1, le=50)


class SearchHit(BaseModel):
    comment_id: str
    author: str | None = None
    text: str
    score: float
    fields: dict[str, Any]


class SearchResult(BaseModel):
    project_id: str
    query: str
    answer: str
    search_text: str
    filters_used: list[dict[str, Any]]
    hits: list[SearchHit]
