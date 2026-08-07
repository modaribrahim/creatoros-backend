import asyncio

from app.services.search import (
    _comments_block,
    _fields_block,
    generate_plan,
    validate_filters,
)

FIELDS = [
    {
        "id": "intent",
        "type": "enum",
        "options": ["purchase_intent", "question", "other"],
    },
    {
        "id": "sentiment_label",
        "type": "enum",
        "options": ["positive", "negative", "neutral"],
    },
    {"id": "priority", "type": "int", "options": []},
    {"id": "tags", "type": "string_list", "options": []},
]


def test_fields_block_renders_vocab():
    block = _fields_block(FIELDS)
    assert "`intent` (enum)" in block
    assert "purchase_intent" in block


def test_validate_filters_keeps_only_valid():
    filters = [
        {"field": "sentiment_label", "op": "eq", "value": "negative"},
        {"field": "priority", "op": "gte", "value": 3},
        {"field": "sentiment_label", "op": "eq", "value": "nonexistent"},
        {"field": "bogus", "op": "eq", "value": "x"},
        {"field": "intent", "op": "contains", "value": "x"},  # bad op
    ]
    valid = validate_filters(filters, FIELDS)
    assert valid == [
        {"field": "sentiment_label", "op": "eq", "value": "negative"},
        {"field": "priority", "op": "gte", "value": 3.0},
    ]


def test_validate_filters_ignores_non_dict():
    assert validate_filters(["not a dict"], FIELDS) == []


def test_validate_filters_enforces_max_three():
    filters = [
        {"field": field, "op": "eq", "value": value}
        for field, value in [
            ("sentiment_label", "negative"),
            ("intent", "question"),
            ("sentiment_label", "positive"),
            ("intent", "other"),
        ]
    ]
    assert len(validate_filters(filters, FIELDS)) <= 3


def test_generate_plan_parses_llm_json(monkeypatch):
    async def fake_chat(system, user):
        return (
            '{"search_text": "pricing complaints", "filters": '
            '[{"field": "sentiment_label", "op": "eq", "value": "negative"}]}'
        )

    monkeypatch.setattr("app.services.search.chat", fake_chat)
    plan = asyncio.run(generate_plan("show negative comments about pricing", FIELDS))
    assert plan["search_text"] == "pricing complaints"
    assert plan["filters"] == [
        {"field": "sentiment_label", "op": "eq", "value": "negative"}
    ]


def test_generate_plan_tolerates_bad_llm_output(monkeypatch):
    async def fake_chat(system, user):
        return "not json at all"

    monkeypatch.setattr("app.services.search.chat", fake_chat)
    plan = asyncio.run(generate_plan("anything", FIELDS))
    assert plan["search_text"] == ""
    assert plan["filters"] == []


def test_comments_block_numbered():
    hits = [
        {"text": "first", "fields": {"sentiment_label": "negative", "index": 1}},
        {"text": "second", "fields": {"sentiment_label": "positive", "index": 2}},
    ]
    block = _comments_block(hits)
    assert "1. first" in block
    assert "2. second" in block
    assert "index" not in block  # internal index not leaked to the LLM
