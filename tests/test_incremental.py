from app.services.incremental import like_changed, plan_incremental


def _comments(*ids_likes):
    return [{"comment_id": cid, "like_count": likes} for cid, likes in ids_likes]


def test_like_changed_threshold():
    assert like_changed(old=100, new=120, pct=0.2)  # +20% = re-analyze
    assert not like_changed(old=100, new=105, pct=0.2)  # +5% = reuse
    assert like_changed(old=0, new=1, pct=0.2)  # absolute floor of 1
    assert not like_changed(old=1000, new=1000, pct=0.2)  # identical


def test_plan_incremental_partitions_correctly():
    fetched = _comments(
        ("c1", 100),  # new
        ("c2", 500),  # existing, changed
        ("c3", 50),  # existing, unchanged
        ("c4", 999),  # new
    )
    plan = plan_incremental(
        fetched,
        analyzed_ids={"c2", "c3"},
        stored_likes={"c2": 300, "c3": 50},
        pct=0.2,
    )
    assert plan["new_ids"] == ["c1", "c4"]
    assert plan["changed_ids"] == ["c2"]
    assert plan["reuse_ids"] == ["c3"]
    assert plan["to_analyze"] == ["c1", "c4", "c2"]


def test_plan_incremental_all_new():
    fetched = _comments(("c1", 0), ("c2", 5))
    plan = plan_incremental(fetched, analyzed_ids=set(), stored_likes={})
    assert plan["new_ids"] == ["c1", "c2"]
    assert plan["reuse_ids"] == []


def test_plan_incremental_all_reuse():
    fetched = _comments(("c1", 10), ("c2", 20))
    plan = plan_incremental(
        fetched,
        analyzed_ids={"c1", "c2"},
        stored_likes={"c1": 10, "c2": 20},
    )
    assert plan["new_ids"] == []
    assert plan["changed_ids"] == []
    assert plan["reuse_ids"] == ["c1", "c2"]
    assert plan["to_analyze"] == []
