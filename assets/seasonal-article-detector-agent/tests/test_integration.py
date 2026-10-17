"""Integration test: end-to-end agent flow with mocked LLM and tools."""
import math
import os
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

os.environ["IBD_TESTING"] = "true"
# Ensure CF code path (no JOULE_RUNTIME)
os.environ.pop("JOULE_RUNTIME", None)

from agent import SampleAgent
from tools import (
    get_classification_results,
    get_run_status,
    persist_classifications,
    read_carab_timeseries,
    run_seasonality_detection,
)


def _make_seasonal_ts(n_years: int = 3) -> list[dict]:
    records = []
    for week in range(n_years * 52):
        year_week = week % 52
        base = 100.0
        seasonal = 800.0 * math.exp(-((year_week - 50) ** 2) / 8) if year_week >= 47 else 0.0
        noise = np.random.default_rng(week).normal(0, 5)
        records.append({
            "article_id": "ART_XMAS",
            "store_id": "S001",
            "date": f"202{week // 52 + 2}-01-{(week % 28) + 1:02d}",
            "sales_quantity": max(0.0, base + seasonal + noise),
            "sales_value": max(0.0, (base + seasonal + noise) * 15.0),
        })
    return records


@pytest.mark.asyncio
async def test_agent_classification_run_flow():
    """Integration test: agent receives a classification request end-to-end.

    On CF the LLM is initialised lazily via aicore.init_llm_from_destination.
    We patch _invoke_with_fallback so no real network calls are made.
    """
    agent = SampleAgent()

    custom_tools = [
        read_carab_timeseries,
        run_seasonality_detection,
        persist_classifications,
        get_classification_results,
        get_run_status,
    ]

    mock_response = MagicMock()
    mock_response.content = "Classification run completed. 1 seasonal article detected for store S001."

    with patch.object(agent, "_invoke_with_fallback", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = {"messages": [mock_response]}

        response = await agent.invoke(
            query="Run seasonal classification for articles in store S001",
            context_id="test-context-001",
            tools=custom_tools,
        )

    assert response.status == "completed"
    assert response.message is not None
    assert len(response.message) > 0


@pytest.mark.asyncio
async def test_seasonality_detection_pipeline():
    """Integration test: verify the full detection pipeline produces correct results."""
    ts_data = _make_seasonal_ts(n_years=3)
    assert len(ts_data) == 3 * 52

    results = run_seasonality_detection.invoke({"timeseries_data": ts_data})
    assert len(results) == 1
    r = results[0]
    assert r["classification"] in ("SEASONAL", "LOW_CONFIDENCE_SEASONAL")
    assert r["article_id"] == "ART_XMAS"
    assert r["store_id"] == "S001"

    persist_result = persist_classifications.invoke({
        "run_id": "integration-run-001",
        "classifications": results,
        "run_metadata": {
            "start_time": "2026-10-07T14:00:00Z",
            "end_time": "2026-10-07T14:05:00Z",
            "total_processed": 1,
            "coverage_pct": 100.0,
        },
    })
    assert persist_result["run_id"] == "integration-run-001"
    assert persist_result["record_count"] == 1
    assert persist_result["status"] == "persisted"

    query_result = get_classification_results.invoke({"filters": {"classification": "SEASONAL"}})
    assert isinstance(query_result, list)

    status = get_run_status.invoke({"run_id": "integration-run-001"})
    assert isinstance(status, dict)
    assert "status" in status
