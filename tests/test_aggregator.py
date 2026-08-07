from app.services.aggregator import aggregate_field, aggregate_records, cross_tab

FIELDS = ["intent", "priority", "needs_response", "churn_risk"]

RECORDS = [
    {
        "intent": "purchase_intent",
        "priority": 4,
        "needs_response": True,
        "churn_risk": "low",
    },
    {"intent": "question", "priority": 2, "needs_response": True, "churn_risk": "high"},
    {"intent": "question", "priority": 1, "needs_response": False, "churn_risk": "na"},
]


def test_aggregate_field_counts_enum_values():
    assert aggregate_field(RECORDS, "intent") == {"question": 2, "purchase_intent": 1}


def test_aggregate_records_summaries():
    agg = aggregate_records(RECORDS, FIELDS)
    assert agg["comment_count"] == 3
    assert agg["high_priority_count"] == 1
    assert agg["needs_response_count"] == 2
    assert agg["churn_risk_count"] == 1
    assert agg["purchase_intent_count"] == 1


def test_aggregate_records_availability_and_coverage():
    agg = aggregate_records(RECORDS, FIELDS)
    assert agg["availability"]["intent"] == 3
    assert agg["coverage"]["intent"] == 1.0


def test_aggregate_records_avg_sentiment_skips_missing():
    records = [
        {"sentiment_score": 1.0},
        {"sentiment_score": 3.0},
        {"sentiment_score": None},
    ]
    assert aggregate_records(records, [])["avg_sentiment_score"] == 2.0


def test_cross_tab():
    tab = cross_tab(RECORDS, "intent", "needs_response")
    assert tab["question"]["True"] == 1
    assert tab["question"]["False"] == 1
