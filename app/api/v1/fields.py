from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import BadRequestError, NotFoundError
from app.schemas.field import FieldCreate, FieldOut, FieldUpdate
from app.services.fields import (
    create_field,
    delete_field,
    get_fields,
    update_field,
)

router = APIRouter(prefix="/api/v1")


@router.get("/fields", response_model=list[FieldOut])
async def list_fields(
    session: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Available fields: shared built-ins + the caller's custom fields."""
    return await get_fields(session, user["id"])


@router.post("/fields", response_model=FieldOut, status_code=201)
async def add_field(
    body: FieldCreate,
    session: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Create a custom field. The id is generated automatically from the name."""
    try:
        return await create_field(
            session,
            user["id"],
            name=body.name,
            type=body.type,
            enabled=body.enabled,
            options=body.options,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc))


@router.put("/fields/{field_id}", response_model=FieldOut)
async def modify_field(
    field_id: str,
    body: FieldUpdate,
    session: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        field = await update_field(
            session,
            user["id"],
            field_id,
            name=body.name,
            type=body.type,
            enabled=body.enabled,
            options=body.options,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc))
    if field is None:
        raise NotFoundError("field not found or not owned by you")
    return field


@router.delete("/fields/{field_id}")
async def remove_field(
    field_id: str,
    session: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    if not await delete_field(session, user["id"], field_id):
        raise NotFoundError("field not found or not owned by you")
    return {"deleted": field_id}
