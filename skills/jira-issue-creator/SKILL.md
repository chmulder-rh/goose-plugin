---
name: jira-issue-creator
description: Create RHCLOUD Jira issues with validated fields and enriched descriptions via the Atlassian Rovo MCP
---

# Jira Issue Creator

Use this skill to create RHCLOUD Jira issues. Invoke it when the user asks to create a
Jira ticket, story, bug, spike, epic, or any RHCLOUD work item.

This skill is the **conversational front-end only**. It gathers and confirms fields
from the user, then hands off to a deterministic pipeline script for everything else
(validation, field mapping, and the actual Jira API call). It does not perform
validation, mapping, or API calls itself.

⚠️ **Supporting files live alongside this file.** This skill's Python scripts
(`scripts/get_recipe_questions.py`, `scripts/create_jira_issue_pipeline.py`) and
recipes (`recipes/jira-issue-mapper.yaml`, `recipes/create-jira-issue.yaml`) are
supporting files bundled in subfolders of this same skill directory — the whole
skill is self-contained. Resolve this skill's own directory once at the start of
the session and reuse it for every script/recipe path below:

```bash
SKILL_DIR="$HOME/.config/goose/skills/create-jira-issue"
```

(If this skill was loaded from a different install location — e.g. a project-level
`.agents/skills/create-jira-issue/` — use that directory instead. `$SKILL_DIR` below
always refers to the directory that directly contains this `SKILL.md` file.)

⚠️ **Single source of truth for questions/options:** Do NOT hardcode the list of
teams, issue types, or activity types anywhere in this skill. They live only in
`recipes/jira-issue-mapper.yaml`'s `parameters:` block. At the start of Phase 1,
run:

```bash
python3 "$SKILL_DIR/scripts/get_recipe_questions.py" \
  "$SKILL_DIR/recipes/jira-issue-mapper.yaml"
```

This prints a JSON array of `{key, input_type, requirement, description, options, default}`
for every parameter the mapper recipe accepts, in order. Use the `description` as the
question text and `options` as the choices to present for every parameter where
`input_type` is `"select"`. If the recipe file is ever changed (options added/removed/
renamed), this script will reflect it automatically — never ask about options you
recall from a previous run or from this document.

Use the Todo extension to track progress: create a checklist at the start covering
all phases below, and check items off as they complete.

## Phase 1: Gather Fields

Parse the invocation text for:
- **summary**: the main phrase or first sentence
- **prefix hint**: `[text]` in brackets → extract as prefix (strip brackets)
- **assignee hint**: "assign to <identifier>", "assign to me", "assign to bot"

### Step 0: Load Questions and Options

Run the `get_recipe_questions.py` command shown above. Keep its output in context
for the rest of this phase — every question you ask and every set of options you
present must come from this output, not from memory.

### Step 1: Resolve Assignee to Account ID

All assignees must be resolved to a **Jira account ID** before delegation.

⚠️ All `cloudId` arguments in this skill (to `lookupJiraAccountId`, `editJiraIssue`,
etc.) must come from the `ATLASSIAN_INSTANCE` environment variable — never hardcode
a specific Atlassian site hostname. Resolve it once (e.g. `echo $ATLASSIAN_INSTANCE`)
and reuse it for every tool call below.

- `"me"`           → run `git config user.email`, then call `lookupJiraAccountId` with
                     `cloudId: <value of $ATLASSIAN_INSTANCE>` and `searchString: <email>`
                     → use the returned account ID; assignee_type = "user"
- `"bot"`          → account ID is `712020:c6b31fa1-eaf5-4921-af5b-cb625f24bb1a` (no lookup needed);
                     assignee_type = "bot"
- contains `"@"`   → call `lookupJiraAccountId` with the email as searchString
                     → use returned account ID; assignee_type = "user"
- other identifier → call `lookupJiraAccountId` with the identifier as searchString
                     → use returned account ID; assignee_type = "user"
- not provided     → assignee_account_id = "unassigned"; assignee_type = "unassigned"

### Step 2: Ask for Team

⚠️ **Ask this question alone. Do not ask any other questions in this message. Wait for the answer.**

Use the `description` and `options` for the `team` parameter from Step 0's output.
Infer the best option from context and present it as the recommendation.

After the user responds, **echo back the full name of the option they selected** (e.g. "✅ Team: Console - Framework") before continuing to the next step.

### Step 3: Ask for Activity Type

⚠️ **Ask this question alone. Do not ask any other questions in this message. Wait for the answer.**

Use the `description` and `options` for the `activity_type` parameter from Step 0's output.

Infer from summary keywords:
- CVE, security, vulnerability, compliance → **Security & Compliance**
- bug, fix, crash, flaky, CI, refactor, lint, test → **Quality / Stability / Reliability**
- incident, hotfix, escalation, production → **Incidents & Support**
- upgrade, migration, architecture, DX, docs → **Future Sustainability**
- training, workshop, learning → **Associate Wellness & Development**
- feature, dashboard, new capability → **Product / Portfolio Work**

