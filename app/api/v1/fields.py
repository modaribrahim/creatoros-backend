from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import BadRequestError, NotFoundError
from app.schemas.field import FieldOut, FieldUpdate
from app.services.fields import delete_field, get_fields, upsert_field

router = APIRouter(prefix="/api/v1")

CORE_FIELDS = ("intent",)


@router.get("/fields", response_model=list[FieldOut])
async def fields(session: AsyncSession = Depends(get_db)):
    return await get_fields(session)


@router.put("/fields", response_model=list[FieldOut])
async def update_field(update: FieldUpdate, session: AsyncSession = Depends(get_db)):
    if update.id in CORE_FIELDS:
        raise BadRequestError(f"cannot modify core field '{update.id}'")
    await upsert_field(
        session,
        update.id,
        name=update.name,
        type=update.type,
        enabled=update.enabled,
        options=update.options,
    )
    return await get_fields(session)


@router.delete("/fields/{field_id}")
async def remove_field(field_id: str, session: AsyncSession = Depends(get_db)):
    if field_id in CORE_FIELDS:
        raise BadRequestError(f"cannot delete core field '{field_id}'")
    if not await delete_field(session, field_id):
        raise NotFoundError("field not found")
    return {"deleted": field_id}
