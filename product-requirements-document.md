# Product Requirements Document (PRD)

**Title:** Seasonal Article Detector Agent  
**Date:** 2026-10-07  
**Owner:** Demand Planning / Retail Supply Chain  
**Solution Category:** AI Agent + n8n Workflow + CAP Application (with React UI)

---

## Product Purpose & Value Proposition

**Elevator Pitch:**  
Retailers hold millions of historical article/store sales records, yet identifying which articles are truly seasonal — high demand in specific periods, near-zero demand outside — remains a fully manual task today. This agent automates that classification, freeing planners from tedious curve analysis and ensuring replenishment parameters are aligned to actual demand patterns before each season begins.

**Business Need:**  
With thousands of articles across hundreds of stores, manually reviewing sales curves to identify seasonal demand patterns is not scalable. Seasonal misclassification leads to overstock outside the season window and stockouts during peak demand, directly impacting profitability and customer satisfaction. No standard SAP product performs AI/ML-based seasonal detection from raw time-series data — a custom agent is required to fill this gap.

**Expected Value:**  
- Eliminate the current 0% automation rate for seasonal classification, reaching ≥90% automatic coverage.
- Reduce planner effort spent on manual seasonality reviews.
- Improve replenishment accuracy for seasonal articles by providing earlier, data-driven classification.
- Close the loop from detection to action: automatically trigger replenishment adjustments and notify stakeholders.

**Product Objectives (Prioritized):**
1. Automatically classify ≥90% of article/store combinations as seasonal or non-seasonal with a confidence score.
2. Surface classification results in an interactive dashboard accessible to demand planners, category managers, and analysts.
3. Trigger downstream replenishment parameter adjustments and user notifications automatically upon classification.

---

## Business Metrics

| Metric | Baseline | Target | Timeline | Process / Capability | Source |
|--------|----------|--------|----------|----------------------|--------|
| % of article/store combos automatically classified as seasonal | 0% (fully manual today) | 90% | No strict timeline | Demand Planning / Seasonal Merchandise Management | user |

---

## User Profiles & Personas

### Primary Persona: Dana — Demand Planner

Dana is a 34-year-old demand planner at a mid-to-large retail organisation, responsible for generating 12-week and seasonal demand forecasts across hundreds of article/store combinations. Every season, she manually inspects sales curves in spreadsheets and SAP reports to flag articles she suspects are seasonal — a process that takes days and is prone to inconsistency across planners. She is comfortable with SAP tools and data exports but frustrated by the lack of automated intelligence on top of the data she already has. She needs a tool that tells her which articles to treat as seasonal before she builds her forecast, not after the season has already started.

### Secondary Persona: Marco — Merchandise / Category Manager

Marco is a 41-year-old category manager responsible for assortment decisions and seasonal ranging for apparel and accessories. He relies on demand planners to flag seasonal articles but often finds out too late — after overstock has been ordered or markdowns have been taken. He wants visibility into which articles exhibit strong seasonal demand patterns so he can make better ranging, pricing, and promotion decisions. He is not a data analyst; he needs a clean, filterable dashboard, not raw numbers.

### Secondary Persona: Priya — Supply Chain Analyst

Priya is a 29-year-old analyst who monitors inventory health across the network. She tracks articles where actuals deviate significantly from plans and frequently investigates cases where seasonal articles were not flagged in time. She needs early-warning signals and audit-trail visibility into classification decisions to explain deviations to management.

### Other User Types

- **Retail Store Manager**: Downstream consumer of replenishment decisions; receives notifications when seasonal articles in their store are reclassified so they can align local stock processes.

---

## User Goals & Tasks

### For Dana (Demand Planner):

**Goals:**
- Know which articles to treat as seasonal before building each forecast cycle.
- Reduce time spent on manual seasonal curve analysis from days to minutes.

**Key Tasks:**
- Review the list of newly classified seasonal articles and their confidence scores.
- Filter classifications by product category or store cluster.
- Accept or flag classifications for manual review before they flow into the replenishment workflow.

