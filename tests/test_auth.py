from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.config import settings as security_settings
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    UnauthorizedError,
)
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    sha256,
    verify_password,
)
from app.services import auth as auth_service


class FakeUser:
    def __init__(self, email, password_hash):
        self.id = "u1"
        self.email = email
        self.password_hash = password_hash
        self.email_verified = False
        self.verification_token_hash = None
        self.verification_token_expires_at = None
        self.created_at = datetime.now(UTC)


class FakeToken:
    def __init__(self, user_id, token_hash):
        self.id = "t1"
        self.user_id = user_id
        self.family_id = "f1"
        self.token_hash = token_hash
        self.expires_at = datetime.now(UTC) + timedelta(days=30)
        self.revoked_at = None


class FakeAuthRepo:
    def __init__(self):
        self.users: dict[str, FakeUser] = {}
        self.tokens: dict[str, FakeToken] = {}
        self.revoked_families: set[str] = set()

    async def create_user(self, email, password_hash):
        user = FakeUser(email, password_hash)
        self.users[email] = user
        return user

    async def get_by_email(self, email):
        return self.users.get(email.lower())

    async def get_by_id(self, user_id):
        return self.users.get("alice@example.com") if user_id == "u1" else None

    async def set_verification_token(self, user, token_hash, expires_at):
        user.verification_token_hash = token_hash
        user.verification_token_expires_at = expires_at

    async def verify_email(self, token_hash, now=None):
        user = self.users.get("alice@example.com")
        if not user or user.verification_token_hash != token_hash:
            return None
        if user.verification_token_expires_at < (now or datetime.now(UTC)):
            return None
        user.email_verified = True
        return user

    async def create_refresh_token(self, user_id, token_hash):
        row = FakeToken(user_id, token_hash)
        self.tokens[token_hash] = row
        return row

    async def get_refresh_token(self, token_hash):
        return self.tokens.get(token_hash)

    async def rotate_refresh_token(self, old, new_token_hash):
        old.revoked_at = datetime.now(UTC)
        row = FakeToken(old.user_id, new_token_hash)
        row.family_id = old.family_id
        self.tokens[new_token_hash] = row
        return row

    async def revoke_token(self, token_id):
        for row in self.tokens.values():
            if row.id == token_id and row.revoked_at is None:
                row.revoked_at = datetime.now(UTC)

    async def revoke_family(self, family_id):
        for row in self.tokens.values():
            if row.family_id == family_id and row.revoked_at is None:
                row.revoked_at = datetime.now(UTC)


@pytest.fixture(autouse=True)
def _patch_repo(monkeypatch):
    repo = FakeAuthRepo()
    emails = []

    def _factory(session):
        return repo

    monkeypatch.setattr(auth_service, "AuthRepository", _factory)
    monkeypatch.setattr(
        auth_service.mailer,
        "send_verification_email",
        lambda email, link: emails.append(email),
    )
    return SimpleNamespace(repo=repo, emails=emails)


# --- primitives ------------------------------------------------------------


def test_password_hash_roundtrip():
    hashed = hash_password("s3cret-pass")
    assert hashed != "s3cret-pass"
    assert verify_password("s3cret-pass", hashed)
    assert not verify_password("wrong", hashed)


def test_password_hash_verify_garbage_returns_false():
    assert not verify_password("x", "not-a-hash")


def test_sha256_deterministic():
    assert sha256("abc") == sha256("abc")
    assert sha256("abc") != sha256("abd")


def test_access_token_roundtrip():
    token = create_access_token("user-1")
    assert decode_access_token(token) == "user-1"


def test_access_token_tampered_rejected():
    token = create_access_token("user-1")
    assert decode_access_token(token + "x") is None


def test_access_token_expired_rejected(monkeypatch):
    monkeypatch.setattr(security_settings, "access_token_ttl_minutes", -1)
    assert decode_access_token(create_access_token("user-1")) is None


# --- services --------------------------------------------------------------


@pytest.mark.asyncio
async def test_signup_returns_tokens_and_queues_email(_patch_repo):
    resp = await auth_service.signup(None, "alice@example.com", "password123")
    assert resp.user.email == "alice@example.com"
    assert resp.user.email_verified is False
    assert resp.tokens.access_token and resp.tokens.refresh_token
    assert _patch_repo.emails == ["alice@example.com"]
    assert "frontend" in resp.verification_url or resp.verification_url


@pytest.mark.asyncio
async def test_signup_verification_url_only_when_no_mail_provider(
    _patch_repo, monkeypatch
):
    monkeypatch.setattr(auth_service.settings, "resend_api_key", "re_xxxx")
    resp = await auth_service.signup(None, "alice@example.com", "password123")
    assert resp.verification_url is None


@pytest.mark.asyncio
async def test_signup_duplicate_email_conflicts(_patch_repo):
    await auth_service.signup(None, "alice@example.com", "password123")
    with pytest.raises(ConflictError):
        await auth_service.signup(None, "alice@example.com", "password123")


@pytest.mark.asyncio
async def test_login_before_verify_forbidden(_patch_repo):
    await auth_service.signup(None, "alice@example.com", "password123")
    with pytest.raises(ForbiddenError):
        await auth_service.login(None, "alice@example.com", "password123")


@pytest.mark.asyncio
async def test_login_wrong_password_rejected(_patch_repo):
    await auth_service.signup(None, "alice@example.com", "password123")
    _patch_repo.repo.users["alice@example.com"].email_verified = True
    with pytest.raises(UnauthorizedError):
        await auth_service.login(None, "alice@example.com", "wrong-password")


@pytest.mark.asyncio
async def test_verify_email_then_login(_patch_repo):
    await auth_service.signup(None, "alice@example.com", "password123")
    repo = _patch_repo.repo
    token = "secret-token"
    repo.users["alice@example.com"].verification_token_hash = sha256(token)
    result = await auth_service.verify_email(None, token)
    assert result["message"] == "email verified"
    assert repo.users["alice@example.com"].email_verified is True
    resp = await auth_service.login(None, "alice@example.com", "password123")
    assert resp.user.email_verified is True


@pytest.mark.asyncio
async def test_verify_email_bad_token(_patch_repo):
    with pytest.raises(Exception) as excinfo:
        await auth_service.verify_email(None, "nope")
    assert excinfo.value.__class__.__name__ == "BadRequestError"


@pytest.mark.asyncio
async def test_refresh_rotates_and_reuse_detected(_patch_repo):
    resp = await auth_service.signup(None, "alice@example.com", "password123")
    old = resp.tokens.refresh_token
    new = await auth_service.refresh(None, old)
    assert new.refresh_token != old
    with pytest.raises(UnauthorizedError):
        await auth_service.refresh(None, old)


@pytest.mark.asyncio
async def test_refresh_unknown_token_rejected(_patch_repo):
    with pytest.raises(UnauthorizedError):
        await auth_service.refresh(None, "unknown-token")


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(_patch_repo):
    resp = await auth_service.signup(None, "alice@example.com", "password123")
    token = resp.tokens.refresh_token
    await auth_service.logout(None, token)
    with pytest.raises(UnauthorizedError):
        await auth_service.refresh(None, token)


@pytest.mark.asyncio
async def test_me_returns_user(_patch_repo):
    await auth_service.signup(None, "alice@example.com", "password123")
    user = await auth_service.get_user(None, "u1")
    assert user.email == "alice@example.com"
