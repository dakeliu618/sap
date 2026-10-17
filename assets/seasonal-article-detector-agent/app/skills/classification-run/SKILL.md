---
name: classification-run
description: Orchestrates a full or incremental classification run — data ingestion from CAR/CARAB, batch detection, result persistence, workflow triggering, and notification dispatch
---

# Classification Run Skill

## When to Use This Skill

Load this skill when the user triggers a full run, scheduled run, or on-demand re-classification of seasonal articles.

## Run Steps

Follow these steps in order. Log the milestone at each step.

### Step 1 — Ingest time-series data

Use the `read_carab_timeseries` tool to retrieve article/store sales data.
- Scope: all in-scope article/store combinations (or the subset specified by the user)
- Date range: last 2–3 years of weekly data
- Log: `M1.achieved: CARAB connectivity verified — time-series data retrieved for {article_count} articles across {store_count} stores`
- On failure: log `M1.missed: CARAB data ingestion failed — {error}; classification run aborted` and stop.

### Step 2 — Run seasonality detection

Use the `run_seasonality_detection` tool in batches of 500 article/store combos.
- Load the `seasonality-detection` skill for algorithm details and threshold interpretation.
- Log: `M2.achieved: Seasonality detection complete — {classified_count} combos classified ({coverage_pct}% coverage), {seasonal_count} classified as seasonal`
- If coverage_pct < 90%: log `M2.missed: Detection coverage below threshold — {classified_count}/{total_count} classified ({coverage_pct}% < 90% target)` (continue, do not abort).

### Step 3 — Persist results

Use the `persist_classifications` tool to save all classification records and run metadata to the CAP backend.
- Include: run_id, all classification records, start_time, end_time, total_processed, coverage_pct
- Log: `M3.achieved: Dashboard published — {record_count} classification records available; run_id={run_id}`
- On failure: log `M3.missed: Dashboard publication failed — results not visible to users; run_id={run_id}, error={error}`. Do not trigger downstream workflows if persistence failed.

### Step 4 — Trigger replenishment workflow

For all articles classified as `SEASONAL` with confidence ≥ 60%, trigger the replenishment adjustment workflow using the `postReplenishmentAdjustmentReceivedUsingPOST` MCP tool.
- Input: run_id + list of qualifying seasonal classifications
- Do NOT trigger for `LOW_CONFIDENCE_SEASONAL` without explicit user confirmation.
- Log: `M4.achieved: Replenishment workflow triggered for {triggered_count} seasonal articles; run_id={run_id}`
- On failure: log `M4.missed: Replenishment workflow trigger failed for {failed_count} articles — {error}; run_id={run_id}`. Mark affected classifications as `pending_workflow`. Do not lose detection results.

### Step 5 — Send notifications

Trigger the classification notification workflow using the `postClassificationNotificationReceived` MCP tool.
- Input: run summary (run_id, run_date, total_classified, seasonal_count, low_confidence_count, dashboard_url, top 5 seasonal articles)
- Log: `M5.achieved: Notifications sent to {recipient_count} stakeholders for run_id={run_id}`
- On failure: log `M5.missed: Notification delivery failed — {error}; run_id={run_id}`.

## Batch Processing

Process article/store combinations in batches of 500. For large assortments, summarize results to the user by category or store cluster rather than listing every individual result.

## Error Handling

- Steps 4 and 5 failures are non-fatal: record the error and continue. The detection and persistence results must not be lost.
- Step 1 and 3 failures are fatal for that run: abort and report clearly.
- For persistent failures, suggest the user contact their system administrator.