### For Marco (Category Manager):

**Goals:**
- Understand the seasonal demand shape (start/end window) for articles in his category.
- Use classification data to inform ranging and promotional decisions.

**Key Tasks:**
- View a dashboard of seasonal articles with season windows and year-over-year patterns.
- Export or share classification reports with buying and planning teams.

### For Priya (Supply Chain Analyst):

**Goals:**
- Identify articles that were misclassified in prior seasons to improve future accuracy.
- Provide audit evidence for classification decisions to management.

**Key Tasks:**
- Review historical classification logs including confidence scores and algorithm outputs.
- Compare seasonal classification dates against actual demand spike dates.

---

## Product Principles

1. **Detection before Forecasting**: Seasonal classification must happen upstream of forecast generation — the agent delivers input to the planning process, not output from it.
2. **Confidence is not a black box**: Every classification must carry a human-readable confidence score and the key signals that drove it, so planners can trust or challenge the result.
3. **Action-oriented outputs**: Classification is not the end — results automatically flow into replenishment workflows and notifications; viewing results in a dashboard should not be the only outcome.
4. **Calibrate to context**: Seasonality thresholds must be configurable per category or product group; what counts as "strongly seasonal" for Christmas decorations differs from swimwear.
5. **Data quality first**: If historical data for an article/store is insufficient (too sparse, too short), the agent must say so explicitly rather than producing unreliable classifications.

---

## Business Context

**Current State:**  
Seasonal article identification is entirely manual. Demand planners review sales curves article by article using SAP reports and spreadsheet exports from SAP Customer Activity Repository (CAR/CARAB). There is no consistent methodology, no confidence scoring, and no automated downstream action. The process is repeated every season and consumes significant planner time, with results varying by planner experience.

**Strategic Alignment:**  
Automating seasonal detection directly supports retail supply chain efficiency goals — reducing markdown exposure, improving service levels during peak seasons, and enabling planners to focus on exception management rather than routine classification work. The solution aligns to the Plan to Fulfill E2E process and the Retail Replenishment and Merchandise Distribution variant.

**Success Criteria:**  
See the Business Metrics section above.

---

## Goals and Non-Goals

### Goals (In Scope)

- Automatically classify all article/store combinations from SAP CAR/CARAB as seasonal or non-seasonal with a confidence score and identified season window.
- Provide an interactive dashboard for demand planners and category managers to review, filter, and act on classifications.
- Trigger an n8n replenishment adjustment workflow for articles classified as strongly seasonal.
- Send notifications and alerts to demand planners, category managers, supply chain analysts, and store managers upon new classifications.
- Support scheduled and on-demand re-classification runs as new sales data arrives.

### Non-Goals (Out of Scope)

- Full demand forecasting or integration with SAP IBP forecast models (this solution feeds into IBP, it does not replace it).
- Writing seasonal classifications back to SAP S/4HANA Season master data (Retail Season API) — planned for a future phase.
- Manual override or correction UI for reclassifying individual articles (future phase).
- Promotion or markdown management beyond notifying affected stakeholders.

---

## Requirements

### Must-Have Requirements

**R1: Time-Series Data Ingestion from SAP CAR/CARAB**

- **Problem to Solve**: Planners cannot classify articles without systematic access to historical article/store sales data at the right granularity.
- **User Story**: As a demand planner, I need the agent to automatically read article/store level sales time-series from SAP CAR/CARAB so that I do not have to manually export data for each classification cycle.
- **Acceptance Criteria**:
  - Given the agent is configured with CAR/CARAB connectivity, when a classification run is triggered, then the agent retrieves sales time-series for all in-scope article/store combinations.
  - Given an article/store combination has insufficient history (< configurable minimum, e.g. 2 years), when the agent processes it, then it marks it as "insufficient data" rather than producing a classification.
- **Maps to Objective**: Objective 1 (≥90% classification coverage)
- **Priority Rank**: 1

