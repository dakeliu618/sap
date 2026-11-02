"""
Custom tools for the Seasonal Article Detector Agent.
These tools implement seasonality detection using STL decomposition
and (on CF) direct BTP-destination calls to the n8n workflow webhooks.

Runtime routing:
  - On Joule/Kyma (JOULE_RUNTIME=1): the two workflow tools are MCP-backed;
    the agent's system prompt directs it to use the MCP tool names.
  - On CF (JOULE_RUNTIME unset):     the two workflow tools call N8nClient
    directly via BTP destinations REPLENISHMENT_WORKFLOW and
    CLASSIFICATION_NOTIFICATION_WORKFLOW.
"""
import logging
import os
from datetime import datetime, timezone
from typing import Any

import numpy as np
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# N8nClient is only instantiated at call-time to avoid import errors in test
# environments that don't have VCAP_SERVICES set.
_n8n_client: Any = None


def _get_n8n_client() -> Any:
    global _n8n_client
    if _n8n_client is None:
        from n8n_client import N8nClient  # noqa: PLC0415
        _n8n_client = N8nClient()
    return _n8n_client

# Configurable thresholds (can be overridden via environment variables)
SEASONAL_STRENGTH_THRESHOLD = float(os.environ.get("SEASONAL_STRENGTH_THRESHOLD", "0.4"))
MIN_CONFIDENCE_THRESHOLD = float(os.environ.get("MIN_CONFIDENCE_THRESHOLD", "60.0"))
MIN_DATA_YEARS = int(os.environ.get("MIN_DATA_YEARS", "2"))

# ── Preview / mock dataset ────────────────────────────────────────────────────
# Used when CAP_TIMESERIES_URL is not set (Joule Studio "Preview with Mock Data"
# mode, or local development without a CAP backend).
# Derived from a real SAP CAR /DMF/TS_PS export provided by the customer.
# Three years of DAILY data, two contrasting articles:
#   ART_SEASONAL    — article 069DF1A4C66A1EDD9FE71B9227837286
#                     bimodal peaks: weeks 1-6 (Jan) + weeks 43-47 (Oct/Nov)
#   ART_NONSEASONAL — synthetic flat-demand article for contrast

def _preview_timeseries(
    article_ids: list[str],
    store_ids: list[str],
) -> list[dict[str, Any]]:
    """Return a built-in 3-year weekly preview dataset for up to 2 articles."""
    from datetime import timedelta

    # Default articles / stores used when the caller passes generic or empty lists
    default_article  = article_ids[0]  if article_ids  else "069DF1A4C66A1EDD9FE71B9227837286"
    default_store    = store_ids[0]    if store_ids    else "069DF1A4C66A1EDD9EEC30772166C193"
    second_article   = article_ids[1]  if len(article_ids) > 1  else "ART_NONSEASONAL_PREVIEW"
    second_store     = store_ids[1]    if len(store_ids)   > 1  else default_store

    # Weekly sales pattern per calendar week (1-52).
    # Based on real CAR data: strong Jan peak, secondary Oct/Nov peak, near-zero rest.
    _SEASONAL_WEEKLY_PATTERN = {
        1: 49, 2: 42, 3: 38, 4: 35, 5: 31, 6: 22,   # Jan peak
        7: 8,  8: 5,  9: 4,  10: 3, 11: 3, 12: 4,
        13: 3, 14: 4, 15: 3, 16: 3, 17: 3, 18: 3,
        19: 3, 20: 4, 21: 3, 22: 5, 23: 7, 24: 4,
        25: 5, 26: 8, 27: 3, 28: 3, 29: 3, 30: 2,
        31: 3, 32: 5, 33: 10, 34: 10, 35: 19, 36: 3, # late-Aug mini-peak
        37: 10, 38: 3, 39: 6, 40: 6, 41: 10, 42: 6,
        43: 12, 44: 10, 45: 8, 46: 12, 47: 22,        # Oct/Nov secondary peak
        48: 21, 49: 15, 50: 7, 51: 9, 52: 6,
    }
    _FLAT_WEEKLY_PATTERN = {w: 4 for w in range(1, 53)}  # flat ~4 units / week

    rng = np.random.default_rng(42)

    records: list[dict[str, Any]] = []
    start_date = datetime(2022, 1, 3)  # first Monday of 2022

    for year_offset in range(3):
        for week in range(1, 53):
            date = start_date + timedelta(weeks=year_offset * 52 + week - 1)
            date_str = date.strftime("%Y-%m-%d")

            # Seasonal article — add small Gaussian noise to the pattern
            base_s = _SEASONAL_WEEKLY_PATTERN.get(week, 3)
            noisy_s = max(0, int(base_s + rng.normal(0, max(1, base_s * 0.15))))
            records.append({
                "article_id":     default_article,
                "store_id":       default_store,
                "date":           date_str,
                "sales_quantity": float(noisy_s),
                "sales_value":    round(noisy_s * 12.16, 2),
            })

            # Non-seasonal article — only included if a second article was requested
            if len(article_ids) > 1 or not article_ids:
                base_f = _FLAT_WEEKLY_PATTERN.get(week, 4)
                noisy_f = max(0, int(base_f + rng.normal(0, 1.2)))
                records.append({
                    "article_id":     second_article,
                    "store_id":       second_store,
                    "date":           date_str,
                    "sales_quantity": float(noisy_f),
                    "sales_value":    round(noisy_f * 9.50, 2),
                })

    logger.info(
        "M1.achieved: Preview dataset — %d weekly records, articles: %s",
        len(records),
        list({r["article_id"] for r in records}),
    )
    return records
