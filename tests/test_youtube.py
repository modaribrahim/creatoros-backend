import httpx
import pytest

from app.services import youtube


class FakeTransport(httpx.AsyncBaseTransport):
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    async def handle_async_request(self, request):
        self.calls.append(request.url.path)
        params = dict(request.url.params)
        if "parentId" in params:
            body = self.pages["replies"]
        else:
            body = self.pages["threads"]
        return httpx.Response(200, json=body, request=request)


THREAD_PAGE = {
    "items": [
        {
            "id": "UgHi_t1",
            "snippet": {
                "totalReplyCount": 2,
                "topLevelComment": {
                    "snippet": {
                        "authorDisplayName": "alice",
                        "textOriginal": "top comment",
                        "likeCount": 5,
                        "publishedAt": "2026-01-01T00:00:00Z",
                    }
                },
            },
        },
        {
            "id": "UgHi_t2",
            "snippet": {
                "totalReplyCount": 0,
                "topLevelComment": {
                    "snippet": {
                        "authorDisplayName": "bob",
                        "textOriginal": "no replies",
                        "likeCount": 1,
                        "publishedAt": "2026-01-02T00:00:00Z",
                    }
                },
            },
        },
    ],
    "nextPageToken": None,
}

REPLIES_PAGE = {
    "items": [
        {
            "id": "UgHi_t1_r1",
            "snippet": {
                "authorDisplayName": "carol",
                "textOriginal": "reply one",
                "likeCount": 2,
                "publishedAt": "2026-01-01T01:00:00Z",
            },
        },
        {
            "id": "UgHi_t1_r2",
            "snippet": {
                "authorDisplayName": "dave",
                "textOriginal": "reply two",
                "likeCount": 0,
                "publishedAt": "2026-01-01T02:00:00Z",
            },
        },
    ],
    "nextPageToken": None,
}


@pytest.mark.asyncio
async def test_fetch_comments_includes_replies(monkeypatch):
    monkeypatch.setattr(youtube.settings, "youtube_api_key", "test-key")
    client = httpx.AsyncClient(
        transport=FakeTransport({"threads": THREAD_PAGE, "replies": REPLIES_PAGE})
    )
    monkeypatch.setattr(youtube.httpx, "AsyncClient", lambda **kw: client)
    comments = await youtube.fetch_comments("v1")
    texts = [c["text"] for c in comments]
    assert texts == ["top comment", "reply one", "reply two", "no replies"]
    assert any(c["comment_id"] == "UgHi_t1" for c in comments)
    assert any(c["comment_id"] == "UgHi_t1_r1" for c in comments)


@pytest.mark.asyncio
async def test_reply_carries_parent_context(monkeypatch):
    monkeypatch.setattr(youtube.settings, "youtube_api_key", "test-key")
    client = httpx.AsyncClient(
        transport=FakeTransport({"threads": THREAD_PAGE, "replies": REPLIES_PAGE})
    )
    monkeypatch.setattr(youtube.httpx, "AsyncClient", lambda **kw: client)
    comments = await youtube.fetch_comments("v1")
    reply = next(c for c in comments if c["comment_id"] == "UgHi_t1_r1")
    assert reply["parent_id"] == "UgHi_t1"
    assert reply["parent_text"] == "top comment"
    top = next(c for c in comments if c["comment_id"] == "UgHi_t1")
    assert top["parent_id"] is None


@pytest.mark.asyncio
async def test_analyze_chunk_injects_reply_context(monkeypatch):
    from app.services import chunk_analyzer as ca

    captured = {}

    async def fake_chat(system, user, json_mode=True):
        captured["user"] = user
        return (
            '{"records":['
            '{"intent":"interested","sentiment_label":"positive","primary_topic":"feature"},'
            '{"intent":"interested","sentiment_label":"positive","primary_topic":"feature"}'
            "]}"
        )

    monkeypatch.setattr(ca, "chat", fake_chat)

    fields = [
        {"id": "intent", "type": "enum", "options": ["purchase_intent", "interested"]},
        {"id": "sentiment_label", "type": "enum", "options": ["positive", "negative"]},
        {"id": "primary_topic", "type": "enum", "options": ["feature", "pricing"]},
    ]
    records = await ca.analyze_chunk(
        [
            ("t1", "I hate the bug", None, None),
            ("r1", "agree", "t1", "I hate the bug"),
        ],
        "sys",
        fields,
    )
    assert "[replying to: I hate the bug] agree" in captured["user"]
    assert records[1]["parent_comment_id"] == "t1"
    assert records[1]["parent_text"] == "I hate the bug"
    assert records[0]["parent_comment_id"] is None