**R2: Automatic Seasonality Detection and Classification**

- **Problem to Solve**: No tool currently identifies which articles are strongly seasonal; this is done manually and inconsistently.
- **User Story**: As a demand planner, I need each article/store combination to be automatically classified as seasonal or non-seasonal, with a confidence score and identified season window, so that I can use these inputs directly in my forecast cycle.
- **Acceptance Criteria**:
  - Given a sufficient time-series, when the agent runs detection, then each article/store combination receives a classification (seasonal / non-seasonal), a confidence score (0–100%), and a season window (start week / end week).
  - Given a configurable seasonality strength threshold, when an article's seasonal index exceeds the threshold, then it is classified as strongly seasonal.
  - Given a classification run completes, when ≥90% of in-scope article/store combinations have sufficient data, then ≥90% of those are classified.
- **Maps to Objective**: Objective 1
- **Priority Rank**: 2

**R3: Interactive Classification Dashboard**

- **Problem to Solve**: Planners and category managers have no consolidated view of seasonal article classifications and cannot act on them efficiently.
- **User Story**: As a merchandise manager, I need an interactive dashboard that shows all classified seasonal articles with their confidence scores and season windows, filterable by article, store, and category, so that I can make informed assortment and replenishment decisions.
- **Acceptance Criteria**:
  - Given classifications are available, when a user opens the dashboard, then they see a list of seasonal articles with: article ID, store ID, classification (seasonal / non-seasonal), confidence score, season start/end, and last updated date.
  - Given the dashboard is open, when a user applies filters (article, store, category, minimum confidence), then the list updates accordingly.
  - Given a user selects an article/store row, when they expand it, then they see the underlying time-series chart with the detected season window highlighted.
- **Maps to Objective**: Objective 2
- **Priority Rank**: 3

**R4: Replenishment Adjustment Workflow Trigger**

- **Problem to Solve**: Even when seasonal articles are identified, replenishment parameters are not updated automatically, leaving planners to make manual changes.
- **User Story**: As a demand planner, I need the agent to automatically trigger a replenishment parameter adjustment workflow for newly classified seasonal articles so that the downstream supply chain reacts without manual intervention.
- **Acceptance Criteria**:
  - Given an article/store combination is classified as strongly seasonal, when the classification run completes, then the replenishment adjustment n8n workflow is triggered with the article ID, store ID, season window, and confidence score as inputs.
  - Given the workflow is triggered, when it completes, then the classification record in the dashboard is updated to show "replenishment workflow triggered."
- **Maps to Objective**: Objective 3
- **Priority Rank**: 4

**R5: User Notification and Alerting**

- **Problem to Solve**: Stakeholders are not informed when seasonal articles are identified or reclassified, causing delayed responses.
- **User Story**: As a store manager, I need to receive a notification when articles in my store are newly classified as seasonal so that I can align local stock processes in time.
- **Acceptance Criteria**:
  - Given a classification run publishes new seasonal classifications, when the notification n8n workflow is triggered, then demand planners, category managers, supply chain analysts, and store managers receive a structured alert with: article ID, store ID, classification, season window, and a link to the dashboard.
  - Given the notification is sent, when a recipient opens the link, then they are directed to the relevant article/store row in the dashboard.
- **Maps to Objective**: Objective 3
- **Priority Rank**: 5

**R6: Scheduled and On-Demand Classification Runs**

- **Problem to Solve**: Classifications become stale as new sales data accumulates; planners need both regular refresh and the ability to trigger a run manually.
- **User Story**: As a demand planner, I need classification runs to execute on a configurable schedule and also be triggerable on demand so that classifications remain current throughout the year.
- **Acceptance Criteria**:
  - Given a configured schedule (e.g. weekly), when the scheduled time is reached, then the agent initiates a full or incremental classification run automatically.
  - Given a user clicks "Run Classification Now" in the dashboard, when confirmed, then a manual classification run begins and progress is visible.
