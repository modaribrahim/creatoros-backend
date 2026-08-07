from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import UnauthorizedError
from app.core.security import decode_access_token
from app.repositories.auth import AuthRepository

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError("missing bearer token")
    user_id = decode_access_token(credentials.credentials)
    if not user_id:
        raise UnauthorizedError("invalid or expired token")
    user = await AuthRepository(db).get_by_id(user_id)
    if not user:
        raise UnauthorizedError("user no longer exists")
    return {
        "id": user.id,
        "email": user.email,
        "email_verified": user.email_verified,
    }
