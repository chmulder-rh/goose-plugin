# chmulder-goose-tools

A [goose plugin](https://goose-docs.ai/docs/guides/context-engineering/plugins)
bundling personal/team goose skills. Currently contains one skill:

## Skills

### `jira-issue-creator`

Create RHCLOUD Jira issues conversationally, with deterministic field validation,
mapping, and creation via the Atlassian Rovo MCP extension.

The skill is a thin conversational front-end only — it gathers and confirms
fields from the user, then hands off to a deterministic Python pipeline script
that runs two goose recipes in sequence (a validate/map recipe with no tools,
then a single-purpose create recipe scoped only to the `atlassian-rovo`
extension), using each recipe's `response.json_schema` structured output as
the hand-off contract between stages. See
`skills/jira-issue-creator/SKILL.md` for the full workflow.

## Installing

```bash
goose plugin install <this-repo-url>
```

This copies the plugin into `~/.agents/plugins/chmulder-goose-tools/` (or the
project-level equivalent) and makes its skill available as
`chmulder-goose-tools:jira-issue-creator`.

To get automatic update checks:

```bash
goose plugin install --auto-update <this-repo-url>
```

## Structure

```
chmulder-goose-tools/
├── plugin.json
├── README.md
└── skills/
    └── jira-issue-creator/
        ├── SKILL.md
        ├── recipes/
        │   ├── jira-issue-mapper.yaml
        │   └── create-jira-issue.yaml
        └── scripts/
            ├── get_recipe_questions.py
            └── create_jira_issue_pipeline.py
```

## Requirements

- `GOOSE_MODE=auto` must be set for the session (nested `goose run` calls used
  by the pipeline script fail under `approve`/`smart_approve` mode).
- The `atlassian-rovo` MCP extension must be configured with valid
  `ATLASSIAN_AUTH`, `ATLASSIAN_CLOUD_ID`, and `ATLASSIAN_INSTANCE` credentials
  (see `skills/jira-issue-creator/recipes/create-jira-issue.yaml`).