- **Maps to Objective**: Objective 1
- **Priority Rank**: 6

---

## Non-Functional Requirements

### Performance

- **Throughput**: The agent must process and classify a minimum of 100,000 article/store combinations per classification run within a reasonable batch window (target: overnight batch ≤ 4 hours).
- **Dashboard Latency**: Dashboard page load and filter operations must respond within 3 seconds for up to 500,000 classification records.

### Reliability

- **Availability**: Dashboard and notification services target 99.5% uptime.
- **Fallback**: If the CAR/CARAB data connection is unavailable at scheduled run time, the run is retried up to 3 times before alerting the administrator. Previously published classifications remain visible in the dashboard.

### Explainability

- **Traceability**: Each classification record must store the algorithm used, the key signal values (e.g. seasonal strength index, FFT peak frequency), and the threshold applied.
- **Decision Logging**: All classification decisions are persisted with timestamp, algorithm version, input data range, and output values.
- **Uncertainty Communication**: Articles with confidence scores below a configurable threshold (e.g. < 60%) are flagged as "low confidence" in the dashboard and are not automatically forwarded to the replenishment workflow without planner confirmation.

---

## Solution Architecture

**Architecture Overview:**  
A Python-based AI agent (A2A protocol) runs on SAP BTP, orchestrating data ingestion from SAP CAR/CARAB, executing the seasonality detection engine, persisting results via a CAP backend, and driving downstream actions through two n8n workflows. A React UI (SAP UI5 Web Components) serves as the end-user dashboard, backed by the CAP OData service.

**Key Components:**

- **Seasonal Detection Agent (Python/A2A)**: Core intelligence — reads time-series from CAR/CARAB, applies seasonality algorithms, persists classifications, and invokes downstream workflows via MCP tools.
- **CAP Backend (Node.js)**: Persists classification results, exposes OData APIs consumed by the dashboard, and provides a REST endpoint for triggering on-demand runs.
- **React Dashboard (SAP UI5 Web Components)**: Interactive UI for planners and managers to review, filter, and explore seasonal classifications.
- **n8n Replenishment Adjustment Workflow**: Receives seasonal article data from the agent and adjusts replenishment parameters in the relevant downstream system.
- **n8n Notification Workflow**: Sends structured alerts to stakeholders when new classifications are published.
- **SAP CAR/CARAB**: Source of historical article/store level sales time-series data.

**Integration Points:**

- SAP CAR/CARAB → Agent: Read historical sales time-series; batch pull per classification run.
- Agent → CAP Backend: Write classification results and run status.
- CAP Backend → React Dashboard: OData read; on-demand.
- Agent → n8n Replenishment Workflow: Trigger via MCP tool call; per classification run.
- Agent → n8n Notification Workflow: Trigger via MCP tool call; per classification run.

---

### Agent Extensibility & Instrumentation

**Agent Extensibility:**
- The seasonality detection engine must be designed as a pluggable module: the default implementation uses STL decomposition and seasonal strength scoring, but the interface must allow additional algorithms (e.g. Fourier/FFT analysis, Prophet-based models) to be registered and selected per category or product group.
- Seasonality thresholds (minimum strength, minimum confidence, minimum data history) must be externally configurable — not hardcoded — to allow tuning without code changes.
- The agent must expose extension hooks for: pre-processing (custom data transformations before detection), post-processing (custom enrichment of classification results), and action routing (custom logic for which classified articles trigger which downstream workflows).

**Business Step Instrumentation:**
All major business steps emit structured log statements following the pattern `[MILESTONE_ID].[achieved|missed]: [description]` to support observability and monitoring in production. See the Milestones section for the full log statement definitions.

---

### Automation & Agent Behaviour

**Automation Level:** ML-assisted with human-in-the-loop for low-confidence cases

**Actions the system performs without human approval:**
- Reads sales time-series from SAP CAR/CARAB on schedule or on demand.
- Classifies article/store combinations with confidence score above the configured threshold.
- Triggers the replenishment adjustment workflow for high-confidence seasonal articles.
- Sends classification notifications to all configured stakeholder groups.

