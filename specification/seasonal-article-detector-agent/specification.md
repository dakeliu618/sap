# Specification: seasonal-article-detector-agent

> **Guidelines**: Read all applicable guidelines before executing ANY tasks below:
> - [guidelines.md](../guidelines.md) — Universal execution rules
> - [guidelines-agent.md](../guidelines-agent.md) — Universal agent patterns
> - [guidelines-agent-python.md](../guidelines-agent-python.md) — Python implementation details
> - [guidelines-agent-skills.md](../guidelines-agent-skills.md) — Runtime skills patterns
> - [guidelines-agent-mcp.md](../guidelines-agent-mcp.md) — MCP integration patterns

---

## Basic Setup

- [ ] Read `product-requirements-document.md` and `intent.md` at the solution root to load full context before starting.
- [ ] Bootstrap agent code in `assets/seasonal-article-detector-agent/` using instructions from the `sap-agent-bootstrap` reference:
  - Agent name: `seasonal-article-detector-agent`
  - Agent description: `An AI agent that automatically detects strongly seasonal articles from historical article/store level sales time-series data in SAP Customer Activity Repository (CAR/CARAB), classifies them with a confidence score and season window, and triggers downstream replenishment and notification workflows.`
- [ ] Install dependencies: `cd assets/seasonal-article-detector-agent && pip install -r requirements.txt`
- [ ] Validate the agent starts and responds at `/.well-known/agent.json`

---

## Runtime Skills

The agent requires two runtime skills due to domain-specific algorithm logic and multi-step classification workflow.

- [ ] Create `assets/seasonal-article-detector-agent/app/skills/seasonality-detection/SKILL.md` with:
  - YAML frontmatter: `name: seasonality-detection`, `description: Step-by-step instructions for running seasonal strength analysis on article/store time-series data including algorithm selection, threshold evaluation, and confidence scoring`
  - Body sections:
    1. **When to Use**: when the user requests classification, detection, or re-analysis of seasonal articles
    2. **Algorithm Steps**: STL decomposition → extract seasonal component strength index → FFT optional peak validation → confidence scoring formula → season window identification (start/end calendar week)
    3. **Threshold Rules**: configurable `SEASONAL_STRENGTH_THRESHOLD` (default 0.4, range 0–1), `MIN_CONFIDENCE_THRESHOLD` (default 60%), `MIN_DATA_YEARS` (default 2)
    4. **Classification Decision Table**: strength ≥ threshold AND confidence ≥ 60% → `SEASONAL`; strength ≥ threshold AND confidence < 60% → `LOW_CONFIDENCE_SEASONAL`; strength < threshold → `NON_SEASONAL`; data < min years → `INSUFFICIENT_DATA`
    5. **Output Format**: for each article/store combo — `article_id`, `store_id`, `classification`, `confidence_score`, `season_start_week`, `season_end_week`, `seasonal_strength_index`, `algorithm_used`, `data_range_start`, `data_range_end`
  - Create companion file `assets/seasonal-article-detector-agent/app/skills/seasonality-detection/references/algorithm-notes.md` with brief description of STL decomposition and seasonal strength index formula

- [ ] Create `assets/seasonal-article-detector-agent/app/skills/classification-run/SKILL.md` with:
  - YAML frontmatter: `name: classification-run`, `description: Orchestrates a full or incremental classification run: data ingestion from CAR/CARAB, batch detection, result persistence, workflow triggering, and notification dispatch`
  - Body sections:
    1. **When to Use**: when the user triggers a full run, scheduled run, or on-demand re-classification
    2. **Run Steps** (numbered, with milestone log statements):
       - Step 1 — Ingest time-series data via `read_carab_timeseries` tool; log `M1.achieved` / `M1.missed`
       - Step 2 — For each article/store batch, run seasonality detection skill; collect results; log `M2.achieved` / `M2.missed`
       - Step 3 — Persist results via `persist_classifications` tool; log `M3.achieved` / `M3.missed`
       - Step 4 — For all `SEASONAL` classifications with confidence ≥ 60%, trigger replenishment workflow via MCP tool; log `M4.achieved` / `M4.missed`
       - Step 5 — Trigger notification workflow via MCP tool for all published results; log `M5.achieved` / `M5.missed`
    3. **Batch Size**: process in batches of 500 article/store combos; sleep 0.1s between batches to avoid overload
    4. **Error Handling**: on tool failure in steps 4–5, mark classification as `pending_workflow` / `pending_notification`; do not lose detection results; surface error to user