(These keyword hints are conversational suggestions only — the actual list of valid
options always comes from Step 0's output, never from this list.)

After the user responds, **echo back the full name of the option they selected** (e.g. "✅ Activity Type: Future Sustainability") before continuing to the next step.

### Step 4: Ask for Issue Type

⚠️ **Ask this question alone. Do not ask any other questions in this message. Wait for the answer.**

Use the `description` and `options` for the `issue_type` parameter from Step 0's output.

Infer from summary keywords:
- bug, fix, broken, crash → **Bug**
- CVE, vulnerability, exploit → **Vulnerability**
- risk, threat, exposure → **Risk**
- weakness, CWE → **Weakness**
- spike, research, investigate, explore → **Spike**
- epic, initiative, quarter → **Epic**
- default → **Story**

(These keyword hints are conversational suggestions only — the actual list of valid
options always comes from Step 0's output, never from this list.)

After the user responds, **echo back the full name of the option they selected** (e.g. "✅ Issue Type: Story") before continuing to the next step.

### Step 5: Ask for Prefix

⚠️ **Ask this question alone. Do not ask any other questions in this message. Wait for the answer.**

Suggest the current working directory basename as the prefix. Present options:
1. `[<cwd basename>]` ← suggested
2. No prefix
3. Other

After the user responds, **echo back the prefix that will be applied** (e.g. "✅ Prefix: [frontend-components]") before continuing to the next step.

### Step 6: Ask for Assignee (if not already resolved in Step 1)

⚠️ **Ask this question alone. Do not ask any other questions in this message. Wait for the answer.**

Options:
1. Unassigned
2. Assign to me
3. Assign to bot
4. Other (enter email or username)

Resolve the answer using `lookupJiraAccountId` as described in Step 1.

After resolving, **echo back the display name** (e.g. "✅ Assignee: Charles Mulder") before continuing.

### Step 7: Bot Label
If assignee_type is "bot", note that the ticket needs the label "hcc-ai-bot".

---

## Phase 2: Run the Pipeline Script

### Step 8: Invoke the Deterministic Pipeline

Once all fields are confirmed, run the pipeline script via the shell tool. Do NOT
call any recipe or the Jira API directly yourself — the script owns the entire
validate → map → create sequence:

```bash
python3 "$SKILL_DIR/scripts/create_jira_issue_pipeline.py" \
  --summary "<confirmed summary text, WITHOUT prefix>" \
  --prefix "<confirmed prefix, or empty string if none>" \
  --team "<confirmed team name>" \
  --issue-type "<confirmed issue type>" \
  --activity-type "<confirmed activity type>" \
  --assignee-account-id "<resolved Jira account ID, or 'unassigned'>"
```

The script prints exactly one JSON object to stdout. Do NOT reason about or
reconstruct the ticket fields yourself — use only the values in that JSON output.

### Step 9: Handle the Pipeline Result

Parse the JSON object's `stage` field:

- `"created"` (success=true) → ticket was created successfully. Show immediately:
  ```
  Created <issue_key>
  View: <issue_url>
  ```

- `"validation_failed"` → show the `errors` array to the user, return to Step 2
  to correct the invalid fields, then retry Step 8.

- `"env_error"` → a required environment variable (`ATLASSIAN_AUTH`,
  `ATLASSIAN_CLOUD_ID`, or `ATLASSIAN_INSTANCE`) is missing. Show the `error`
  message and ask the user to export it before retrying — do not attempt to
  guess or fabricate a value yourself.

- `"mapper_error"`, `"creator_error"`, or `"creation_failed"` → show the `error`
  message to the user. These indicate a pipeline/API failure rather than a bad
  input value; do not silently retry — report the error and ask how to proceed.

---

## Phase 3: Description and Approval

### Step 10: Generate an Enriched Description

Write a comprehensive description using the summary and any codebase context available:
- **Background**: Technical context and motivation
- **Scope**: Affected files, components, or systems (if determinable)
- **Acceptance Criteria**: Functional requirements as checkboxes, with test coverage
  requirements tailored to the issue type:
  - Bug: unit test for fix, regression test, E2E validation
  - Story/Feature: unit, component, integration, and E2E tests
  - Spike: research questions, deliverables, time-box
  - Vulnerability/CVE: remediation steps, security verification tests
  - Epic/Risk: success criteria and measurable outcomes
- **Additional requirements**: documentation, accessibility, performance (if relevant)

### Step 11: Show Description and Ask for Approval

Display the full proposed description as plain text, then ask:

> Approve this description for `<issue_key>`?
> 1. **Approve and update ticket**
> 2. **Request changes** — describe what to change
> 3. **Cancel** — skip description update

- Approved → Step 12
- Changes needed → incorporate feedback, repeat Step 10
- Cancelled → stop, show ticket URL only

### Step 12: Update the Ticket Description

Call `editJiraIssue`:
```
cloudId:       <value of $ATLASSIAN_INSTANCE>
issueIdOrKey:  <issue_key from Step 9>
contentFormat: "markdown"
fields:        { "description": <approved description as markdown> }
```

---

## Phase 4: Confirm

### Step 13: Final Confirmation

```
Created <issue_key>
├── Type:          <issue type>
├── Summary:       <final summary>
├── Team:          <team>
├── Assignee:      <display name or "Unassigned">
├── Activity Type: <activity type>
└── View:          <issue_url>
```