**Actions that require human review or approval:**
- Classifications with confidence score below the configurable low-confidence threshold are held in a "pending review" state in the dashboard and are not forwarded to the replenishment workflow until a planner confirms.
- Articles flagged as "insufficient data" require a planner to either extend the data lookback window or manually classify.

**Model or engine used:** Statistical time-series algorithms (STL decomposition, seasonal strength index, optionally FFT) running on SAP BTP; no large language model required for the core detection step. SAP Generative AI Hub may be used for natural language explanations of classification results surfaced in the dashboard.

**Knowledge & data sources accessed:**
- SAP CAR/CARAB: Historical article/store sales time-series (weekly or daily granularity); owned by the Retail Supply Chain team.
- CAP backend database: Persisted classification results and run history; owned by the solution.

**Tools or connectors invoked:**
- `read_carab_timeseries` (read-only): Fetches article/store sales time-series from SAP CAR/CARAB for a specified date range and article/store scope.
- `persist_classifications` (write): Writes classification results to the CAP backend database.
- `replenishment-adjustment` workflow (via `trigger_replenishment_adjustment` MCP tool): Triggers the replenishment parameter adjustment workflow for classified seasonal articles.
- `notification` workflow (via `send_classification_notification` MCP tool): Triggers the stakeholder notification workflow when new classifications are published.

**Guardrails & fail-safes:**
- The agent never modifies replenishment parameters directly; it only triggers the n8n workflow which owns that responsibility.
- Classifications with confidence below the configured threshold (default: 60%) are never automatically forwarded to the replenishment workflow.
- If the CAR/CARAB connection fails, the run is aborted cleanly; no partial or corrupted classifications are persisted.
- If the replenishment workflow trigger fails, the classification is marked "pending workflow" and an administrator alert is raised; the detection result is not lost.
- All classification runs are idempotent: re-running for the same period overwrites previous results for the same article/store combinations rather than creating duplicates.

---

## Milestones

### M1: Data Connectivity Established

- **Description**: The agent successfully authenticates with and reads article/store sales time-series from SAP CAR/CARAB.
- **Achieved when**: At least one article/store time-series is successfully retrieved and validated in a test run.
- **Log on achievement**: `M1.achieved: CARAB connectivity verified — time-series data retrieved for {article_count} articles across {store_count} stores`
- **Log on miss**: `M1.missed: CARAB data ingestion failed — {error_detail}; classification run aborted`

### M2: Seasonality Detection Operational

- **Description**: The detection engine runs successfully and classifies article/store combinations at scale.
- **Achieved when**: ≥90% of in-scope article/store combinations with sufficient data history receive a classification and confidence score.
- **Log on achievement**: `M2.achieved: Seasonality detection complete — {classified_count} article/store combos classified ({coverage_pct}% coverage), {seasonal_count} classified as seasonal`
- **Log on miss**: `M2.missed: Detection coverage below threshold — {classified_count}/{total_count} classified ({coverage_pct}% < 90% target)`

### M3: Dashboard Live

- **Description**: The interactive classification dashboard is deployed and accessible to business users.
- **Achieved when**: At least one classification run's results are visible and filterable in the dashboard by demand planners and category managers.
- **Log on achievement**: `M3.achieved: Dashboard published — {record_count} classification records available; run_id={run_id}`
- **Log on miss**: `M3.missed: Dashboard publication failed — results not visible to users; run_id={run_id}, error={error_detail}`

### M4: Replenishment Workflow Integration Complete

- **Description**: The n8n replenishment adjustment workflow is triggered automatically for newly classified seasonal articles.
- **Achieved when**: At least one classification run successfully triggers the replenishment workflow for all qualifying seasonal articles.
- **Log on achievement**: `M4.achieved: Replenishment workflow triggered for {triggered_count} seasonal articles; run_id={run_id}`
- **Log on miss**: `M4.missed: Replenishment workflow trigger failed for {failed_count} articles — {error_detail}; run_id={run_id}`

