import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.dependencies import get_current_user
from app.main import app
from app.services import chat as chat_service


class FakeProjectRepo:
    def __init__(self, owned=True, has_comments=True):
        self.owned = owned
        self.has_comments = has_comments
        self.semantic_called = False
        self.top_called = False

    async def get_project(self, project_id, owner_id=None):
        if not self.owned:
            return None
        return SimpleNamespace(id=project_id, name="Launch", aggregate=None)

    async def get_project_videos(self, project_id):
        return [SimpleNamespace(video_id="v1", created_at=None)]

    async def get_all_project_records(self, project_id):
        return [SimpleNamespace(record=json.dumps({"sentiment_label": "negative"}))]

    async def get_project_field_ids(self, project_id):
        return ["sentiment_label"]

    async def get_project_fields(self, project_id):
        return [{"id": "sentiment_label", "type": "enum", "options": ["negative"]}]

    async def get_insight(self, project_id, video_id):
        return SimpleNamespace(
            project_id=project_id,
            video_id=video_id,
            comment_count=1,
            status="completed",
            aggregate='{"comment_count": 1}',
        )

    async def get_records(self, project_id, video_id):
        return [SimpleNamespace(record=json.dumps({"sentiment_label": "negative"}))]

    async def semantic_search(self, project_id, video_id, vector, filters, limit):
        self.semantic_called = True
        return [
            {"comment_id": "c1", "text": "too expensive", "score": 0.9, "fields": {}}
        ]

    async def top_comments(self, project_id, video_id, limit):
        self.top_called = True
        return [
            {"comment_id": "c1", "text": "too expensive", "score": 5.0, "fields": {}}
        ]


class FakeChatRepo:
    def __init__(self):
        self.messages: list[dict] = []
        self.title = None
        self.sessions: set[str] = set()

    async def set_title(self, session_id, title):
        self.title = title

    async def add_message(self, session_id, role, content):
        self.messages.append({"role": role, "content": content})
        return SimpleNamespace(id=1, session_id=session_id, role=role, content=content)

    async def get_messages(self, session_id):
        return [
            SimpleNamespace(role=m["role"], content=m["content"]) for m in self.messages
        ]

    async def delete_session(self, session_id):
        self.sessions.discard(session_id)
        return True

    async def delete_message(self, session_id, message_id):
        return True