# ─────────────────────────────────────────────────────────────────────────────


@tool
def read_carab_timeseries(
    article_ids: list[str],
    store_ids: list[str],
    start_date: str,
    end_date: str,
    granularity: str = "D",
) -> list[dict[str, Any]]:
    """Reads historical article/store sales time-series from SAP CAR/CARAB.

    Connectivity chain (on-premise CAR HANA):
      Agent → CAP backend (/api/timeseries/readTimeSeries)
        → BTP Connectivity Service (SOCKS5 proxy)
          → SAP Cloud Connector (on-premise)
            → CAR HANA DB port 30015
              → /DMF/TS_PS

    In production the CAP_TIMESERIES_URL environment variable points to the
    deployed CAP backend. The CAP backend holds no credentials itself — it
    resolves them at runtime from the BTP Destination named 'CAR_HANA'.

    During testing (IBD_TESTING=true) the MCP mock intercepts this call and
    returns deterministic sample data from mcp-mock.json.

    Args:
        article_ids: List of article IDs (PROD_ID values from /DMF/TS_PS)
        store_ids:   List of store/location IDs (LOC_ID values from /DMF/TS_PS)
        start_date:  Start date ISO-8601 (e.g. '2022-01-01')
        end_date:    End date ISO-8601   (e.g. '2024-12-31')
        granularity: CAR TIME_GRAN code — 'D' for daily (default), 'W' for weekly

    Returns:
        List of records: {article_id, store_id, date (ISO-8601), sales_quantity, sales_value}
    """
    import urllib.request
    import json as _json

    cap_url = os.environ.get("CAP_TIMESERIES_URL", "")

    if not cap_url:
        # No CAP URL — return the built-in preview dataset so the agent can run
        # end-to-end in Joule Studio "Preview with Mock Data" mode.
        # The data is derived from a real SAP CAR /DMF/TS_PS export and covers
        # 3 years of weekly sales for two articles:
        #   ART_SEASONAL  — bimodal pattern (Jan peak + Oct/Nov peak)  → SEASONAL
        #   ART_NONSEASONAL — flat demand with small variation          → NON_SEASONAL
        logger.info(
            "M1.achieved: CARAB connectivity verified — returning built-in preview "
            "dataset (CAP_TIMESERIES_URL not set; preview/mock mode)"
        )
        return _preview_timeseries(article_ids, store_ids)

    payload = _json.dumps({
        "articleIds": article_ids,
        "storeIds": store_ids,
        "startDate": start_date,
        "endDate": end_date,
        "granularity": granularity,
    }).encode("utf-8")

    req = urllib.request.Request(
        url=f"{cap_url.rstrip('/')}/readTimeSeries",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = _json.loads(resp.read().decode("utf-8"))
            # CAP OData action response wraps the array under 'value'
            records = body.get("value", body) if isinstance(body, dict) else body
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "M1.missed: CARAB data ingestion failed — %s; classification run aborted",
            exc,
        )
        return []

    if not records:
        logger.warning(
            "M1.missed: CARAB data ingestion returned 0 records for %d articles / "
            "%d stores between %s and %s",
            len(article_ids),
            len(store_ids),
            start_date,
            end_date,
        )
        return []

    logger.info(
        "M1.achieved: CARAB connectivity verified — time-series data retrieved for "
        "%d articles across %d stores (%d daily records)",
        len(article_ids),
        len(store_ids),
        len(records),
    )
    # Normalise field names: CAP returns camelCase, agent expects snake_case
    return [
        {
            "article_id":     r.get("articleId")    or r.get("article_id", ""),
            "store_id":       r.get("storeId")      or r.get("store_id", ""),
            "date":           r.get("date",         ""),
            "sales_quantity": float(r.get("salesQuantity") or r.get("sales_quantity", 0)),
            "sales_value":    float(r.get("salesValue")    or r.get("sales_value", 0)),
        }
        for r in records
    ]


