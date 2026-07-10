"""Tests for webservice list sorting helpers."""

from flowcept.webservice.services.sorting import sort_docs_by_first_date_field


def test_sort_docs_uses_later_fallback_timestamp_per_document():
    """A doc missing utc_timestamp still sorts by started_at against older utc_timestamp docs."""
    docs = [
        {"workflow_id": "old", "utc_timestamp": 100},
        {"workflow_id": "new", "started_at": 200},
    ]

    sorted_docs = sort_docs_by_first_date_field(docs, ["utc_timestamp", "started_at"])

    assert [doc["workflow_id"] for doc in sorted_docs] == ["new", "old"]
