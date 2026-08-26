# jira-issue-creator: Architecture & Design

---

## Overview

The jira-issue-creator skill implements a **three-layer deterministic pipeline** for creating RHCLOUD Jira issues:

1. **Layer 1 (SKILL.md):** Conversational front-end only — gathers user input
2. **Layer 2 (Python scripts):** Deterministic logic — validates fields, maps values
3. **Layer 3 (Recipes):** MCP tool calls only — calls Jira API

This separation ensures:
- ✅ Reproducible, predictable behavior (no LLM improvisation)
- ✅ Fast validation (pure Python, ~100x vs. LLM-based)
- ✅ Clear accountability (know exactly where each step happens)
- ✅ Testable, maintainable code

---

## Architecture Layers

### Layer 1: SKILL.md (Conversational Q&A)
- Asks user for: summary, team, issue type, activity type, prefix, assignee
- Presents numbered options [1], [2], [3] for all choices
- Zero tools, zero API calls
- Delegates all validation/mapping/API to Layer 2 & 3

### Layer 2: Python Scripts (Deterministic Logic)

**`validate_and_map_fields.py`**
- Pure field validation (no tools, no API, no LLM)
- Maps human-readable inputs to Jira API values (UUIDs, custom field objects)
- Returns JSON: `{valid, errors[], mapped_summary, team_field_value, ...}`
- Single source of truth for allowed teams, issue types, activity types

**`run_recipe.py`**
- Generic recipe orchestrator (reusable for any workflow)
- Handles GOOSE_MODE=auto, environment variables, JSON parsing
- Takes `--recipe <path>` and `--params <json>` as input
- Returns recipe's structured output as-is

**`get_recipe_questions.py`**
- Extracts canonical questions from recipe YAML files
- Used by SKILL.md Step 0 to load allowed options

### Layer 3: Recipes (MCP Tool Calls Only)

**`create-jira-issue.yaml`**
- Calls `createJiraIssue` MCP (extensions: [rovo])
- Receives pre-validated, pre-mapped field values from Layer 2
- Returns JSON: `{success, issue_key, issue_url, error}`

**`update-jira-issue-description.yaml`**
- Calls `editJiraIssue` MCP (extensions: [rovo])
- Updates issue description after creation
- Returns JSON: `{success, error}`

---

## Data Flow

```
SKILL.md (Layer 1)
  ↓ collect user input
validate_and_map_fields.py (Layer 2a)
  ↓ validation + mapping (pure Python, ~1ms)
run_recipe.py (Layer 2b)
  ↓ orchestrator
create-jira-issue.yaml (Layer 3a)
  ↓ MCP createJiraIssue call
run_recipe.py (Layer 2b)
  ↓ orchestrator
update-jira-issue-description.yaml (Layer 3b)
  ↓ MCP editJiraIssue call
SKILL.md (Layer 1)
  ↓ confirm to user
```

---

## Key Design Decisions

### 1. Validation in Python, Not Recipes

**Why:** Field validation is deterministic data transformation, not reasoning.
- ✅ Pure Python: testable, fast, no LLM variance
- ❌ LLM-based recipe: expensive, non-deterministic, wastes inference

**Result:** ~100x faster validation, single source of truth

### 2. Generic Recipe Runner

**Why:** Eliminates code duplication across pipeline stages.
- ✅ One `run_recipe.py` handles any recipe with JSON params
- ❌ Two hardcoded pipeline scripts (create_jira_issue, update_jira_description)

**Result:** Reusable pattern for other multi-step MCP workflows

### 3. Code-Native Recipes

**Why:** Clear function signatures, easier to debug, follows goose core patterns.
- ✅ ~30-line recipes with function-call style prompts
- ❌ ~90-line recipes with verbose instructions blocks

**Result:** 35% smaller recipes, more maintainable

### 4. Explicit Extension Scoping

**Why:** Every recipe declares exactly what tools it uses.
- ✅ Each recipe has `extensions:` list (explicitly includes only what it needs)
- ❌ Implicit inheritance (silently includes developer, delegate, etc.)

**Result:** No unintended tool access, no self-delegation bugs

---

## Why This Architecture Works

### Reliability
- Each stage is a separate OS process (`goose run --recipe`)
- Stages hand off via structured JSON (response.json_schema)
- No LLM can improvise or skip a stage
- No soft delegation (sub_recipes), only hard shell-based execution

### Maintainability
- Clear separation: logic (scripts) vs. tools (recipes)
- Single source of truth for field validation (validate_and_map_fields.py)
- Easy to debug (explicit Python logic, not prose instructions)
- Easy to extend (add new recipes with run_recipe.py)

### Performance
- Field validation: ~100x faster (Python vs. LLM)
- No LLM latency on deterministic transformations
- Recipes are thin wrappers, minimal LLM context

### Testability
- Pure Python scripts are unit-testable
- Recipes have structured output contracts
- No fuzzy prose interpretations

---

## Environment Requirements

- `GOOSE_MODE=auto` (required for nested `goose run` calls)
- `ATLASSIAN_AUTH` (Bearer token for Rovo MCP)
- `ATLASSIAN_CLOUD_ID` (Atlassian tenant UUID)
- `ATLASSIAN_INSTANCE` (Atlassian site hostname, e.g., company.atlassian.net)

---

## Reference Pattern

This architecture can serve as a reference for building other multi-step MCP workflows in goose:

1. **Layer 1:** Conversational skill (user interaction)
2. **Layer 2:** Python scripts (business logic, deterministic)
3. **Layer 3:** Recipes (MCP tool calls, explicit extensions)

The key insight: **Scripts for logic, Recipes for tools.**