### M5: Notification System Active

- **Description**: Business users receive structured alerts when new seasonal classifications are published.
- **Achieved when**: Notifications are successfully delivered to all configured stakeholder groups following a classification run.
- **Log on achievement**: `M5.achieved: Notifications sent to {recipient_count} stakeholders for run_id={run_id}`
- **Log on miss**: `M5.missed: Notification delivery failed — {error_detail}; run_id={run_id}`

---

## Risks, Assumptions, and Dependencies

### Risks

- **Data quality dependency**: Seasonality detection accuracy depends on sufficient clean historical data (minimum 2 years recommended per article/store). Articles with sparse or heavily promoted histories may yield unreliable classifications.
- **Algorithm threshold calibration**: Initial threshold parameters for "strongly seasonal" must be tuned to the retailer's product mix; out-of-the-box defaults may not be optimal and will require iteration.
- **CAR/CARAB API availability**: The solution depends on stable programmatic access to SAP CAR/CARAB data; any changes to API contracts or access controls could affect the classification pipeline.

### Assumptions (Validate These)

- SAP CAR/CARAB holds at least 2 years of weekly or daily article/store sales history for the majority of the assortment.
- The organisation has SAP BTP capacity available for deploying a Python-based agent and a CAP application.
- Stakeholders have email or notification channel access configured for receiving alerts from the n8n notification workflow.
- Replenishment parameters in the downstream system can be updated programmatically via the n8n replenishment workflow.

### Dependencies

- Access to SAP CAR/CARAB APIs or data exports from the customer's system.
- SAP BTP environment (Cloud Foundry or Kyma) for agent, CAP backend, and workflow runtime deployment.
- n8n workflow runtime available in the SAP managed environment.
- Downstream replenishment system API or interface for the replenishment adjustment workflow to invoke.

---

## Open Questions

- What is the minimum data history required by the business (2 years? 3 years?) and how many articles/stores will fall below that threshold?
- Should low-confidence classifications be surfaced to all planners or routed to a specific review queue owner?
- Is there a preference for notification channel (email, SAP Build Work Zone, Microsoft Teams)?
- Should the agent eventually write seasonal flags back to the SAP S/4HANA Retail Season master data (via `CE_RETAILSEASON_0001`)? This has been deferred to a future phase but the integration point should be designed for.

---

## Appendix

### Glossary

- **Article/store combination**: A unique pairing of a retail article (SKU or article number) and a store location, representing the granularity at which sales and inventory are tracked in SAP CAR/CARAB.
- **Seasonality strength index**: A numeric measure (0–1 or 0–100%) of how much of a time-series's variance is explained by a repeating seasonal component, derived from STL decomposition.
- **Season window**: The identified start and end period (e.g. calendar weeks) during which a seasonal article exhibits its characteristic demand peak.
- **STL decomposition**: Seasonal and Trend decomposition using Loess — a statistical method that separates a time-series into trend, seasonal, and residual components.
- **Confidence score**: A combined measure reflecting data sufficiency, signal clarity, and algorithm consistency, used to indicate how reliable a classification result is.
- **A2A protocol**: Agent-to-Agent protocol used by SAP BTP Python-based agents for interoperability and tool invocation.

### References

- SAP Customer Activity Repository (CAR/CARAB) — Demand Planning documentation
- SAP S/4HANA Retail Season API: `sap.s4:apiResource:CE_RETAILSEASON_0001:v1`
- SAP IBP — Demand Forecasting and Demand Sensing capabilities (SC2989, SC701)
- SAP Business Accelerator Hub — Season Process Maintenance API: `sap.s4:apiResource:OP_API_SEASON_PROCESS_SRV_0001:v1`
- RBA Sub-processes: BPS-338 (Plan demand), BPS-327 (Align demand, supply and financial plans)