---

## Project-Specific Tasks

### Tool: read_carab_timeseries

- [ ] In `assets/seasonal-article-detector-agent/app/agent.py`, define a LangGraph tool `read_carab_timeseries` that:
  - Accepts: `article_ids` (list[str]), `store_ids` (list[str]), `start_date` (str ISO-8601), `end_date` (str ISO-8601), `granularity` (str, default `"weekly"`)
  - Returns: list of time-series records `{article_id, store_id, date, sales_quantity, sales_value}` (mocked from `mcp-mock.json` during tests)
  - During testing (`IBD_TESTING=true`), returns mock data from `mcp-mock.json`; in production, the MCP tool call to the CAR/CARAB integration handles data retrieval
  - Docstring: "Reads historical article/store sales time-series from SAP CAR/CARAB for the specified scope and date range."

### Tool: run_seasonality_detection

- [ ] In `assets/seasonal-article-detector-agent/app/agent.py`, define a LangGraph tool `run_seasonality_detection` that:
  - Accepts: `timeseries_data` (list of records from `read_carab_timeseries`), `config` (dict with optional `seasonal_strength_threshold`, `min_confidence`, `min_data_years`)
  - Implements STL decomposition via Python `statsmodels` library (`STL` class from `statsmodels.tsa.seasonal`):
    - Decomposes each article/store time-series into trend, seasonal, residual components
    - Calculates seasonal strength index: `1 - Var(residual) / Var(seasonal + residual)`
    - Identifies season window: calendar weeks where seasonal component exceeds 1 standard deviation above mean
    - Calculates confidence score from data length, signal-to-noise ratio, and cross-year consistency
  - Returns: list of classification records per article/store (see skill output format)
  - Handles `INSUFFICIENT_DATA` gracefully — no exception, just classification label
  - Add `statsmodels` and `numpy` to `requirements.txt`

### Tool: persist_classifications

- [ ] In `assets/seasonal-article-detector-agent/app/agent.py`, define a LangGraph tool `persist_classifications` that:
  - Accepts: `run_id` (str), `classifications` (list of classification records), `run_metadata` (dict: `start_time`, `end_time`, `total_processed`, `coverage_pct`)
  - During production: calls the CAP backend OData endpoint to POST classification results (via MCP tool)
  - During tests: returns mock success response
  - Docstring: "Persists classification results and run metadata to the CAP backend database."

### Tool: get_classification_results

- [ ] In `assets/seasonal-article-detector-agent/app/agent.py`, define a LangGraph tool `get_classification_results` that:
  - Accepts: `filters` (dict with optional `classification`, `min_confidence`, `article_id`, `store_id`, `category`)
  - Returns: filtered list of classification records from the CAP backend
  - Docstring: "Retrieves current classification results from the CAP backend, with optional filters for dashboard and user queries."

### Tool: get_run_status

- [ ] In `assets/seasonal-article-detector-agent/app/agent.py`, define a LangGraph tool `get_run_status` that:
  - Accepts: `run_id` (str, optional — if omitted returns latest run)
  - Returns: run metadata including coverage %, counts by classification type, duration, and any errors
  - Docstring: "Returns status and summary metrics for a classification run."

### System Prompt

- [ ] Update the system prompt in `assets/seasonal-article-detector-agent/app/agent.py` to include:
  - Core role description: seasonal article detection agent
  - Instruction to load `seasonality-detection` skill when performing algorithm work
  - Instruction to load `classification-run` skill when orchestrating a full or incremental run
  - Standard data integrity instruction (never fabricate data; relay tool errors verbatim)
  - Pagination guard: when calling tools that return lists, set page size to maximum 100 items
  - Instruction: "To trigger the replenishment adjustment workflow, use the `replenishmentAdjustment` MCP tool. Do not call workflow webhook URLs directly."
  - Instruction: "To send classification notifications, use the `classificationNotification` MCP tool. Do not call workflow webhook URLs directly."
  - Low-confidence guardrail: "Never forward article/store classifications with confidence below 60% to the replenishment workflow without explicit user confirmation."
  - Batch processing guidance: classify articles in batches and summarize results rather than listing every individual result

### Agent Configuration

- [ ] Add `SEASONAL_STRENGTH_THRESHOLD` = `0.4` as a configurable environment variable with fallback default in `app/agent.py`
- [ ] Add `MIN_CONFIDENCE_THRESHOLD` = `60` as a configurable environment variable with fallback default
- [ ] Add `MIN_DATA_YEARS` = `2` as a configurable environment variable with fallback default

