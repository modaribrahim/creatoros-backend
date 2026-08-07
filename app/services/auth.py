from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)
from app.core.security import (
    create_access_token,
    generate_token,
    hash_password,
    sha256,
    verify_password,
)
from app.repositories.auth import AuthRepository
from app.schemas.auth import AuthResponse, TokenPair, UserOut
from app.services import mailer


def _user_out(user) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        email_verified=user.email_verified,
        created_at=user.created_at,
    )


def _token_pair(user_id: str, refresh_token: str) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user_id), refresh_token=refresh_token
    )


def _verification_link(token: str) -> str:
    return f"{settings.frontend_url}/verify?token={token}"


async def signup(session: AsyncSession, email: str, password: str) -> AuthResponse:
    repo = AuthRepository(session)
    if await repo.get_by_email(email):
        raise ConflictError("an account with this email already exists")
    user = await repo.create_user(email, hash_password(password))
    token = generate_token()
    await repo.set_verification_token(
        user,
        sha256(token),
        datetime.now(UTC) + timedelta(hours=settings.verification_token_ttl_hours),
    )
    verification_link = _verification_link(token)
    mailer.send_verification_email(email, verification_link)
    # In dev (no mail provider) return the link so the demo is usable without a
    # real email: the frontend can show it. In prod it is sent by email only.
    verification_url = verification_link if not settings.resend_api_key else None
    refresh_token = generate_token()
    await repo.create_refresh_token(user.id, sha256(refresh_token))
    return AuthResponse(
        user=_user_out(user),
        tokens=_token_pair(user.id, refresh_token),
        verification_url=verification_url,
    )


async def login(session: AsyncSession, email: str, password: str) -> AuthResponse:
    repo = AuthRepository(session)
    user = await repo.get_by_email(email)
    if not user or not verify_password(password, user.password_hash):
        raise UnauthorizedError("invalid email or password")
    # if not user.email_verified:
    #     raise ForbiddenError("email not verified; check your inbox")
    refresh_token = generate_token()
    await repo.create_refresh_token(user.id, sha256(refresh_token))
    return AuthResponse(
        user=_user_out(user), tokens=_token_pair(user.id, refresh_token)
    )


async def verify_email(session: AsyncSession, token: str) -> dict[str, str]:
    repo = AuthRepository(session)
    user = await repo.verify_email(sha256(token))
    if not user:
        raise BadRequestError("verification token is invalid or expired")
    return {"message": "email verified"}


async def refresh(session: AsyncSession, raw_token: str) -> TokenPair:
    repo = AuthRepository(session)
    row = await repo.get_refresh_token(sha256(raw_token))
    if not row:
        raise UnauthorizedError("invalid refresh token")
    if row.revoked_at is not None:
        await repo.revoke_family(row.family_id)
        raise UnauthorizedError("refresh token is no longer valid")
    if row.expires_at < datetime.now(UTC):
        raise UnauthorizedError("refresh token expired")
    new_token = generate_token()
    await repo.rotate_refresh_token(row, sha256(new_token))
    return _token_pair(row.user_id, new_token)


async def logout(session: AsyncSession, raw_token: str) -> None:
    repo = AuthRepository(session)
    row = await repo.get_refresh_token(sha256(raw_token))
    if row and row.revoked_at is None:
        await repo.revoke_token(row.id)


async def get_user(session: AsyncSession, user_id: str) -> UserOut:
    repo = AuthRepository(session)
    user = await repo.get_by_id(user_id)
    if not user:
        raise NotFoundError("user not found")
    return _user_out(user)
