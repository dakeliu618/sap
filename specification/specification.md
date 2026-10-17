# Specification

> **Guidelines**: Read [guidelines.md](./guidelines.md) before executing ANY tasks below.

Check off items as completed.

## Solution Setup

- [x] Create asset directories:
  ```bash
  mkdir -p assets/seasonal-article-detector-agent/
  mkdir -p assets/workflows/replenishment-adjustment-workflow/
  mkdir -p assets/workflows/classification-notification-workflow/
  ```
- [x] Invoke `setup-solution` skill to create `solution.yaml` and `asset.yaml` files for every asset (agent + both workflows + their MCP server assets once generated)
- [x] Validate all `asset.yaml` and `solution.yaml` files exist and are well-formed

## Asset Implementation

> **Order matters**: Build the two n8n workflows first (they establish the webhook ORD IDs needed by the agent's MCP wiring). Then build the agent. The MCP server generation (Steps A–F in each workflow spec) links everything together.

- [x] Execute `specification/replenishment-adjustment-workflow/specification.md` (all items) — includes MCP server generation Steps A–F
- [x] Execute `specification/classification-notification-workflow/specification.md` (all items) — includes MCP server generation Steps A–F
- [x] Execute `specification/seasonal-article-detector-agent/specification.md` (all items) — after both workflow MCP servers exist
- [x] Cross-implementation compatibility check:
  - Verify the agent's `asset.yaml` `requires` section references both workflow MCP server ORD IDs (derived from each workflow's `asset.yaml` `kind: rest` entry with `_mcp` appended to the `apiName` segment)
  - Verify `app/agent.py` system prompt contains tool invocation instructions for both workflow MCP tools (not webhook URLs)
  - Verify both workflow webhook input shapes match what the agent tools send (article/store classification records for replenishment; run summary for notification)
  - Verify `solution.yaml` references all assets: agent, both workflows, both MCP servers
  - Fix any mismatches before proceeding

## Example Data

> When the user provides example article/store sales time-series data, use it to:
> - Validate the `run_seasonality_detection` tool produces sensible seasonal/non-seasonal classifications
> - Confirm the season window detection (start/end week) aligns with visible demand peaks in the sample data
> - Tune the `SEASONAL_STRENGTH_THRESHOLD` default if the example data suggests a different baseline
> - Generate realistic `mcp-mock.json` entries for the `read_carab_timeseries` tool
