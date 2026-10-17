# Specification: replenishment-adjustment-workflow

> **Guidelines**: Read all applicable guidelines before executing ANY tasks below:
> - [guidelines.md](../guidelines.md) — Universal execution rules
> - [guidelines-n8n-workflow.md](../guidelines-n8n-workflow.md) — n8n workflow constraints

---

## Setup

- [ ] Create asset folder: `assets/workflows/replenishment-adjustment-workflow/`
- [ ] Ensure `solution.yaml` includes a `ref:` entry for `./assets/workflows/replenishment-adjustment-workflow/asset.yaml`

---

## Node Discovery

- [ ] Call `search-nodes-catalog` with queries: `["webhook", "set", "switch", "if", "code", "respond webhook", "sap mcp client", "sap agent", "aggregate", "split out"]` to confirm all planned nodes exist and capture exact `type` and `typeVersion` values before writing any workflow JSON.

---

## Workflow Design

**Purpose**: Receives a list of seasonal article/store classifications from the detector agent, validates each, applies replenishment parameter adjustment logic, and responds with a summary of processed articles.

**Trigger**: Webhook POST — receives a JSON body containing an array of classified seasonal articles with their season windows.

**Input shape** (POST body):
```json
{
  "run_id": "string",
  "classifications": [
    {
      "article_id": "string",
      "store_id": "string",
      "classification": "SEASONAL",
      "confidence_score": 85,
      "season_start_week": 10,
      "season_end_week": 20,
      "seasonal_strength_index": 0.72
    }
  ]
}
```

**Node topology**:
1. **Webhook** (trigger) — named `"Replenishment Adjustment Received"`; `responseMode: "responseNode"`
2. **Split Out** — split `body.classifications` into individual items
3. **IF** — filter: `confidence_score >= 60`; true branch proceeds; false branch is a no-op path to Aggregate
4. **Code** (JavaScript) — named `"Build Replenishment Payload"`:
   - `SEASON_LEAD_WEEKS = 4` (weeks before season start to begin building stock)
   - Calculates: `order_start_week = season_start_week - SEASON_LEAD_WEEKS`
   - Constructs replenishment parameter update payload: `{article_id, store_id, replenishment_type: "SEASONAL", order_start_week, season_start_week, season_end_week, seasonal_strength_index}`
   - Sticky note above: "Configuration: SEASON_LEAD_WEEKS controls how many weeks before the season start the system should begin building stock. Adjust based on your supplier lead times."
5. **SAP Agent** — named `"Determine Replenishment Strategy"`:
   - Analyzes the replenishment payload and selects the appropriate replenishment strategy (push vs. pull, suggested reorder point multiplier) based on seasonal strength and confidence score
   - Outputs a structured strategy recommendation
6. **Aggregate** — collects all processed items (from both IF branches) into a results array
7. **Code** (JavaScript) — named `"Build Response Summary"` (executeOnce):
   - Counts total received, total processed (confidence ≥ 60%), total skipped (low confidence)
   - Constructs response: `{run_id, processed_count, skipped_count, status: "completed"}`
8. **Respond to Webhook** — returns the summary response to the caller

- [ ] Write the complete workflow JSON to `assets/workflows/replenishment-adjustment-workflow/replenishment-adjustment-workflow.n8n.json`
  - Include `"description"` field at top level
  - No `"credentials"` blocks on any node
  - `"pinData": {}` placeholder (will be populated in next step)

---

## pinData

- [ ] Call `pin-data-schemas` MCP tool with all node types used (deduplicated, exact typeVersions from catalog)
- [ ] Synthesize one sample per node per schema returned; merge into workflow `pinData`

---

## Asset Generation

- [ ] Run `node skills/n8n-workflow/scripts/generate-workflow-asset.js assets/workflows/replenishment-adjustment-workflow/replenishment-adjustment-workflow.n8n.json replenishment-adjustment-workflow <solution-name>` and paste output into `assets/workflows/replenishment-adjustment-workflow/asset.yaml`
- [ ] Fill in the `description` for the `kind: rest` API entry: "Receives seasonal article classifications and triggers replenishment parameter adjustments"

---

## MCP Server for Agent Consumption

The detector agent must invoke this workflow via MCP (not direct webhook). Complete Steps A–F from `n8n-workflow/references/execution.md`:

- [ ] **Step A** — Generate OpenAPI spec: `mkdir -p specification/replenishment-adjustment-workflow-mcp-server/api-specs && node skills/n8n-workflow/scripts/generate-webhook-openapi.js assets/workflows/replenishment-adjustment-workflow/replenishment-adjustment-workflow.n8n.json replenishment-adjustment-workflow > specification/replenishment-adjustment-workflow-mcp-server/api-specs/replenishment-adjustment-workflow-webhook-api.json`
- [ ] **Step B** — Create `specification/replenishment-adjustment-workflow-mcp-server/specification.md` referencing the REST ORD ID from the generated asset.yaml
- [ ] **Step C** — Invoke `mcp-translation-file` skill for asset `replenishment-adjustment-workflow-mcp-server`; copy generated files to `assets/replenishment-adjustment-workflow-mcp-server/mcp-translation/`
- [ ] **Step D** — Create `assets/replenishment-adjustment-workflow-mcp-server/asset.yaml` with `type: mcp-server`; derive `<mcp-card-ordId>` by appending `_mcp` to the `apiName` segment of the `kind: rest` ORD ID
- [ ] **Step E** — Add `- ref: ./assets/replenishment-adjustment-workflow-mcp-server/asset.yaml` to `solution.yaml`
- [ ] **Step F** — Add `requires` entry to `assets/seasonal-article-detector-agent/asset.yaml`; update `app/agent.py` system prompt to use the MCP tool name (not webhook URL)

---

## Validation

- [ ] Validate workflow and asset.yaml with `validate-n8n-workflow` MCP tool
- [ ] Fix any errors (expected: missing credentials are acceptable)