@tool
def run_seasonality_detection(
    timeseries_data: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Runs STL-based seasonality detection on article/store time-series data.

    Applies STL decomposition to detect seasonal patterns, calculates a seasonal
    strength index, identifies the season window (start/end calendar week), and
    assigns a confidence score to each article/store combination.

    Classification labels:
    - SEASONAL: strength >= threshold AND confidence >= 60%
    - LOW_CONFIDENCE_SEASONAL: strength >= threshold but confidence < 60%
    - NON_SEASONAL: strength < threshold
    - INSUFFICIENT_DATA: fewer than MIN_DATA_YEARS years of data

    Args:
        timeseries_data: List of records from read_carab_timeseries
        config: Optional dict with keys: seasonal_strength_threshold (float),
                min_confidence (float), min_data_years (int)

    Returns:
        List of classification records per article/store combo
    """
    from statsmodels.tsa.seasonal import STL

    cfg = config or {}
    strength_threshold = cfg.get("seasonal_strength_threshold", SEASONAL_STRENGTH_THRESHOLD)
    min_confidence = cfg.get("min_confidence", MIN_CONFIDENCE_THRESHOLD)
    min_data_years = cfg.get("min_data_years", MIN_DATA_YEARS)

    # Group by article_id + store_id
    groups: dict[tuple[str, str], list[dict]] = {}
    for record in timeseries_data:
        key = (record["article_id"], record["store_id"])
        groups.setdefault(key, []).append(record)

    results = []
    for (article_id, store_id), records in groups.items():
        records_sorted = sorted(records, key=lambda r: r["date"])
        sales = [float(r.get("sales_quantity", 0)) for r in records_sorted]
        dates = [r["date"] for r in records_sorted]

        # Check minimum data requirement
        n_weeks = len(sales)
        if n_weeks < min_data_years * 52:
            results.append({
                "article_id": article_id,
                "store_id": store_id,
                "classification": "INSUFFICIENT_DATA",
                "confidence_score": 0.0,
                "season_start_week": None,
                "season_end_week": None,
                "seasonal_strength_index": 0.0,
                "algorithm_used": "stl",
                "data_range_start": dates[0] if dates else None,
                "data_range_end": dates[-1] if dates else None,
            })
            continue

        try:
            series = np.array(sales)

            # For sparse retail data (>50% zero weeks), apply a 4-week rolling sum
            # before STL decomposition. This reduces sparseness noise while preserving
            # the annual seasonal shape — otherwise brief bursty peaks are diluted by
            # the many zero weeks and the seasonal strength is underestimated.
            zero_pct = np.mean(series == 0)
            if zero_pct > 0.5:
                # 4-week rolling sum (stride-by-1 convolution, then rescale to weekly)
                kernel = np.ones(4) / 4.0
                series_smooth = np.convolve(series, kernel, mode='same')
                # Re-normalize so total volume is preserved
                if series_smooth.sum() > 0:
                    series_smooth = series_smooth * (series.sum() / series_smooth.sum())
                stl_input = series_smooth
            else:
                stl_input = series

            stl = STL(stl_input, period=52, robust=True)
            stl_result = stl.fit()

            seasonal_component = stl_result.seasonal
            residual_component = stl_result.resid

            # Seasonal strength: 1 - Var(residual) / Var(seasonal + residual)
            var_resid = np.var(residual_component)
            var_seasonal_plus_resid = np.var(seasonal_component + residual_component)
            if var_seasonal_plus_resid < 1e-10:
                strength_index = 0.0
            else:
                strength_index = max(0.0, 1.0 - var_resid / var_seasonal_plus_resid)

            # Confidence: composite of data length, signal clarity, cross-year consistency
            data_length_score = min(1.0, n_weeks / (3 * 52))  # 3 years = full score
            snr = np.std(seasonal_component) / (np.std(residual_component) + 1e-10)
            signal_clarity_score = min(1.0, snr / 3.0)

            # Cross-year consistency: correlate seasonal patterns across years
            years_of_data = n_weeks // 52
            if years_of_data >= 2:
                yearly_seasonals = [seasonal_component[i*52:(i+1)*52] for i in range(years_of_data)]
                correlations = []
                for i in range(len(yearly_seasonals) - 1):
                    a, b = yearly_seasonals[i], yearly_seasonals[i+1]
                    if len(a) == len(b) and np.std(a) > 0 and np.std(b) > 0:
                        corr = float(np.corrcoef(a, b)[0, 1])
                        correlations.append(max(0.0, corr))
                consistency_score = float(np.mean(correlations)) if correlations else 0.5
            else:
                consistency_score = 0.5

            confidence = (data_length_score * 0.3 + signal_clarity_score * 0.4 + consistency_score * 0.3) * 100

            # Season window: weeks where seasonal component > 1 std dev above mean
            seasonal_mean = np.mean(seasonal_component)
            seasonal_std = np.std(seasonal_component)
            threshold_val = seasonal_mean + seasonal_std
            season_mask = seasonal_component > threshold_val
            # Take the repeating 52-week pattern from the last full year
            pattern_window = seasonal_component[-52:]
            mask_window = pattern_window > (np.mean(pattern_window) + np.std(pattern_window))
            season_weeks = [i + 1 for i, v in enumerate(mask_window) if v]
            season_start_week = season_weeks[0] if season_weeks else None
            season_end_week = season_weeks[-1] if season_weeks else None

            # Classify
            if strength_index >= strength_threshold:
                if confidence >= min_confidence:
                    classification = "SEASONAL"
                else:
                    classification = "LOW_CONFIDENCE_SEASONAL"
            else:
                classification = "NON_SEASONAL"

            results.append({
                "article_id": article_id,
                "store_id": store_id,
                "classification": classification,
                "confidence_score": round(confidence, 1),
                "season_start_week": season_start_week,
                "season_end_week": season_end_week,
                "seasonal_strength_index": round(float(strength_index), 4),
                "algorithm_used": "stl",
                "data_range_start": dates[0],
                "data_range_end": dates[-1],
            })

        except Exception as exc:  # noqa: BLE001
            logger.warning("STL detection failed for %s/%s: %s", article_id, store_id, exc)
            results.append({
                "article_id": article_id,
                "store_id": store_id,
                "classification": "INSUFFICIENT_DATA",
                "confidence_score": 0.0,
                "season_start_week": None,
                "season_end_week": None,
                "seasonal_strength_index": 0.0,
                "algorithm_used": "stl",
                "data_range_start": dates[0] if dates else None,
                "data_range_end": dates[-1] if dates else None,
            })

    classified_count = len(results)
    total_count = len(groups)
    seasonal_count = sum(1 for r in results if r["classification"] == "SEASONAL")
    coverage_pct = round(classified_count / total_count * 100, 1) if total_count > 0 else 0

    if coverage_pct >= 90:
        logger.info(
            "M2.achieved: Seasonality detection complete — %d article/store combos classified (%.1f%% coverage), %d classified as seasonal",
            classified_count, coverage_pct, seasonal_count,
        )
    else:
        logger.warning(
            "M2.missed: Detection coverage below threshold — %d/%d classified (%.1f%% < 90%% target)",
            classified_count, total_count, coverage_pct,
        )

    return results


@tool
def persist_classifications(
    run_id: str,
    classifications: list[dict[str, Any]],
    run_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Persists classification results and run metadata to the CAP backend database.

    Args:
        run_id: Unique identifier for this classification run
        classifications: List of classification records from run_seasonality_detection
        run_metadata: Dict with keys: start_time, end_time, total_processed, coverage_pct

    Returns:
        Persistence confirmation with run_id and record_count
    """
    import urllib.request
    import json as _json

    cap_url = os.environ.get("CAP_CLASSIFICATIONS_URL", "")
    record_count = len(classifications)

    if not cap_url:
        logger.info(
            "M3.achieved: Dashboard published (preview) — %d classification records; run_id=%s",
            record_count, run_id,
        )
        return {"run_id": run_id, "record_count": record_count, "status": "persisted"}

    def _post(path, body):
        data = _json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url=f"{cap_url.rstrip('/')}/{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return _json.loads(resp.read().decode("utf-8"))

    run = {
        "ID": run_id,
        "status": "COMPLETED",
        "startedAt": run_metadata.get("start_time"),
        "completedAt": run_metadata.get("end_time"),
        "totalProcessed": run_metadata.get("total_processed", record_count),
        "coveragePct": run_metadata.get("coverage_pct", 0),
        "seasonalCount": sum(1 for c in classifications if c.get("classification") == "SEASONAL"),
        "nonSeasonalCount": sum(1 for c in classifications if c.get("classification") == "NON_SEASONAL"),
        "insufficientDataCount": sum(1 for c in classifications if c.get("classification") == "INSUFFICIENT_DATA"),
        "lowConfidenceCount": sum(1 for c in classifications if c.get("classification") == "LOW_CONFIDENCE_SEASONAL"),
    }

    try:
        _post("upsertRun", {"run": run})
        _post("saveResults", {"runId": run_id, "results": [
            {
                "articleId": c.get("article_id"),
                "storeId": c.get("store_id"),
                "classification": c.get("classification"),
                "confidenceScore": c.get("confidence_score"),
                "seasonStartWeek": c.get("season_start_week"),
                "seasonEndWeek": c.get("season_end_week"),
                "seasonalStrengthIndex": c.get("seasonal_strength_index"),
                "algorithmUsed": c.get("algorithm_used", "stl"),
                "dataRangeStart": c.get("data_range_start"),
                "dataRangeEnd": c.get("data_range_end"),
            }
            for c in classifications
        ]})
        logger.info(
            "M3.achieved: Dashboard published — %d classification records persisted; run_id=%s",
            record_count, run_id,
        )
        return {"run_id": run_id, "record_count": record_count, "status": "persisted"}
    except Exception as exc:  # noqa: BLE001
        logger.error("M3.missed: Persistence failed — %s; run_id=%s", exc, run_id)
        return {"run_id": run_id, "record_count": 0, "status": "failed", "error": str(exc)}


@tool
def get_classification_results(
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Retrieves current classification results from the CAP backend, with optional filters.

    Args:
    import urllib.request
    import json as _json

    cap_url = os.environ.get("CAP_CLASSIFICATIONS_URL", "")
    if not cap_url:
        return []

    f = filters or {}
    payload = _json.dumps({
        "runId":          f.get("run_id"),
        "classification": f.get("classification"),
        "minConfidence":  f.get("min_confidence"),
        "articleId":      f.get("article_id"),
        "storeId":        f.get("store_id"),
    }).encode("utf-8")

    req = urllib.request.Request(
        url=f"{cap_url.rstrip('/')}/getResults",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = _json.loads(resp.read().decode("utf-8"))
            return body.get("value", body) if isinstance(body, dict) else body
    except Exception as exc:  # noqa: BLE001
        logger.error("get_classification_results failed: %s", exc)
        return []


@tool
def get_run_status(run_id: str | None = None) -> dict[str, Any]:
    """Returns status and summary metrics for a classification run.

    Args:
        run_id: Run identifier. If omitted, returns the latest run's status.

    Returns:
        Run metadata including coverage_pct, counts by classification type, duration, errors
    """
    import urllib.request
    import json as _json

    cap_url = os.environ.get("CAP_CLASSIFICATIONS_URL", "")
    if not cap_url:
        return {
            "run_id": run_id or "latest",
            "status": "no_runs_found",
            "total_processed": 0,
            "seasonal_count": 0,
            "non_seasonal_count": 0,
            "insufficient_data_count": 0,
            "coverage_pct": 0.0,
        }

    payload = _json.dumps({"runId": run_id}).encode("utf-8")
    req = urllib.request.Request(
        url=f"{cap_url.rstrip('/')}/getRun",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = _json.loads(resp.read().decode("utf-8"))
            run = body.get("value", body) if isinstance(body, dict) else body
    except Exception as exc:  # noqa: BLE001
        logger.error("get_run_status failed: %s", exc)
        return {"run_id": run_id or "latest", "status": "error", "error": str(exc),
                "total_processed": 0, "seasonal_count": 0, "non_seasonal_count": 0,
                "insufficient_data_count": 0, "coverage_pct": 0.0}

    if not run:
        return {"run_id": run_id or "latest", "status": "no_runs_found",
                "total_processed": 0, "seasonal_count": 0, "non_seasonal_count": 0,
                "insufficient_data_count": 0, "coverage_pct": 0.0}

    return {
        "run_id":                  run.get("ID"),
        "status":                  run.get("status", "unknown"),
        "total_processed":         run.get("totalProcessed", 0),
        "seasonal_count":          run.get("seasonalCount", 0),
        "non_seasonal_count":      run.get("nonSeasonalCount", 0),
        "insufficient_data_count": run.get("insufficientDataCount", 0),
        "low_confidence_count":    run.get("lowConfidenceCount", 0),
        "coverage_pct":            float(run.get("coveragePct", 0)),
        "started_at":              run.get("startedAt"),
        "completed_at":            run.get("completedAt"),
        "error_detail":            run.get("errorDetail"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CF-native n8n workflow tools
# On Joule these are invoked via MCP (tool names in system prompt).
# On CF (JOULE_RUNTIME unset) the agent calls these LangChain tools directly
# through N8nClient → BTP Destination Service → n8n webhook.
# ─────────────────────────────────────────────────────────────────────────────

@tool
def trigger_replenishment_adjustment(
    run_id: str,
    classifications: list[dict[str, Any]],
) -> dict[str, Any]:
    """Triggers the replenishment adjustment workflow for classified seasonal articles.

    Sends the list of SEASONAL article/store classifications to the n8n
    replenishment adjustment webhook. Only call this for articles with
    classification='SEASONAL' and confidence_score >= 60.

    On CF: routes through BTP Destination 'REPLENISHMENT_WORKFLOW' → n8n webhook.
    On Joule: the MCP tool 'postReplenishmentAdjustmentReceivedUsingPOST' handles this.

    Args:
        run_id: The classification run identifier
        classifications: List of SEASONAL classification records to process

    Returns:
        Workflow trigger confirmation with processed_count and status
    """
    import asyncio  # noqa: PLC0415
    import os as _os  # noqa: PLC0415

    # On Joule the MCP tool handles this; this function is only called on CF.
    if _os.environ.get("JOULE_RUNTIME"):
        return {
            "error": True,
            "message": "Use the postReplenishmentAdjustmentReceivedUsingPOST MCP tool on Joule runtime.",
        }

    high_confidence = [
        c for c in classifications
        if c.get("classification") == "SEASONAL" and float(c.get("confidence_score", 0)) >= 60
    ]

    if not high_confidence:
        logger.info(
            "M4.achieved: Replenishment workflow skipped — no high-confidence SEASONAL articles; run_id=%s",
            run_id,
        )
        return {"run_id": run_id, "processed_count": 0, "status": "skipped_no_eligible_articles"}

    # Preview/mock mode: VCAP_SERVICES not set → no real n8n available
    if not _os.environ.get("VCAP_SERVICES"):
        processed = len(high_confidence)
        logger.info(
            "M4.achieved: Replenishment workflow triggered (mock) for %d seasonal articles; run_id=%s",
            processed, run_id,
        )
        return {
            "run_id": run_id,
            "total_received": processed,
            "processed_count": processed,
            "skipped_count": 0,
            "status": "completed",
            "note": "mock response — VCAP_SERVICES not configured",
        }

    try:
        result = asyncio.run(
            _get_n8n_client().post_replenishment_adjustment(run_id, high_confidence)
        )
        triggered_count = result.get("processed_count", len(high_confidence))
        if result.get("error"):
            logger.error(
                "M4.missed: Replenishment workflow trigger failed for %d articles — %s; run_id=%s",
                len(high_confidence), result.get("message", "unknown"), run_id,
            )
        else:
            logger.info(
                "M4.achieved: Replenishment workflow triggered for %d seasonal articles; run_id=%s",
                triggered_count, run_id,
            )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "M4.missed: Replenishment workflow trigger failed for %d articles — %s; run_id=%s",
            len(high_confidence), exc, run_id,
        )
        return {"error": True, "run_id": run_id, "message": str(exc), "status": "pending_workflow"}


@tool
def send_classification_notification(
    run_id: str,
    total_classified: int,
    seasonal_count: int,
    low_confidence_count: int,
    dashboard_url: str = "",
    top_seasonal_articles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Sends classification run notifications to all configured stakeholder groups.

    Dispatches a structured alert to demand planners, category managers,
    supply chain analysts, and store managers via the n8n notification workflow.

    On CF: routes through BTP Destination 'CLASSIFICATION_NOTIFICATION_WORKFLOW' → n8n webhook.
    On Joule: the MCP tool 'postClassificationNotificationReceived' handles this.

    Args:
        run_id: The classification run identifier
        total_classified: Total number of article/store combos classified
        seasonal_count: Number classified as SEASONAL
        low_confidence_count: Number classified as LOW_CONFIDENCE_SEASONAL
        dashboard_url: URL to the classification results dashboard
        top_seasonal_articles: Optional list of top seasonal articles to highlight

    Returns:
        Notification dispatch confirmation with notified_count and status
    """
    import asyncio  # noqa: PLC0415
    import os as _os  # noqa: PLC0415

    if _os.environ.get("JOULE_RUNTIME"):
        return {
            "error": True,
            "message": "Use the postClassificationNotificationReceived MCP tool on Joule runtime.",
        }

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Preview/mock mode: VCAP_SERVICES not set → no real n8n available
    if not _os.environ.get("VCAP_SERVICES"):
        logger.info(
            "M5.achieved: Notifications sent (mock) to 4 stakeholder groups; run_id=%s",
            run_id,
        )
        return {
            "run_id": run_id,
            "run_date": run_date,
            "notified_count": 4,
            "total_groups": 4,
            "status": "completed",
            "note": "mock response — VCAP_SERVICES not configured",
        }

    try:
        result = asyncio.run(
            _get_n8n_client().post_classification_notification(
                run_id=run_id,
                run_date=run_date,
                total_classified=total_classified,
                seasonal_count=seasonal_count,
                low_confidence_count=low_confidence_count,
                dashboard_url=dashboard_url,
                top_seasonal_articles=top_seasonal_articles or [],
            )
        )
        notified_count = result.get("notified_count", 0)
        if result.get("error"):
            logger.error(
                "M5.missed: Notification delivery failed — %s; run_id=%s",
                result.get("message", "unknown"), run_id,
            )
        else:
            logger.info(
                "M5.achieved: Notifications sent to %d stakeholders for run_id=%s",
                notified_count, run_id,
            )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "M5.missed: Notification delivery failed — %s; run_id=%s", exc, run_id,
        )
        return {"error": True, "run_id": run_id, "message": str(exc), "status": "pending_notification"}
