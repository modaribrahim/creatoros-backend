from sqlalchemy import delete, select
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


async def seed_fields(session: AsyncSession) -> None:
    if await session.scalar(select(AnalysisField).limit(1)):
        return
    for i, (fid, ftype, options) in enumerate(FIELDS):
        session.add(AnalysisField(id=fid, name=fid, type=ftype, enabled=True, sort=i))
        for value in options:
            session.add(AnalysisFieldOption(field_id=fid, value=value))
    await session.commit()


async def get_fields(session: AsyncSession) -> list[dict]:
    await seed_fields(session)
    fields = (
        await session.scalars(select(AnalysisField).order_by(AnalysisField.sort))
    ).all()
    options = (await session.scalars(select(AnalysisFieldOption))).all()
    by_id: dict[str, list[str]] = {}
    for opt in options:
        by_id.setdefault(opt.field_id, []).append(opt.value)
    return [
        {
            "id": f.id,
            "name": f.name,
            "type": f.type,
            "enabled": f.enabled,
            "options": by_id.get(f.id, []),
        }
        for f in fields
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


async def upsert_field(
    session: AsyncSession,
    field_id: str,
    *,
    name: str | None = None,
    type: str | None = None,
    enabled: bool | None = None,
    options: list[str] | None = None,
) -> None:
    field = await session.get(AnalysisField, field_id)
    if field is None:
        field = AnalysisField(
            id=field_id,
            name=name or field_id,
            type=type or "enum",
            enabled=bool(enabled),
        )
        session.add(field)
    if name is not None:
        field.name = name
    if type is not None:
        field.type = type
    if enabled is not None:
        field.enabled = enabled
    if options is not None:
        await session.execute(
            delete(AnalysisFieldOption).where(AnalysisFieldOption.field_id == field_id)
        )
        for value in options:
            session.add(AnalysisFieldOption(field_id=field_id, value=value))
    await session.commit()


async def delete_field(session: AsyncSession, field_id: str) -> bool:
    field = await session.get(AnalysisField, field_id)
    if field is None:
        return False
    await session.execute(
        delete(AnalysisFieldOption).where(AnalysisFieldOption.field_id == field_id)
    )
    await session.delete(field)
    await session.commit()
    return True
