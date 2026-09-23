---
name: jira-issue-creator
description: Create RHCLOUD Jira issues with validated fields and enriched descriptions via the Atlassian Rovo MCP
---

# Workflow

Prerequisite: Skill installed at `~/.config/goose/skills/jira-issue-creator/`.

## 1. Infer ticket title

Infer from the skill prompt

## 2. Resolve assignee

Default: `unassigned`

If assigned to `<identifier>` (email, username, etc.) then run:

```shell
python3 ~/.config/goose/skills/jira-issue-creator/scripts/run_recipe.py \
  --recipe recipes/resolve-assignee.yaml \
  --params '{"search_string": "<identifier>"}'
```

If "assign to bot" then use `712020:c6b31fa1-eaf5-4921-af5b-cb625f24bb1a` as `<identifier>`.

Returns:

```jsonc
{
  "success": <boolean>,           // true if lookup succeeded
  "account_id": <string>,         // Jira account ID or "" on failure
  "display_name": <string>,       // User's full name
  "error": <string>               // Error message (empty if success)
}
```

If lookup fails, report the error and ask the user to retry with a different identifier, or choose "unassigned".

---

## 3. Ask for title prefix

Suggest the current working directory basename as the prefix:

1. `[<cwd basename>]` (suggested)
2. No prefix
3. Other (custom prefix)

Wait for user input before proceeding. After the user responds, echo back the prefix to confirm (e.g. "✅ Prefix: [frontend-components]").

---

## 4. Load questions

```shell
python3 ~/.config/goose/skills/jira-issue-creator/scripts/get_recipe_questions.py \
  ~/.config/goose/skills/jira-issue-creator/recipes/jira-issue-mapper.yaml
```

Returns:

```jsonc
[
    {
        "key": <string>,            // eg. team or issue_type
        "input_type": <string>,     // select or string
        "requirement": <string>,    // required or optional
        "description": <string>,    // question text
        "options": <array<string>|NULL>,    // list of choices or null for free text
        "default": <string|NULL>    // default value or null
    }
]
```

---

## 5. Use todo extension to ask questions one at a time

**Create a todo list** using the `todo` extension with one item per question:

**For each question in order:**

1. **Display the question** with description and numbered options
2. **Show a suggested answer** based on keywords in the summary (if applicable)
3. **Wait for user input** — do not proceed to the next question
4. **Mark as complete** in the todo (change `[ ]` to `[x]`)
5. **Echo back the answer** to confirm

Only after the current question is answered should you ask the next one.
Omit questions for fields already resolved (summary, prefix, assignee).

---

## 6. Validate and Map fields

Once all questions are answered and assignee is resolved, call the validation and mapping script:

```shell
python3 ~/.config/goose/skills/jira-issue-creator/scripts/validate_and_map_fields.py \
  --summary <string> \
  --prefix <string> \
  --team <string> \
  --issue-type <string> \
  --activity-type <string> \
  --assignee-account-id <string>
```

Returns:

```jsonc
{
  "valid": <boolean>,
  "errors": <string[]>,           // empty if valid
  "mapped_summary": <string>,     // with prefix applied
  "issue_type": <string>,
  "team_field_value": <uuid>,
  "activity_type_field_value": <object>,
  "security_field_value": <object|null>,
  "assignee_account_id": <string>
}
```

If validation fails, report errors and return. If valid, proceed to issue creation.

## 7. Create Issue

```shell
python3 ~/.config/goose/skills/jira-issue-creator/scripts/run_recipe.py \
  --recipe recipes/create-jira-issue.yaml \
  --params '{"mapped_summary": <string>, "issue_type": <string>, "team_field_value": <uuid>, "activity_type_field_value": <object>, "security_field_value": <object|null>, "assignee_account_id": <string>}'
```

Returns:

```jsonc
{
  "success": <boolean>,
  "issue_key": <string>,          // e.g., "RHCLOUD-1234" or "" on failure
  "issue_url": <string>,          // browse URL or "" on failure
  "error": <string>               // error message (empty if success)
}
```

---

## 8. Enrich Description

Generate a comprehensive markdown description based on the summary and issue type:

- **Background:** Technical context and motivation
- **Scope:** Affected files, components, systems
- **Acceptance Criteria:** Requirements and test coverage
- **Additional Requirements:** Docs, accessibility, performance

Display the proposed description and ask for approval:

```
[description text]

Approve this description for CONSOLE-1234?

[1] Approve and update ticket
[2] Request changes — describe what to change
[3] Cancel — skip description update
```

If approved, update via recipe:

```shell
python3 ~/.config/goose/skills/jira-issue-creator/scripts/run_recipe.py \
  --recipe recipes/update-jira-issue-description.yaml \
  --params '{"issue_key": <string>, "description": <string>}'
```

Returns:

```jsonc
{
  "success": <boolean>,
  "error": <string>               // error message (empty if success)
}
```

---

## 9. Show Final Summary

Display the created ticket with all details:

```
Created RHCLOUD-1234
├── Type:          Bug
├── Summary:       Fix authentication timeout issue
├── Team:          Console - UI
├── Assignee:      Charles Mulder (chmulder@redhat.com)
├── Activity Type: Quality / Stability / Reliability
└── View:          https://$ATLASSIAN_INSTANCE/browse/RHCLOUD-1234
```

---

## Troubleshooting

- **First-time OAuth**: Headless recipe runs cannot display browser auth prompts. If authentication fails, run `goose session` once interactively to complete the Atlassian OAuth flow.
- **Direct tool calls**: Never call `rovo__*` MCP tools directly from the top-level session. Always go through `run_recipe.py`.

---

## Key Principles

✅ **No hardcoded options** — all questions and choices fetched from mapper recipe  
✅ **Todo-driven workflow** — enforces one question at a time  
✅ **Pure script validation** — all business logic in Python (not LLM)  
✅ **Deterministic mapping** — one source of truth for field values  
✅ **Explicit delegation** — recipes called via shell, not direct rovo tool calls
