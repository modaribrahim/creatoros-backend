from app.services.chunk_analyzer import (
    _coerce,
    _coerce_enum,
    _normalize_record,
    _strip_fences,
)

FIELDS = [
    {
        "id": "intent",
        "type": "enum",
        "options": ["purchase_intent", "question", "other"],
    },
    {"id": "priority", "type": "int", "options": []},
    {"id": "urgency", "type": "int", "options": []},
    {"id": "sentiment_score", "type": "float", "options": []},
    {"id": "needs_response", "type": "bool", "options": []},
    {"id": "tags", "type": "string_list", "options": []},
]


def test_strip_fences():
    assert _strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_coerce_int_float_bool():
    assert _coerce("3", "int") == 3
    assert _coerce("1.5", "float") == 1.5
    assert _coerce("yes", "bool") is True


def test_coerce_enum_falls_back_to_other():
    assert (
        _coerce_enum("purchase_intent", ["purchase_intent", "question"])
        == "purchase_intent"
    )
    assert _coerce_enum("bogus", ["purchase_intent", "question"]) == "other"


def test_normalize_record_clamps_ints():
    raw = {
        "intent": "purchase_intent",
        "priority": 99,
        "urgency": -5,
        "sentiment_score": "2.5",
        "needs_response": "true",
        "tags": ["a", "b", "c", "d", "e", "f"],
    }
    rec = _normalize_record(raw, FIELDS, 1)
    assert rec["priority"] == 4
    assert rec["urgency"] == 0
    assert rec["sentiment_score"] == 2.5
    assert rec["needs_response"] is True
    assert rec["tags"] == ["a", "b", "c", "d", "e"]
    assert rec["index"] == 1


def test_normalize_record_defaults_for_missing():
    rec = _normalize_record({}, FIELDS, 0)
    assert rec["priority"] == 0
    assert rec["needs_response"] is False
    assert rec["tags"] == []
    assert rec["intent"] is None