def _tool_call(name, args):
    return SimpleNamespace(
        id=f"call-{name}",
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def _msg(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


@pytest.fixture
def patch_all(monkeypatch):
    script = []
    chat_repo = FakeChatRepo()
    proj_repo = FakeProjectRepo()

    async def fake_chat_message(messages, tools=None, temperature=0.3):
        return script.pop(0)

    monkeypatch.setattr(chat_service, "chat_message", fake_chat_message)
    monkeypatch.setattr(chat_service, "ChatRepository", lambda db: chat_repo)
    monkeypatch.setattr(chat_service, "ProjectRepository", lambda db: proj_repo)
    monkeypatch.setattr(chat_service, "embed", _fake_embed)
    return SimpleNamespace(
        script=script,
        chat_repo=chat_repo,
        proj_repo=proj_repo,
    )


async def _fake_embed(texts):
    return [[0.0] * 3]


def _session(title="New chat"):
    return SimpleNamespace(id="s1", title=title, project_id=None)


# --- send_message orchestration ----------------------------------------------


@pytest.mark.asyncio
async def test_send_message_calls_tools_then_answers(patch_all):
    patch_all.script[:] = [
        _msg(
            tool_calls=[
                _tool_call("search_comments", {"query": "pricing", "project_id": "p1"})
            ]
        ),
        _msg(tool_calls=[_tool_call("get_project_analytics", {"project_id": "p1"})]),
        _msg("people complain about pricing a lot."),
    ]
    reply = await chat_service.send_message(
        None, _session(), "u1", "what about pricing?"
    )
    assert reply.content == "people complain about pricing a lot."
    assert reply.tools_used == ["get_project_analytics", "search_comments"]
    roles = [m["role"] for m in patch_all.chat_repo.messages]
    assert roles == ["user", "assistant"]


@pytest.mark.asyncio
async def test_send_message_no_tools_needed(patch_all):
    patch_all.script[:] = [_msg("hello!")]
    reply = await chat_service.send_message(None, _session(), "u1", "hi")
    assert reply.content == "hello!"
    assert reply.tools_used == []


@pytest.mark.asyncio
async def test_send_message_loop_guard(patch_all):
    patch_all.script[:] = [
        _msg(
            tool_calls=[
                _tool_call("search_comments", {"query": "x", "project_id": "p1"})
            ]
        )
    ] * 20
    reply = await chat_service.send_message(None, _session(), "u1", "hi")
    assert "allowed number" in reply.content
    assert len(patch_all.chat_repo.messages) == 2


@pytest.mark.asyncio
async def test_send_message_titles_first_message(patch_all):
    patch_all.script[:] = [_msg("ok")]
    await chat_service.send_message(None, _session(), "u1", "what is the sentiment?")
    assert patch_all.chat_repo.title == "what is the sentiment?"


@pytest.mark.asyncio
async def test_send_message_unknown_tool_result_survives(patch_all):
    patch_all.script[:] = [
        _msg(tool_calls=[_tool_call("nope_tool", {})]),
        _msg("done"),
    ]
    reply = await chat_service.send_message(None, _session(), "u1", "hi")
    assert reply.content == "done"


@pytest.mark.asyncio
async def test_system_prompt_injects_project_scope(patch_all):
    prompt = await chat_service._system_prompt(
        None, "u1", SimpleNamespace(id="s1", title="t", project_id="p1")
    )
    assert "project_id 'p1'" in prompt
    assert "Launch" in prompt


@pytest.mark.asyncio
async def test_system_prompt_unowned_project_flagged(monkeypatch):
    monkeypatch.setattr(
        chat_service, "ProjectRepository", lambda db: FakeProjectRepo(owned=False)
    )
    prompt = await chat_service._system_prompt(
        None, "u1", SimpleNamespace(id="s1", title="t", project_id="p1")
    )
    assert "not owned" in prompt


# --- tool handlers -------------------------------------------------------------


@pytest.mark.asyncio
async def test_analytics_owned(patch_all):
    result = await chat_service._analytics(None, "u1", {"project_id": "p1"})
    data = json.loads(result)
    assert data["project_name"] == "Launch"
    assert data["comment_count"] == 1


@pytest.mark.asyncio
async def test_analytics_not_owned(monkeypatch):
    monkeypatch.setattr(
        chat_service, "ProjectRepository", lambda db: FakeProjectRepo(owned=False)
    )
    result = await chat_service._analytics(None, "u1", {"project_id": "p1"})
    assert "error" in json.loads(result)


@pytest.mark.asyncio
async def test_insights_missing_video(patch_all):
    result = await chat_service._insights(None, "u1", {"project_id": "p1"})
    assert "error" in json.loads(result)


@pytest.mark.asyncio
async def test_search_semantic(patch_all):
    result = await chat_service._search(
        None, "u1", {"query": "pricing", "project_id": "p1"}
    )
    hits = json.loads(result)
    assert hits[0]["text"] == "too expensive"
    assert patch_all.proj_repo.semantic_called
    assert not patch_all.proj_repo.top_called


@pytest.mark.asyncio
async def test_search_falls_back_to_like_ranked(monkeypatch):
    async def failing_embed(texts):
        raise RuntimeError("embedding down")

    monkeypatch.setattr(chat_service, "embed", failing_embed)
    monkeypatch.setattr(chat_service, "ProjectRepository", lambda db: FakeProjectRepo())
    result = await chat_service._search(
        None, "u1", {"query": "pricing", "project_id": "p1"}
    )
    hits = json.loads(result)
    assert hits[0]["score"] == 5.0


# --- delete endpoints ------------------------------------------------------------


def test_delete_session_endpoint(monkeypatch):
    from app.api.v1 import chat as chat_module
    from app.core.database import get_db

    async def fake_current_user():
        return {"id": "u1", "email": "a@b.co", "email_verified": True}

    class StubRepo:
        async def get_session(self, session_id, user_id):
            return SimpleNamespace(id=session_id)

        async def delete_session(self, session_id):
            return True

    async def fake_get_db():
        yield None

    monkeypatch.setattr(chat_module, "ChatRepository", lambda db: StubRepo())
    app.dependency_overrides[get_current_user] = fake_current_user
    app.dependency_overrides[get_db] = fake_get_db
    try:
        client = TestClient(app)
        resp = client.delete("/api/v1/chat/sessions/s1")
        assert resp.status_code == 200
        assert resp.json() == {"deleted": "s1"}
    finally:
        app.dependency_overrides.clear()


def test_delete_session_endpoint_not_owned(monkeypatch):
    from app.api.v1 import chat as chat_module
    from app.core.database import get_db

    async def fake_current_user():
        return {"id": "u1", "email": "a@b.co", "email_verified": True}

    class StubRepo:
        async def get_session(self, session_id, user_id):
            return None

    async def fake_get_db():
        yield None

    monkeypatch.setattr(chat_module, "ChatRepository", lambda db: StubRepo())
    app.dependency_overrides[get_current_user] = fake_current_user
    app.dependency_overrides[get_db] = fake_get_db
    try:
        client = TestClient(app)
        assert client.delete("/api/v1/chat/sessions/s1").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_delete_message_endpoint(monkeypatch):
    from app.api.v1 import chat as chat_module
    from app.core.database import get_db

    async def fake_current_user():
        return {"id": "u1", "email": "a@b.co", "email_verified": True}

    class StubRepo:
        async def get_session(self, session_id, user_id):
            return SimpleNamespace(id=session_id)

        async def delete_message(self, session_id, message_id):
            return True

    async def fake_get_db():
        yield None

    monkeypatch.setattr(chat_module, "ChatRepository", lambda db: StubRepo())
    app.dependency_overrides[get_current_user] = fake_current_user
    app.dependency_overrides[get_db] = fake_get_db
    try:
        client = TestClient(app)
        resp = client.delete("/api/v1/chat/sessions/s1/messages/5")
        assert resp.status_code == 200
        assert resp.json() == {"deleted": 5}
    finally:
        app.dependency_overrides.clear()


def test_delete_message_endpoint_not_found(monkeypatch):
    from app.api.v1 import chat as chat_module
    from app.core.database import get_db

    async def fake_current_user():
        return {"id": "u1", "email": "a@b.co", "email_verified": True}

    class StubRepo:
        async def get_session(self, session_id, user_id):
            return SimpleNamespace(id=session_id)

        async def delete_message(self, session_id, message_id):
            return False

    async def fake_get_db():
        yield None

    monkeypatch.setattr(chat_module, "ChatRepository", lambda db: StubRepo())
    app.dependency_overrides[get_current_user] = fake_current_user
    app.dependency_overrides[get_db] = fake_get_db
    try:
        client = TestClient(app)
        assert (
            client.delete("/api/v1/chat/sessions/s1/messages/5").status_code == 404
        )
    finally:
        app.dependency_overrides.clear()
