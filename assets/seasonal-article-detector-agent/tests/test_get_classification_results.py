"""Unit tests for get_classification_results tool."""
import os

os.environ["IBD_TESTING"] = "true"

from tools import get_classification_results


def test_get_classification_results_returns_list():
    """get_classification_results should return a list."""
    result = get_classification_results.invoke({"filters": {"classification": "SEASONAL"}})
    assert isinstance(result, list)


def test_get_classification_results_no_filters():
    """get_classification_results works without filters."""
    result = get_classification_results.invoke({})
    assert isinstance(result, list)


def test_get_classification_results_with_min_confidence_filter():
    """get_classification_results accepts a min_confidence filter."""
    result = get_classification_results.invoke({"filters": {"min_confidence": 80.0}})
    assert isinstance(result, list)
