import re

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisField, AnalysisFieldOption

FIELDS: list[tuple[str, str, list[str]]] = [
    (
        "intent",
        "enum",
        [
            "purchase_intent",
            "interested",
            "question",
            "feature_request",
            "complaint",
            "support",
            "promotion",
            "unrelated",
            "other",
        ],
    ),
    ("intent_strength", "float", []),
    (
        "sentiment_label",
        "enum",
        ["positive", "negative", "neutral", "mixed"],
    ),
    ("sentiment_score", "float", []),
    (
        "primary_topic",
        "enum",
        [
            "feature",
            "pricing",
            "performance",
            "ui_ux",
            "bug",
            "content",
            "documentation",
            "support",
            "accessibility",
            "integration",
            "competition",
            "monetization",
            "other",
        ],
    ),
    (
        "tags",
        "string_list",
        [
            "dark_mode",
            "subscription",
            "discount",
            "crash",
            "export",
            "api",
            "mobile",
            "desktop",
            "web",
            "login",
            "sync",
            "privacy",
            "speed",
            "templates",
            "collaboration",
        ],
    ),
    ("priority", "int", []),
    ("needs_response", "bool", []),
    ("is_creator_relevant", "bool", []),
    ("platform_context", "enum", ["mobile", "desktop", "web", "unknown"]),
    ("monetization_signal", "bool", []),
    ("churn_risk", "enum", ["low", "medium", "high", "na"]),
    ("user_role", "enum", ["creator", "viewer", "brand", "unknown"]),
    (
        "objection",
        "enum",
        ["price", "trust", "usability", "performance", "competition", "none"],
    ),
    (
        "buying_stage",
        "enum",
        ["awareness", "consideration", "decision", "retention", "na"],
    ),
    ("urgency", "int", []),
    ("mentions_competitor", "bool", []),
    ("competitor_names", "string_list", []),
    ("key_entities", "string_list", []),
    ("topical_focus", "string", []),
]

TYPE_CHOICES = {"enum", "int", "float", "bool", "string", "string_list"}


async def seed_fields(session: AsyncSession) -> None:
    if await session.scalar(select(AnalysisField).limit(1)):
        return
    for i, (fid, ftype, options) in enumerate(FIELDS):
        session.add(AnalysisField(id=fid, name=fid, type=ftype, enabled=True, sort=i))
        for value in options:
            session.add(AnalysisFieldOption(field_id=fid, value=value))
    await session.commit()


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return (slug or "custom_field")[:64]


async def _next_sort(session: AsyncSession) -> int:
    max_sort = await session.scalar(
        select(AnalysisField.sort).order_by(AnalysisField.sort.desc()).limit(1)
    )
    return (max_sort or 0) + 1


async def _field_dict(field: AnalysisField, options: list[str]) -> dict:
    return {
        "id": field.id,
        "name": field.name,
        "type": field.type,
        "enabled": field.enabled,
        "options": options,
        "builtin": field.user_id is None,
    }


async def get_fields(session: AsyncSession, user_id: str | None = None) -> list[dict]:
    await seed_fields(session)
    fields = (
        await session.scalars(
            select(AnalysisField)
            .where(or_(AnalysisField.user_id.is_(None), AnalysisField.user_id == user_id))
            .order_by(AnalysisField.sort, AnalysisField.name)
        )
    ).all()
    options = (await session.scalars(select(AnalysisFieldOption))).all()
    by_id: dict[str, list[str]] = {}
    for opt in options:
        by_id.setdefault(opt.field_id, []).append(opt.value)
    return [
        await _field_dict(f, by_id.get(f.id, [])) for f in fields
    ]


async def get_enabled_filters(session: AsyncSession) -> list[str]:
    await seed_fields(session)
    return list(
        (
            await session.scalars(
                select(AnalysisField.id).where(AnalysisField.enabled.is_(True))
            )
        ).all()
    )


async def create_field(
    session: AsyncSession,
    user_id: str,
    *,
    name: str,
    type: str,
    enabled: bool = True,
    options: list[str] | None = None,
) -> dict:
    if type not in TYPE_CHOICES:
        raise ValueError(f"invalid field type: {type}")
    options = options or []
    base = _slugify(name)
    field_id = base
    suffix = 2
    while await session.get(AnalysisField, field_id) is not None:
        field_id = f"{base}_{suffix}"
        suffix += 1
    field = AnalysisField(
        id=field_id,
        name=name,
        type=type,
        enabled=enabled,
        sort=await _next_sort(session),
        user_id=user_id,
    )
    session.add(field)
    for value in options:
        session.add(AnalysisFieldOption(field_id=field_id, value=value))
    await session.commit()
    return await _field_dict(field, options)


async def get_owned_field(
    session: AsyncSession, user_id: str, field_id: str
) -> AnalysisField | None:
    field = await session.get(AnalysisField, field_id)
    if field is not None and field.user_id == user_id:
        return field
    return None


async def update_field(
    session: AsyncSession,
    user_id: str,
    field_id: str,
    *,
    name: str | None = None,
    type: str | None = None,
    enabled: bool | None = None,
    options: list[str] | None = None,
) -> dict | None:
    field = await get_owned_field(session, user_id, field_id)
    if field is None:
        return None
    if name is not None:
        field.name = name
    if type is not None:
        if type not in TYPE_CHOICES:
            raise ValueError(f"invalid field type: {type}")
        field.type = type
    if enabled is not None:
        field.enabled = enabled
    if options is not None:
        await session.execute(
            delete(AnalysisFieldOption).where(AnalysisFieldOption.field_id == field_id)
        )
        for value in options:
            if value:
                session.add(AnalysisFieldOption(field_id=field_id, value=value))
    await session.commit()
    return await _field_dict(field, options or [])


async def delete_field(session: AsyncSession, user_id: str, field_id: str) -> bool:
    field = await get_owned_field(session, user_id, field_id)
    if field is None:
        return False
    await session.execute(
        delete(AnalysisFieldOption).where(AnalysisFieldOption.field_id == field_id)
    )
    await session.delete(field)
    await session.commit()
    return True
