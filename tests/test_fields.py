import pytest

from app.services import fields as fsvc


class FakeSession:
    """Minimal in-memory fake for the fields service operations."""

    def __init__(self):
        self.fields = {}
        self.options = {}
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        from app.models import AnalysisField, AnalysisFieldOption

        for obj in self.added:
            if isinstance(obj, AnalysisField):
                self._store_field(obj)
            elif isinstance(obj, AnalysisFieldOption):
                self.options.setdefault(obj.field_id, []).append(obj.value)
        self.added = []

    def _store_field(self, field):
        self.fields[field.id] = field

    async def get(self, model, pk):
        return self.fields.get(pk)

    async def scalar(self, stmt):
        return None

    async def scalars(self, stmt):
        return AsyncResult([])

    async def execute(self, stmt):
        return None

    async def delete(self, obj):
        if getattr(obj, "id", None) in self.fields:
            del self.fields[obj.id]


class AsyncResult:
    def __init__(self, rows):
        self._rows = rows

    async def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_create_field_auto_generates_slug_id():
    sess = FakeSession()
    field = await fsvc.create_field(
        sess, "u1", name="Customer Pain Point", type="enum", options=["price", "usability"]
    )
    assert field["id"] == "customer_pain_point"
    assert field["name"] == "Customer Pain Point"
    assert field["builtin"] is False
    assert set(field["options"]) == {"price", "usability"}


@pytest.mark.asyncio
async def test_create_field_dedupes_id_with_suffix():
    sess = FakeSession()
    await fsvc.create_field(sess, "u1", name="intent", type="enum")
    second = await fsvc.create_field(sess, "u1", name="intent", type="enum")
    assert second["id"] == "intent_2"


@pytest.mark.asyncio
async def test_delete_field_only_owned():
    sess = FakeSession()
    await fsvc.create_field(sess, "u1", name="My Field", type="string")
    assert await fsvc.delete_field(sess, "u2", "my_field") is False
    assert await fsvc.delete_field(sess, "u1", "my_field") is True
    assert "my_field" not in sess.fields


@pytest.mark.asyncio
async def test_update_field_returns_none_for_unowned():
    sess = FakeSession()
    await fsvc.create_field(sess, "u1", name="My Field", type="string")
    assert await fsvc.update_field(sess, "u2", "my_field", name="Nope") is None
    updated = await fsvc.update_field(sess, "u1", "my_field", name="Renamed", enabled=False)
    assert updated["name"] == "Renamed"
    assert updated["enabled"] is False


def test_slugify():
    assert fsvc._slugify("Customer Pain Point") == "customer_pain_point"
    assert fsvc._slugify("  --!! ") == "custom_field"
    assert fsvc._slugify("A/B Test") == "a_b_test"
