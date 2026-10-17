"""Unit tests for persist_classifications tool."""
import os

os.environ["IBD_TESTING"] = "true"

from tools import persist_classifications


def test_persist_classifications_returns_confirmation():
    """persist_classifications should return a confirmation dict with run_id and record_count."""
    classifications = [
        {"article_id": "ART001", "store_id": "S001", "classification": "SEASONAL", "confidence_score": 85.0},
        {"article_id": "ART002", "store_id": "S001", "classification": "NON_SEASONAL", "confidence_score": 72.0},
    ]
    result = persist_classifications.invoke({
        "run_id": "run-test-001",
        "classifications": classifications,
        "run_metadata": {
            "start_time": "2026-10-07T14:00:00Z",
            "end_time": "2026-10-07T14:30:00Z",
            "total_processed": 2,
            "coverage_pct": 100.0,
        },
    })
    assert result["run_id"] == "run-test-001"
    assert result["record_count"] == 2
    assert result["status"] == "persisted"


def test_persist_empty_classifications():
    """persist_classifications handles empty list gracefully."""
    result = persist_classifications.invoke({
        "run_id": "run-empty",
        "classifications": [],
        "run_metadata": {"start_time": "2026-10-07T14:00:00Z", "end_time": "2026-10-07T14:01:00Z", "total_processed": 0, "coverage_pct": 0.0},
    })
    assert result["record_count"] == 0
    assert result["run_id"] == "run-empty"
