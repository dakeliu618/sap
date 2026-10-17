# Specification: classification-notification-workflow

> **Guidelines**: Read all applicable guidelines before executing ANY tasks below:
> - [guidelines.md](../guidelines.md) — Universal execution rules
> - [guidelines-n8n-workflow.md](../guidelines-n8n-workflow.md) — n8n workflow constraints

---

## Setup

- [ ] Create asset folder: `assets/workflows/classification-notification-workflow/`
- [ ] Ensure `solution.yaml` includes a `ref:` entry for `./assets/workflows/classification-notification-workflow/asset.yaml`

---

## Node Discovery

- [ ] Call `search-nodes-catalog` with queries: `["webhook", "set", "code", "respond webhook", "sap agent", "split out", "aggregate", "email", "notification"]` to confirm all planned nodes exist and capture exact `type` and `typeVersion` values before writing any workflow JSON.

---

## Workflow Design

**Purpose**: Receives a classification run summary from the detector agent and sends structured alert notifications to all configured stakeholder groups (demand planners, category managers, supply chain analysts, store managers).

**Trigger**: Webhook POST — receives a run summary with key metrics and a link to the dashboard.

**Input shape** (POST body):
```json
{
  "run_id": "string",
  "run_date": "ISO-8601 datetime",
  "total_classified": 1200,
  "seasonal_count": 340,
  "low_confidence_count": 45,
  "dashboard_url": "string",
  "top_seasonal_articles": [
    {"article_id": "string", "store_id": "string", "season_start_week": 10, "season_end_week": 20}
  ]
}
```

**Notification recipients**: configurable list of stakeholder groups, each with role and contact details.

**Node topology**:
1. **Webhook** (trigger) — named `"Classification Notification Received"`; `responseMode: "responseNode"`
2. **Code** (JavaScript) — named `"Build Notification Content"`:
   - `STAKEHOLDER_GROUPS` constant (ALL_CAPS, at top of node) — list of recipient groups: `[{role: "Demand Planner", email: "demand.planners@example.com"}, {role: "Category Manager", email: "category.managers@example.com"}, {role: "Supply Chain Analyst", email: "sc.analysts@example.com"}, {role: "Store Manager", email: "store.managers@example.com"}]`
   - Constructs notification payload for each group with role-specific message framing
   - Sticky note above: "Configuration: Update STAKEHOLDER_GROUPS with actual recipient email addresses or distribution list addresses for each role. Replace placeholder addresses before activating."
3. **Split Out** — split recipient groups into individual items for per-group notification
4. **SAP Agent** — named `"Compose Notification Message"`:
   - Composes a concise, role-appropriate notification message for each stakeholder group
   - Includes: run summary stats, number of seasonal articles identified, link to dashboard, call-to-action
   - Adapts message tone: planners get technical detail; store managers get simple headline + link
5. **Aggregate** — collects all sent notification results
6. **Code** (JavaScript) — named `"Build Notification Summary"` (executeOnce):
   - Counts total recipients notified
   - Constructs response: `{run_id, notified_count, status: "completed"}`
7. **Respond to Webhook** — returns the notification summary to the caller

- [ ] Write the complete workflow JSON to `assets/workflows/classification-notification-workflow/classification-notification-workflow.n8n.json`
  - Include `"description"` field at top level
  - No `"credentials"` blocks on any node
  - `"pinData": {}` placeholder

---

## pinData

- [ ] Call `pin-data-schemas` MCP tool with all node types used (deduplicated, exact typeVersions from catalog)
- [ ] Synthesize one sample per node per schema returned; merge into workflow `pinData`

---

## Asset Generation

- [ ] Run `node skills/n8n-workflow/scripts/generate-workflow-asset.js assets/workflows/classification-notification-workflow/classification-notification-workflow.n8n.json classification-notification-workflow <solution-name>` and paste output into `assets/workflows/classification-notification-workflow/asset.yaml`
- [ ] Fill in the `description` for the `kind: rest` API entry: "Receives a classification run summary and dispatches structured notifications to all stakeholder groups"

---

## MCP Server for Agent Consumption

The detector agent must invoke this workflow via MCP (not direct webhook). Complete Steps A–F from `n8n-workflow/references/execution.md`:

- [ ] **Step A** — Generate OpenAPI spec: `mkdir -p specification/classification-notification-workflow-mcp-server/api-specs && node skills/n8n-workflow/scripts/generate-webhook-openapi.js assets/workflows/classification-notification-workflow/classification-notification-workflow.n8n.json classification-notification-workflow > specification/classification-notification-workflow-mcp-server/api-specs/classification-notification-workflow-webhook-api.json`
- [ ] **Step B** — Create `specification/classification-notification-workflow-mcp-server/specification.md` referencing the REST ORD ID from the generated asset.yaml
- [ ] **Step C** — Invoke `mcp-translation-file` skill for asset `classification-notification-workflow-mcp-server`; copy generated files to `assets/classification-notification-workflow-mcp-server/mcp-translation/`
- [ ] **Step D** — Create `assets/classification-notification-workflow-mcp-server/asset.yaml` with `type: mcp-server`; derive `<mcp-card-ordId>` by appending `_mcp` to the `apiName` segment of the `kind: rest` ORD ID
- [ ] **Step E** — Add `- ref: ./assets/classification-notification-workflow-mcp-server/asset.yaml` to `solution.yaml`
- [ ] **Step F** — Add `requires` entry to `assets/seasonal-article-detector-agent/asset.yaml`; update `app/agent.py` system prompt to use the MCP tool name (not webhook URL)

---

## Validation

- [ ] Validate workflow and asset.yaml with `validate-n8n-workflow` MCP tool
- [ ] Fix any errors (expected: missing credentials are acceptable)
