"""Unit tests for get_run_status tool."""
import os

os.environ["IBD_TESTING"] = "true"

from tools import get_run_status


def test_get_run_status_with_run_id():
    """get_run_status should return a dict for a specific run_id."""
    result = get_run_status.invoke({"run_id": "run-test-001"})
    assert isinstance(result, dict)
    assert result["run_id"] == "run-test-001"
    assert "status" in result
    assert "total_processed" in result


def test_get_run_status_without_run_id():
    """get_run_status should return latest run status when no run_id supplied."""
    result = get_run_status.invoke({})
    assert isinstance(result, dict)
    assert "status" in result
    assert "coverage_pct" in result


def test_get_run_status_has_required_fields():
    """get_run_status result must contain all required tracking fields."""
    result = get_run_status.invoke({"run_id": "run-abc"})
    required = {"run_id", "status", "total_processed", "seasonal_count",
                "non_seasonal_count", "insufficient_data_count", "coverage_pct"}
    assert required.issubset(set(result.keys()))
