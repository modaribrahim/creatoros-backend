import pytest

from app.repositories.projects import _cosine, _filter_clause, _similarity_fn


def test_cosine_similarity():
    a = [1.0, 0.0]
    b = [1.0, 0.0]
    c = [0.0, 1.0]
    assert _cosine(a, b) == pytest.approx(1.0)
    assert _cosine(a, c) == pytest.approx(0.0)


def test_similarity_fn_scores():
    score = _similarity_fn([1.0, 0.0])
    assert score([1.0, 0.0]) == pytest.approx(1.0)
    assert score(None) == 0.0


def test_filter_clause_eq():
    clause = _filter_clause(
        {"field": "sentiment_label", "op": "eq", "value": "negative"}
    )
    sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
    assert "sentiment_label" in sql
    assert "'negative'" in sql
    assert "JSONB" in sql


def test_filter_clause_gte():
    clause = _filter_clause({"field": "priority", "op": "gte", "value": 3})
    sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
    assert ">=" in sql
