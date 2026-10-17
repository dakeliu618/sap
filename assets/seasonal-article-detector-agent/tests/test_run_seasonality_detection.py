"""Unit tests for run_seasonality_detection tool."""
import math
import os

import numpy as np

os.environ["IBD_TESTING"] = "true"

from tools import run_seasonality_detection


def _make_seasonal_ts(article_id: str, store_id: str, n_years: int = 3) -> list[dict]:
    """Generates a synthetic strongly-seasonal time-series (Christmas spike weeks 48-52)."""
    records = []
    for week in range(n_years * 52):
        year_week = week % 52
        # Strong spike in weeks 48-52 (Christmas season)
        base = 100.0
        seasonal = 800.0 * math.exp(-((year_week - 50) ** 2) / 8) if year_week >= 47 else 0.0
        noise = np.random.default_rng(week).normal(0, 5)
        date = f"2022-W{week // 52 + 1:02d}-{(week % 52) + 1:02d}"
        records.append({
            "article_id": article_id,
            "store_id": store_id,
            "date": f"2022-01-{(week % 28) + 1:02d}",
            "sales_quantity": max(0, base + seasonal + noise),
            "sales_value": max(0, (base + seasonal + noise) * 15.0),
        })
    return records


def _make_flat_ts(article_id: str, store_id: str, n_years: int = 3) -> list[dict]:
    """Generates a flat (non-seasonal) time-series."""
    records = []
    rng = np.random.default_rng(42)
    for week in range(n_years * 52):
        records.append({
            "article_id": article_id,
            "store_id": store_id,
            "date": f"2022-01-{(week % 28) + 1:02d}",
            "sales_quantity": float(100 + rng.normal(0, 5)),
            "sales_value": float(1500 + rng.normal(0, 50)),
        })
    return records


def test_seasonal_article_classified_correctly():
    """A strongly seasonal article should receive SEASONAL or LOW_CONFIDENCE_SEASONAL classification."""
    data = _make_seasonal_ts("ART_SEASONAL", "S001", n_years=3)
    results = run_seasonality_detection.invoke({"timeseries_data": data})

    assert len(results) == 1
    r = results[0]
    assert r["article_id"] == "ART_SEASONAL"
    assert r["store_id"] == "S001"
    assert r["classification"] in ("SEASONAL", "LOW_CONFIDENCE_SEASONAL")
    assert r["seasonal_strength_index"] >= 0.4
    assert r["confidence_score"] >= 0.0
    assert r["algorithm_used"] == "stl"


def test_flat_article_classified_non_seasonal():
    """A flat time-series should receive NON_SEASONAL classification."""
    data = _make_flat_ts("ART_FLAT", "S001", n_years=3)
    results = run_seasonality_detection.invoke({"timeseries_data": data})

    assert len(results) == 1
    r = results[0]
    assert r["classification"] == "NON_SEASONAL"


def test_insufficient_data_classification():
    """An article with less than 2 years of data should be INSUFFICIENT_DATA."""
    data = _make_seasonal_ts("ART_SHORT", "S001", n_years=1)  # only 1 year
    results = run_seasonality_detection.invoke({
        "timeseries_data": data,
        "config": {"min_data_years": 2},
    })
    assert len(results) == 1
    assert results[0]["classification"] == "INSUFFICIENT_DATA"


def test_multiple_articles_returned_separately():
    """Multiple article/store combos should each produce their own classification."""
    data = (
        _make_seasonal_ts("ART1", "S001", n_years=3)
        + _make_flat_ts("ART2", "S001", n_years=3)
    )
    results = run_seasonality_detection.invoke({"timeseries_data": data})
    assert len(results) == 2
    ids = {r["article_id"] for r in results}
    assert ids == {"ART1", "ART2"}


def test_empty_input_returns_empty():
    """Empty input should return empty list."""
    results = run_seasonality_detection.invoke({"timeseries_data": []})
    assert results == []


def test_result_has_required_fields():
    """Each classification result must contain all required output fields."""
    data = _make_seasonal_ts("ART001", "S001", n_years=3)
    results = run_seasonality_detection.invoke({"timeseries_data": data})
    required_fields = {
        "article_id", "store_id", "classification", "confidence_score",
        "season_start_week", "season_end_week", "seasonal_strength_index",
        "algorithm_used", "data_range_start", "data_range_end",
    }
    assert required_fields.issubset(set(results[0].keys()))
