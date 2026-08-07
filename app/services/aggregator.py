from collections import Counter, defaultdict


def aggregate_records(records: list[dict], field_ids: list[str]) -> dict:
    agg: dict = {}

    for field in field_ids:
        agg[field] = aggregate_field(records, field)

    agg["comment_count"] = len(records)
    agg["avg_sentiment_score"] = _avg_signal(records, "sentiment_score")
    agg["high_priority_count"] = sum(1 for r in records if r.get("priority", 0) >= 3)
    agg["needs_response_count"] = sum(1 for r in records if r.get("needs_response"))
    agg["churn_risk_count"] = sum(1 for r in records if r.get("churn_risk") == "high")
    agg["purchase_intent_count"] = sum(
        1 for r in records if r.get("intent") == "purchase_intent"
    )
    agg["opportunities"] = _top_opportunities(records)

    agg["availability"] = {f: sum(1 for r in records if f in r) for f in field_ids}
    agg["coverage"] = {
        f: (
            round(sum(1 for r in records if f in r) / len(records), 4)
            if records
            else 1.0
        )
        for f in field_ids
    }
    return agg


def aggregate_field(records: list[dict], field: str) -> dict:
    counter: Counter = Counter()
    for r in records:
        value = r.get(field)
        if isinstance(value, list):
            for v in value:
                if v is not None:
                    counter[str(v)] += 1
        elif value is not None:
            counter[str(value)] += 1
    return dict(counter.most_common())


def _avg_signal(records: list[dict], field: str) -> float | None:
    vals = [r[field] for r in records if isinstance(r.get(field), (int, float))]
    return round(sum(vals) / len(vals), 4) if vals else None


def _top_opportunities(records: list[dict], top: int = 3) -> list[int]:
    scored = []
    for i, r in enumerate(records):
        if r.get("intent") in ("feature_request", "purchase_intent") or (
            r.get("intent") == "complaint" and r.get("priority", 0) >= 2
        ):
            score = float(r.get("intent_strength", 0) or 0) + float(
                r.get("priority", 0) or 0
            )
            scored.append((score, i))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [i for _, i in scored[:top]]


def cross_tab(records: list[dict], row_field: str, col_field: str) -> dict:
    tab = defaultdict(lambda: defaultdict(int))
    for r in records:
        row = r.get(row_field)
        col = r.get(col_field)
        if row is None or col is None:
            continue
        tab[str(row)][str(col)] += 1
    return {k: dict(v) for k, v in tab.items()}
