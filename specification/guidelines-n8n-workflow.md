# n8n Workflow Guidelines

Technical constraints and patterns for building n8n workflow automations. Follow these throughout specification execution.

## Key Constraints

- If the solution also requires a CAP application, create CAP FIRST before any n8n workflow
- **NEVER** answer with the n8n URL in the message
- **NEVER** add a `"credentials"` block to any node in the workflow JSON. Credential blocks embed IDs and names that are instance-specific and will cause import errors on any other n8n instance.

## Workflow Structure

- Each workflow gets its own folder under `assets/workflows/`: `assets/workflows/<workflow-name>/`
- `sourceRoot` in `asset.yaml` MUST be `.` (the schema default) — never `workflows` or any other path
- Each workflow is a single `*.n8n.json` file
- Validate JSON is well-formed after creation

## Specification Checklist

When executing a specification for an n8n workflow asset, complete the following tasks:

- [ ] Ensure that each workflow gets its own asset folder under `assets/workflows/<workflow-name>/`.
- [ ] Ensure the asset type is `n8nworkflow` declared inside `metadata.type`. Do not derive the type from naming conventions
- [ ] Ensure `connections` in JSON reference nodes by `name`, not `id`
- [ ] **If the solution contains an agent that should invoke this workflow**: complete the MANDATORY-when-applicable section in `skills/n8n-workflow/references/execution.md` (Steps A–F) — create the mcp-server translation card, update `solution.yaml`, and add a `requires` entry plus system prompt instruction to every agent asset that should call this workflow. This task must be ticked regardless of which skill (agent or n8n) ran first.
- [ ] Validate all workflow and asset.yaml files with the `validate-n8n-workflow` mcp tool. 