---

## Business Instrumentation

- [ ] Add structured logging with OpenTelemetry spans for all 5 milestones. Use the **decorator form** on async helper methods (not inside `stream()` generator). Extract business logic into `_run_classification()` async helper:
  - `M1` — CARAB data ingestion: `M1.achieved: CARAB connectivity verified — time-series data retrieved for {article_count} articles across {store_count} stores` / `M1.missed: CARAB data ingestion failed — {error_detail}; classification run aborted`
  - `M2` — Detection complete: `M2.achieved: Seasonality detection complete — {classified_count} article/store combos classified ({coverage_pct}% coverage), {seasonal_count} classified as seasonal` / `M2.missed: Detection coverage below threshold — {classified_count}/{total_count} classified ({coverage_pct}% < 90% target)`
  - `M3` — Results persisted / dashboard published: `M3.achieved: Dashboard published — {record_count} classification records available; run_id={run_id}` / `M3.missed: Dashboard publication failed — results not visible to users; run_id={run_id}, error={error_detail}`
  - `M4` — Replenishment workflow triggered: `M4.achieved: Replenishment workflow triggered for {triggered_count} seasonal articles; run_id={run_id}` / `M4.missed: Replenishment workflow trigger failed for {failed_count} articles — {error_detail}; run_id={run_id}`
  - `M5` — Notifications sent: `M5.achieved: Notifications sent to {recipient_count} stakeholders for run_id={run_id}` / `M5.missed: Notification delivery failed — {error_detail}; run_id={run_id}`
- [ ] Verify `bootstrap(app)` is called after `app = server.build()` in `main.py`

---

## MCP Tool Integration

> See [guidelines-agent-mcp.md](../guidelines-agent-mcp.md) for complete patterns.

- [ ] The CAR/CARAB APIs returned by discovery have no published ORD IDs and are not available for MCP translation. The `read_carab_timeseries` tool will be implemented as a local agent tool backed by the CAP backend proxy during production. During tests, use `mcp-mock.json` mock data.
- [ ] After n8n workflows are created (replenishment + notification), run Steps A–F from `n8n-workflow` execution.md to generate MCP servers for both workflows.
- [ ] Once MCP server assets exist for both workflows, invoke `setup-solution` to register them, then invoke `mcp-mock-config` skill to generate `mcp-mock.json` in `assets/seasonal-article-detector-agent/`.
- [ ] Add `requires` entries to `assets/seasonal-article-detector-agent/asset.yaml` for:
  - `replenishment-adjustment-workflow-mcp-server` (ORD ID derived from workflow asset.yaml after workflow is created)
  - `classification-notification-workflow-mcp-server` (ORD ID derived from workflow asset.yaml after workflow is created)

---

## Testing

- [ ] Install test dependencies: `pip install -r requirements-test.txt` from `assets/seasonal-article-detector-agent/`
- [ ] Write unit tests in `assets/seasonal-article-detector-agent/tests/`:
  - `test_read_carab_timeseries.py` — mock MCP response; assert returned records have required fields
  - `test_run_seasonality_detection.py` — provide synthetic time-series (clear seasonal pattern and flat pattern); assert correct classifications, confidence scores, and season windows
  - `test_persist_classifications.py` — mock CAP backend response; assert run_id is included in payload
  - `test_get_classification_results.py` — mock CAP response; assert filters are applied correctly
  - `test_get_run_status.py` — mock run metadata response; assert coverage_pct is calculated
- [ ] Write one integration test `tests/test_integration.py` — mock LLM + mock MCP tools; simulate a user asking "Run seasonal classification for articles in store S001"; assert M1–M5 milestones are logged in sequence
- [ ] Run `pytest` from `assets/seasonal-article-detector-agent/` (no args) — fix any failures immediately
- [ ] If coverage < 70%, add targeted tests until threshold met
- [ ] Run `pytest` again (no args) to generate final `test_report.json`
- [ ] Verify `test_report.json` exists in `assets/seasonal-article-detector-agent/`

---

## Validation Checklist

```bash
# Instrumentation
grep -r "M[0-9]\.achieved" assets/seasonal-article-detector-agent/app/

# Test report
ls assets/seasonal-article-detector-agent/test_report.json

# Agent card
curl -s http://localhost:8000/.well-known/agent.json | python -m json.tool
```
