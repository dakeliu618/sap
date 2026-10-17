# Seasonal Article Detector Agent

AI-powered agent to automatically identify strongly seasonal articles from historical sales time-series data at article/store level in SAP CAR/CARAB.

## Business challenge

Retailers hold large volumes of historical sales data at article/store level (time-series). Manually identifying which articles are strongly seasonal — high demand only during specific periods of the year with little to no demand outside those periods — is impractical at scale. An AI agent is needed to automate this detection and surface actionable results to demand planners, merchandise managers, supply chain analysts, and store managers.

## Business Goals & Success Criteria

| Metric | Baseline | Target | Timeline | Process / Capability | Source |
|--------|----------|--------|----------|----------------------|--------|
| % of article/store combos automatically classified as seasonal | 0% (fully manual today) | 90% | No strict timeline | Demand Planning / Seasonal Merchandise Management | user |

## Key Milestones

| Milestone | Condition |
|-----------|-----------|
| Data connectivity established | Agent successfully reads article/store time-series from SAP CAR/CARAB |
| Seasonality detection operational | Agent classifies articles with ≥90% coverage across all article/store combos |
| Dashboard live | Interactive report shows seasonal articles, season windows, and confidence scores |
| Workflow integration complete | Downstream replenishment adjustment workflow is triggered automatically for flagged articles |
| Notification system active | Business users receive alerts when new seasonal classifications are published |

## Business Architecture (RBA)

### End-to-End Process

Plan to Fulfill

### Process Hierarchy

```
Plan to Fulfill
└── Plan to Optimize Fulfillment (generic)
    └── Plan demand (generic) [BPS-338]
        └── Generate collaborative demand plan
        └── Develop demand forecast
    └── Align demand, supply and financial plans (generic) [BPS-327]
        └── Perform sales and operations planning
```

### Summary

Automatically detecting seasonal articles from historical article/store sales data maps directly to the Plan to Fulfill E2E, specifically the demand planning sub-process (BPS-338). The Retail Replenishment and Merchandise Distribution variant is the most relevant industry pattern. The agent's output feeds into supply/demand alignment (BPS-327) by informing replenishment parameter adjustments.

## Fit Gap Analysis

| Requirement (business) | Standard asset(s) found | API ORD ID | MCP Server ORD ID | MCP Server Version | Webhook API ORD ID | Data Product ORD ID | Gap? | Notes / assumptions |
| ---------------------- | ----------------------- | ---------- | ----------------- | ------------------ | ------------------ | ------------------- | ---- | ------------------- |
| Read historical sales time-series at article/store level | SAP Customer Activity Repository (CARAB) — Multi-Level Demand Planning (SC4398) | — | — | — | — | — | No | CARAB is confirmed data source; custom API integration required |
| Automatic seasonality detection / classification of articles | No standard SAP product covers AI/ML-based seasonal detection | — | — | — | — | — | **Yes** | Gap — custom AI agent with time-series analysis (e.g. STL decomposition, FFT) required |
| Demand forecasting aligned to seasonal patterns | SAP IBP — Demand Forecasting (SC2989), Demand Sensing (SC701) | — | — | — | — | — | Maybe | IBP covers forecasting but not the initial seasonal classification step |
| Interactive dashboard/report of seasonal articles | Custom UI required | — | — | — | — | — | Yes | No standard SAP report for AI-detected seasonality; CAP + React UI recommended |
| Trigger replenishment workflow for seasonal articles | Custom workflow required | — | — | — | — | — | Yes | n8n workflow to adjust replenishment parameters upon seasonal flag |
| Notification/alert to business users | Custom notification | — | — | — | — | — | Yes | n8n workflow to send alerts to planners and managers |
| Season master data management | SAP S/4HANA — Retail Season (A2X) | `sap.s4:apiResource:CE_RETAILSEASON_0001:v1` | — | — | — | — | No | Season API available; no MCP server found — direct API integration |

### Key findings

- SAP CAR/CARAB is the confirmed data source for article/store level sales time-series and covers multi-level demand planning; no MCP server found for its APIs.
- No standard SAP product automatically detects seasonal articles via AI/ML from raw time-series data — this is the primary gap driving the need for a custom AI agent.
- SAP IBP covers demand forecasting and demand sensing but does not perform the upstream seasonal classification step the agent will handle.
- The Retail Season API (`CE_RETAILSEASON_0001`) in S/4HANA can be used to read or write season master data, but has no available MCP server.
- Three custom components are needed beyond the AI agent: a dashboard (CAP + React UI), a replenishment adjustment workflow (n8n), and a notification workflow (n8n).
- The solution follows the Retail Replenishment and Merchandise Distribution variant of the Plan to Fulfill E2E.

## Recommendations

### AI Agent for Seasonal Article Detection

#### Executive Summary

Custom AI agent on SAP BTP detects seasonal articles from CARAB time-series data.

#### Recommended Solution

Build a Python-based AI agent (A2A protocol) on SAP BTP that:
1. Connects to SAP CAR/CARAB to extract historical article/store level sales time-series.
2. Applies statistical and ML-based seasonality detection algorithms (e.g. STL decomposition, seasonal strength scoring, FFT analysis) to classify each article/store combination as seasonal or non-seasonal, and identifies the season window.
3. Exposes results via a CAP backend with a React (SAP UI5 Web Components) dashboard showing seasonal articles, confidence scores, and season periods.
4. Triggers an n8n workflow to adjust replenishment parameters for classified seasonal articles.
5. Sends notifications/alerts to demand planners, merchandise managers, supply chain analysts, and store managers via an n8n notification workflow.

#### Problem Statement

With thousands of articles across hundreds of stores, manually reviewing sales curves to identify seasonal demand patterns is not scalable. Seasonal misclassification leads to overstock outside the season and stockouts during peak periods, directly impacting profitability and customer satisfaction.

#### Affected User Roles

- Demand planners
- Merchandise / category managers
- Supply chain analysts
- Retail store managers

#### Important factors

##### Scalability through automation

Processing all article/store combinations automatically removes the manual bottleneck and allows continuous re-classification as new sales data arrives.

##### Actionable output

Results are not just informational — they directly trigger replenishment parameter adjustments and notify relevant stakeholders, closing the loop from detection to action.

##### Integration with existing SAP landscape

The agent reads directly from SAP CAR/CARAB (the system of record for retail sales data) and can optionally write seasonal classifications back to SAP S/4HANA via the Retail Season API.

#### Potential risks

##### Data quality dependency

Seasonality detection accuracy depends on sufficient historical data (typically 2+ years per article/store). Articles with sparse or noisy data may yield unreliable classifications.

##### Algorithm tuning required

Threshold parameters for what counts as "strongly seasonal" must be calibrated to the retailer's specific product mix and business rules; initial configuration may require iteration.

#### Recommended solution category

AI Agent, n8n Workflow, CAP Application (with React UI)

#### Intent fit

92%
