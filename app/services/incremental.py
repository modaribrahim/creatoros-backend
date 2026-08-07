from app.core.config import settings


def like_changed(old: int, new: int, pct: float | None = None) -> bool:
    """A comment needs re-analysis if its like count moved meaningfully.

    Threshold is the larger of 1 like or `pct`% of the old value.
    """
    pct = pct or settings.like_change_pct
    return abs(new - old) >= max(1, int(old * pct))


def plan_incremental(
    fetched: list[dict],
    analyzed_ids: set[str],
    stored_likes: dict[str, int],
    pct: float | None = None,
) -> dict:
    """Partition freshly fetched comments into what to (re)analyze vs reuse.

    Returns counts plus the comment ids to analyze:
      new_ids      comments never analyzed for this project
      changed_ids  comments already analyzed but whose like count moved
      reuse_ids    comments already analyzed, unchanged -> reuse records
    """
    new_ids, changed_ids, reuse_ids = [], [], []
    for comment in fetched:
        cid = comment["comment_id"]
        if cid not in analyzed_ids:
            new_ids.append(cid)
        elif like_changed(stored_likes.get(cid, 0), comment.get("like_count", 0), pct):
            changed_ids.append(cid)
        else:
            reuse_ids.append(cid)
    return {
        "new_ids": new_ids,
        "changed_ids": changed_ids,
        "reuse_ids": reuse_ids,
        "to_analyze": new_ids + changed_ids,
    }
