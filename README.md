# chmulder-goose-plugin

A [goose plugin](https://goose-docs.ai/docs/guides/context-engineering/plugins) bundling personal/team goose skills.

## Skills

### `jira-issue-creator`

Create RHCLOUD Jira issues with deterministic field validation, mapping, and Jira API calls.

**Architecture:**
- **Layer 1:** Conversational skill (user Q&A, numbered options)
- **Layer 2:** Python scripts (pure field validation & mapping)
- **Layer 3:** Recipes (MCP tool calls only, explicit extension scoping)

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for design rationale and [`skills/jira-issue-creator/SKILL.md`](./skills/jira-issue-creator/SKILL.md) for the full workflow.

[Atlassian Rovo MCP Tools](https://support.atlassian.com/atlassian-ai-gateway/docs/supported-tools/)

## Installation

```bash
goose plugin install <repo-url>
```

Skill becomes available as `jira-issue-creator`.

## Requirements

```bash
export GOOSE_MODE=auto
export ATLASSIAN_AUTH="<Bearer token>"
export ATLASSIAN_CLOUD_ID="<Atlassian tenant UUID>"
export ATLASSIAN_INSTANCE="company.atlassian.net"
```

## Testing

```bash
uv run pytest
```

Mocks all subprocess calls; runs fast with no credentials or network access.
