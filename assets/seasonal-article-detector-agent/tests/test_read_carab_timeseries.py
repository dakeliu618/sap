"""Unit tests for read_carab_timeseries tool."""
import os

os.environ["IBD_TESTING"] = "true"

from tools import read_carab_timeseries


def test_read_carab_timeseries_returns_list():
    """read_carab_timeseries should return a list."""
    result = read_carab_timeseries.invoke({
        "article_ids": ["ART001", "ART002"],
        "store_ids": ["S001"],
        "start_date": "2022-01-01",
        "end_date": "2024-12-31",
        "granularity": "weekly",
    })
    assert isinstance(result, list)


def test_read_carab_timeseries_default_granularity():
    """read_carab_timeseries works without explicit granularity."""
    result = read_carab_timeseries.invoke({
        "article_ids": ["ART001"],
        "store_ids": ["S001"],
        "start_date": "2022-01-01",
        "end_date": "2024-12-31",
    })
    assert isinstance(result, list)
