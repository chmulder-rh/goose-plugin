#!/usr/bin/env python3
"""
create_jira_issue_pipeline.py — deterministic "Foreman" for RHCLOUD Jira ticket creation.

This script contains ZERO creative/LLM logic of its own. It hardcodes a two-stage
pipeline of `goose run --recipe ...` invocations, using each recipe's
`response.json_schema` structured output as the deterministic hand-off contract
between stages:

    Stage A: recipes/jira-issue-mapper.yaml
        Validates human-friendly fields and maps them to raw Jira API values.
    Stage B: recipes/create-jira-issue.yaml
        Takes the mapped values and makes the single createJiraIssue MCP call.

Usage:
    python3 create_jira_issue_pipeline.py \
        --summary "Fix bug in login page" \
        --prefix "" \
        --team "Console - UI" \
        --issue-type "Bug" \
        --activity-type "Quality / Stability / Reliability" \
        --assignee-account-id "unassigned"

Prints a single JSON object to stdout describing the final outcome, e.g.:
    {"stage": "created", "success": true, "issue_key": "RHCLOUD-1234",
     "issue_url": "https://<ATLASSIAN_INSTANCE>/browse/RHCLOUD-1234", "error": ""}

or, if a required environment variable is missing:
    {"stage": "env_error", "success": false, "error": "..."}

or, if validation failed:
    {"stage": "validation_failed", "success": false, "errors": ["..."]}

or, if a stage crashed / produced unparsable output:
    {"stage": "mapper_error"|"creator_error", "success": false, "error": "..."}

Requires GOOSE_MODE=auto to be effective for the session (nested `goose run`
calls will fail under approve/smart_approve mode).

Requires the following environment variables to already be exported (this script
never hardcodes a specific organization's Atlassian tenant or credentials):
    ATLASSIAN_AUTH      - Bearer token for the Atlassian Rovo MCP server
    ATLASSIAN_CLOUD_ID  - UUID of the Atlassian Cloud tenant (for MCP server auth)
    ATLASSIAN_INSTANCE  - Atlassian site hostname, e.g. "yourcompany.atlassian.net"
                          (used as the `cloudId` argument to Jira tool calls)
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# This script lives at <skill-dir>/scripts/create_jira_issue_pipeline.py, and the
# recipes it runs live at <skill-dir>/recipes/*.yaml (both bundled inside this
# skill directory so the whole skill is self-contained and portable as a unit —
# e.g. for later packaging as a plugin). Resolve everything relative to this
# file's own location; never assume a fixed goose config root.
SKILL_DIR = Path(__file__).resolve().parent.parent
RECIPES_DIR = SKILL_DIR / "recipes"
MAPPER_RECIPE = RECIPES_DIR / "jira-issue-mapper.yaml"
CREATOR_RECIPE = RECIPES_DIR / "create-jira-issue.yaml"

REQUIRED_ENV_VARS = ["ATLASSIAN_AUTH", "ATLASSIAN_CLOUD_ID", "ATLASSIAN_INSTANCE"]


def check_required_env_vars() -> list:
    """Return a list of required env var names that are missing or empty."""
    return [name for name in REQUIRED_ENV_VARS if not os.environ.get(name, "").strip()]


def run_recipe(recipe_path: Path, params: dict) -> dict:
    """Run a goose recipe non-interactively and parse its final structured-output line."""
    cmd = ["goose", "run", "--recipe", str(recipe_path), "-q"]
    for key, value in params.items():
        cmd += ["--params", f"{key}={value}"]

    # GOOSE_MODE=auto is required for non-interactive nested `goose run` calls
    # to succeed (approve/smart_approve mode blocks on tool approval with no
    # TTY to prompt). Set it explicitly here rather than relying on the
    # parent session/shell having it exported session-wide, which has proven
    # unreliable in practice.
    env = {**os.environ, "GOOSE_MODE": "auto"}

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)

    if result.returncode != 0:
        raise RuntimeError(
            f"goose run failed (exit {result.returncode}) for {recipe_path.name}: "
            f"{result.stderr.strip()[-2000:]}"
        )

    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"No output from {recipe_path.name}. stderr: {result.stderr.strip()[-2000:]}")

    last_line = lines[-1]
    try:
        return json.loads(last_line)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Could not parse structured JSON output from {recipe_path.name}: {e}. "
            f"Last line was: {last_line!r}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic RHCLOUD Jira ticket creation pipeline")
    parser.add_argument("--summary", required=True)
    parser.add_argument("--prefix", default="")
    parser.add_argument("--team", required=True)
    parser.add_argument("--issue-type", required=True, dest="issue_type")
    parser.add_argument("--activity-type", required=True, dest="activity_type")
    parser.add_argument("--assignee-account-id", required=True, dest="assignee_account_id")
    args = parser.parse_args()

    missing_env_vars = check_required_env_vars()
    if missing_env_vars:
        print(json.dumps({
            "stage": "env_error",
            "success": False,
            "error": "Missing required environment variable(s): " + ", ".join(missing_env_vars) +
                     ". Export ATLASSIAN_AUTH, ATLASSIAN_CLOUD_ID, and ATLASSIAN_INSTANCE before running.",
        }))
        return 1

    atlassian_instance = os.environ["ATLASSIAN_INSTANCE"].strip()

    # Stage A: Map
    try:
        mapped = run_recipe(
            MAPPER_RECIPE,
            {
                "summary": args.summary,
                "prefix": args.prefix,
                "team": args.team,
                "issue_type": args.issue_type,
                "activity_type": args.activity_type,
                "assignee_account_id": args.assignee_account_id,
            },
        )
    except Exception as e:
        print(json.dumps({"stage": "mapper_error", "success": False, "error": str(e)}))
        return 1

    if not mapped.get("valid", False):
        print(json.dumps({
            "stage": "validation_failed",
            "success": False,
            "errors": mapped.get("errors", ["Unknown validation error"]),
        }))
        return 1

    security = mapped.get("security_field_value") or {}
    security_name = security.get("name", "") if isinstance(security, dict) else ""

    activity_value = ""
    activity_field = mapped.get("activity_type_field_value") or {}
    if isinstance(activity_field, dict):
        activity_value = activity_field.get("value", "")

    # Stage B: Create
    try:
        created = run_recipe(
            CREATOR_RECIPE,
            {
                "mapped_summary": mapped["mapped_summary"],
                "issue_type": mapped["issue_type"],
                "team_field_value": mapped["team_field_value"],
                "activity_type_value": activity_value,
                "security_field_name": security_name,
                "assignee_account_id": mapped["assignee_account_id"],
                "atlassian_instance": atlassian_instance,
            },
        )
    except Exception as e:
        print(json.dumps({"stage": "creator_error", "success": False, "error": str(e)}))
        return 1

    print(json.dumps({
        "stage": "created" if created.get("success") else "creation_failed",
        "success": created.get("success", False),
        "issue_key": created.get("issue_key", ""),
        "issue_url": created.get("issue_url", ""),
        "error": created.get("error", ""),
    }))
    return 0 if created.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
