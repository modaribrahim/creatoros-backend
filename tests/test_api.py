from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import AppError, NotFoundError
from app.main import app, app_error_handler


def test_health():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in {"ok", "degraded"}
    assert set(body) >= {"status", "database", "redis"}


def test_validation_error_envelope():
    client = TestClient(app)
    resp = client.post("/api/v1/auth/signup", json={})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "detail" in body["error"]


def test_app_error_handler_envelope():
    mini = FastAPI()

    @mini.get("/boom")
    async def boom():
        raise NotFoundError("widget not found")

    mini.add_exception_handler(AppError, app_error_handler)
    resp = TestClient(mini).get("/boom")
    assert resp.status_code == 404
    assert resp.json() == {
        "error": {"code": "NOT_FOUND", "message": "widget not found"}
    }


def test_auth_requires_bearer_token():
    client = TestClient(app)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/projects").status_code == 401


def test_validation_errors_auth_schema():
    client = TestClient(app)
    resp = client.post(
        "/api/v1/auth/signup", json={"email": "not-an-email", "password": "x"}
    )
    assert resp.status_code == 422
    assert (
        client.post(
            "/api/v1/auth/signup", json={"email": "a@b.co", "password": "short"}
        ).status_code
        == 422
    )


def test_project_endpoints_run_ownership_check():
    """A valid token still requires a real user in the DB (dependency wired)."""
    from app.core.database import get_db
    from app.core.security import create_access_token

    class FakeSession:
        async def get(self, model, pk):
            return None

        async def scalar(self, stmt):
            return None

    async def fake_get_db():
        yield FakeSession()

    app.dependency_overrides[get_db] = fake_get_db
    try:
        client = TestClient(app)
        token = create_access_token("no-such-user")
        resp = client.get(
            "/api/v1/projects", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_projects_scope_to_current_user(monkeypatch):
    """A user cannot read a project owned by another user."""
    from app.core.dependencies import get_current_user
    from app.repositories.projects import ProjectRepository

    async def fake_current_user():
        return {"id": "user-1", "email": "a@b.co", "email_verified": True}

    async def fake_get_owned_project(self, project_id, owner_id=None):
        if owner_id != "user-other":
            return None
        return SimpleNamespace(
            id=project_id,
            name="p",
            user_id="user-other",
            aggregate=None,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

    monkeypatch.setattr(ProjectRepository, "get_project", fake_get_owned_project)
    app.dependency_overrides[get_current_user] = fake_current_user
    try:
        client = TestClient(app)
        assert client.get("/api/v1/projects/other-user-project").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_project_fields_put_returns_field_out_shape(monkeypatch):
    """The fields PUT must return a list of ProjectFieldOut, not raw ids."""
    from app.core.dependencies import get_current_user, get_db
    from app.repositories.projects import ProjectRepository

    async def fake_current_user():
        return {"id": "user-1", "email": "a@b.co", "email_verified": True}

    class FakeSession:
        async def scalar(self, stmt):
            return SimpleNamespace(id="project-1", user_id="user-1", name="p")

    async def fake_get_db():
        yield FakeSession()

    async def fake_has_fields(self, project_id):
        return False

    async def fake_has_runs(self, project_id):
        return False

    async def fake_set_fields(self, project_id, field_ids):
        return None

    async def fake_get_field_ids(self, project_id):
        return ["sentiment_label", "priority"]

    async def fake_get_fields(db, user_id=None):
        return [{"id": "sentiment_label"}, {"id": "priority"}]

    monkeypatch.setattr(ProjectRepository, "has_project_fields", fake_has_fields)
    monkeypatch.setattr(ProjectRepository, "has_project_runs", fake_has_runs)
    monkeypatch.setattr(ProjectRepository, "set_project_fields", fake_set_fields)
    monkeypatch.setattr(ProjectRepository, "get_project_field_ids", fake_get_field_ids)
    monkeypatch.setattr(
        "app.api.v1.projects.get_fields", fake_get_fields
    )
    app.dependency_overrides[get_current_user] = fake_current_user
    app.dependency_overrides[get_db] = fake_get_db
    try:
        client = TestClient(app)
        resp = client.put(
            "/api/v1/projects/project-1/fields",
            json={"field_ids": ["sentiment_label", "priority"]},
        )
        assert resp.status_code == 200
        assert resp.json() == [
            {"field_id": "sentiment_label", "enabled": True},
            {"field_id": "priority", "enabled": True},
        ]
    finally:
        app.dependency_overrides.clear()


def test_project_fields_locked_after_first_run(monkeypatch):
    """Once a project has a run, its field config is locked."""
    from app.core.dependencies import get_current_user, get_db
    from app.repositories.projects import ProjectRepository

    async def fake_current_user():
        return {"id": "user-1", "email": "a@b.co", "email_verified": True}

    class FakeSession:
        async def scalar(self, stmt):
            return SimpleNamespace(id="project-1", user_id="user-1", name="p")

    async def fake_get_db():
        yield FakeSession()

    async def fake_has_runs(self, project_id):
        return True

    monkeypatch.setattr(ProjectRepository, "has_project_runs", fake_has_runs)
    app.dependency_overrides[get_current_user] = fake_current_user
    app.dependency_overrides[get_db] = fake_get_db
    try:
        client = TestClient(app)
        resp = client.put(
            "/api/v1/projects/project-1/fields",
            json={"field_ids": ["sentiment_label"]},
        )
        assert resp.status_code == 409
        assert resp.json() == {
            "error": {
                "code": "CONFLICT",
                "message": "project fields are locked after the first analysis",
            }
        }
    finally:
        app.dependency_overrides.clear()
