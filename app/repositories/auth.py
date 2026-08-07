from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import RefreshToken, User


class AuthRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # users ----------------------------------------------------------------
    async def create_user(self, email: str, password_hash: str) -> User:
        user = User(id=str(uuid4()), email=email, password_hash=password_hash)
        self.session.add(user)
        await self.session.commit()
        return user

    async def get_by_email(self, email: str) -> User | None:
        return await self.session.scalar(
            select(User).where(User.email == email.lower())
        )

    async def get_by_id(self, user_id: str) -> User | None:
        return await self.session.get(User, user_id)

    async def set_verification_token(
        self, user: User, token_hash: str, expires_at: datetime
    ) -> None:
        user.verification_token_hash = token_hash
        user.verification_token_expires_at = expires_at
        await self.session.commit()

    async def verify_email(
        self, token_hash: str, now: datetime | None = None
    ) -> User | None:
        now = now or datetime.now(UTC)
        user = await self.session.scalar(
            select(User).where(
                User.verification_token_hash == token_hash,
                User.verification_token_expires_at > now,
            )
        )
        if not user:
            return None
        user.email_verified = True
        user.verification_token_hash = None
        user.verification_token_expires_at = None
        await self.session.commit()
        return user

    # refresh tokens --------------------------------------------------------
    async def create_refresh_token(self, user_id: str, token_hash: str) -> RefreshToken:
        row = RefreshToken(
            id=str(uuid4()),
            user_id=user_id,
            family_id=str(uuid4()),
            token_hash=token_hash,
            expires_at=datetime.now(UTC)
            + timedelta(days=settings.refresh_token_ttl_days),
        )
        self.session.add(row)
        await self.session.commit()
        return row

    async def get_refresh_token(self, token_hash: str) -> RefreshToken | None:
        return await self.session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )

    async def rotate_refresh_token(
        self, old: RefreshToken, new_token_hash: str
    ) -> RefreshToken:
        old.revoked_at = datetime.now(UTC)
        row = RefreshToken(
            id=str(uuid4()),
            user_id=old.user_id,
            family_id=old.family_id,
            token_hash=new_token_hash,
            expires_at=datetime.now(UTC)
            + timedelta(days=settings.refresh_token_ttl_days),
        )
        self.session.add(row)
        await self.session.commit()
        return row

    async def revoke_token(self, token_id: str) -> None:
        row = await self.session.get(RefreshToken, token_id)
        if row and row.revoked_at is None:
            row.revoked_at = datetime.now(UTC)
            await self.session.commit()

    async def revoke_family(self, family_id: str) -> None:
        """Revoke all tokens in a family (reuse detection / logout-all)."""
        await self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None)
            )
            .values(revoked_at=datetime.now(UTC))
        )
        await self.session.commit()
