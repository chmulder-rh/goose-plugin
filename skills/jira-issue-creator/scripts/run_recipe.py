#!/usr/bin/env python3
"""
run_recipe.py — Generalized, deterministic recipe runner for the jira-issue-creator skill.

This script contains ZERO creative/LLM logic. It:
1. Validates required environment variables.
2. Accepts a recipe path and a JSON-encoded parameters object.
3. Runs `goose run --recipe <recipe> --params key=value ...` in GOOSE_MODE=auto.
4. Parses the final structured JSON output from the recipe's response.json_schema.
5. Returns the result or an error, also as JSON.

The script is agnostic to the recipe's internal logic—it only handles:
- Environment validation
- Parameter marshalling
- Subprocess execution
- JSON output parsing
- Error reporting

Usage:
    python3 run_recipe.py \
        --recipe recipes/jira-issue-mapper.yaml \
        --params '{"summary":"test","prefix":"","team":"Console - UI","issue_type":"Bug","activity_type":"Quality / Stability / Reliability","assignee_account_id":"unassigned"}'

Prints a single JSON object to stdout with at minimum:
    {"success": <bool>, "error": <string>}

Plus any fields the recipe's response.json_schema defines (e.g., issue_key, issue_url,
valid, mapped_summary, errors, etc.).

If environment validation fails:
    {"stage": "env_error", "success": false, "error": "Missing ATLASSIAN_CLOUD_ID, ..."}

If subprocess fails or JSON parsing fails:
    {"stage": "execution_error", "success": false, "error": "..."}

Requires GOOSE_MODE=auto to be effective for the session.

Requires these environment variables to be exported:
    ATLASSIAN_CLOUD_ID  - UUID of Atlassian Cloud tenant
    ATLASSIAN_INSTANCE  - Atlassian site hostname (e.g., "company.atlassian.net"), used when displaying issue URLs

The Rovo MCP extension authenticates interactively with OAuth 2.1. Headless
recipe execution still requires GOOSE_MODE=auto; OAuth authorization may open
a browser when no valid session authorization is cached.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
RECIPES_DIR = SKILL_DIR / "recipes"
MAPPER_RECIPE = RECIPES_DIR / "jira-issue-mapper.yaml"
CREATOR_RECIPE = RECIPES_DIR / "create-jira-issue.yaml"
REQUIRED_ENV_VARS = ["ATLASSIAN_CLOUD_ID", "ATLASSIAN_INSTANCE"]

# Wall-clock budget for one `goose run`. Working runs take 15-60s; anything
# longer is a hang (historically: OAuth credentials unreadable from the OS
# keyring, or goose waiting on a headless browser-auth callback).
SUBPROCESS_TIMEOUT_SECS = 180

# If cached Atlassian OAuth credentials are missing, goose falls back to an
# interactive browser flow that waits on a local callback for 300s by
# default — silent in headless mode. Shorten it so we get a fast, visible
# failure instead. Override by exporting the variable yourself.
GOOSE_OAUTH_CALLBACK_TIMEOUT_SECS = "15"


def check_required_env_vars() -> list:
    """Return a list of required env var names that are missing or empty."""
    return [name for name in REQUIRED_ENV_VARS if not os.environ.get(name, "").strip()]


def run_recipe(recipe_path: Path, params: dict) -> dict:
    """
    Run a goose recipe non-interactively and parse its final JSON output.
    
    Args:
        recipe_path: Path to the .yaml recipe file.
        params: Dictionary of parameters to pass via --params key=value.
    
    Returns:
        Dictionary parsed from the recipe's final JSON output line.
    
    Raises:
        RuntimeError: If subprocess fails, times out, output is empty, or JSON
            parsing fails. Timeout errors include the goose stderr tail so the
            failure mode (e.g. Atlassian OAuth) is diagnosable.
    """
    # Build command: goose run --recipe <path> --params k1=v1 --params k2=v2 ... -q
    cmd = ["goose", "run", "--recipe", str(recipe_path), "-q"]
    for key, value in params.items():
        # Drop null/empty values entirely. Passing them literally (e.g.
        # security_field_value=None) makes the string "None" truthy in the
        # recipe's Jinja conditional, wrongly rendering `"security": None`.
        # Dropping them lets the recipe default ("" — falsy) take over.
        # A required param that is null/empty here makes goose exit with a
        # clear MissingParams error rather than prompting.
        if value is None or value == "":
            continue
        # JSON-encode every value (strings, dicts, lists, bools, numbers):
        # escapes special characters in strings and renders dicts as valid
        # JSON (double quotes) instead of Python repr (single quotes).
        cmd += ["--params", f"{key}={json.dumps(value)}"]

    # GOOSE_MODE=auto is required for nested `goose run` calls to succeed.
    env = {**os.environ, "GOOSE_MODE": "auto"}
    env.setdefault("GOOSE_OAUTH_CALLBACK_TIMEOUT_SECONDS", GOOSE_OAUTH_CALLBACK_TIMEOUT_SECS)

    # Leave an evidence trail: what ran, with which timeout.
    print(f"[run_recipe] {recipe_path.name} timeout={SUBPROCESS_TIMEOUT_SECS}s", file=sys.stderr)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_SECS, env=env
        )
    except subprocess.TimeoutExpired as e:
        # e.stderr holds the goose output captured before the kill — this is
        # the evidence that was previously discarded (e.g. the Atlassian
        # "authorize manually at: https://..." URL or the keyring blocker).
        stderr_tail = (e.stderr or "")[-1500:] if isinstance(e.stderr, str) else ""
        raise RuntimeError(
            f"goose run timed out after {SUBPROCESS_TIMEOUT_SECS}s for {recipe_path.name}. "
            f"Likely cause: Atlassian OAuth credentials unreadable (OS keyring locked, "
            f"e.g. KeePassXC) or a headless browser-auth wait. Fix: unlock the keyring / "
            f"run 'goose session' once interactively to refresh the rovo OAuth grant. "
            f"stderr tail: {stderr_tail.strip() or '(empty)'}"
        )

    if result.returncode != 0:
        raise RuntimeError(
            f"goose run failed (exit {result.returncode}) for {recipe_path.name}: "
            f"{result.stderr.strip()[-2000:]}"
        )

    # Extract non-empty lines and take the last one (structured JSON output).
    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(
            f"No output from {recipe_path.name}. stderr: {result.stderr.strip()[-2000:]}"
        )

    last_line = lines[-1]
    json_start = last_line.find('{')
    if json_start != -1:
        last_line = last_line[json_start:]
    try:
        return json.loads(last_line)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Could not parse structured JSON output from {recipe_path.name}: {e}. "
            f"Last line was: {last_line!r}"
        )


def recipe_main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a goose recipe with JSON parameters and return structured output"
    )
    parser.add_argument(
        "--recipe",
        required=True,
        help="Path to the recipe .yaml file (relative to skill dir or absolute)"
    )
    parser.add_argument(
        "--params",
        required=True,
        help="JSON-encoded dictionary of parameters to pass to the recipe"
    )
    args = parser.parse_args()

    # Validate environment variables.
    missing_env_vars = check_required_env_vars()
    if missing_env_vars:
        print(json.dumps({
            "stage": "env_error",
            "success": False,
            "error": "Missing required environment variable(s): " + ", ".join(missing_env_vars) +
                     ". Export ATLASSIAN_CLOUD_ID and ATLASSIAN_INSTANCE before running. "
                     "The Rovo MCP extension will authenticate through OAuth 2.1.",
        }))
        return 1

    # Resolve recipe path (relative to skill dir or absolute).
    recipe_path = Path(args.recipe).expanduser()
    if not recipe_path.is_absolute():
        recipe_path = SKILL_DIR / recipe_path
    if not recipe_path.exists():
        print(json.dumps({
            "stage": "execution_error",
            "success": False,
            "error": f"Recipe file not found: {recipe_path}",
        }))
        return 1

    # Parse parameters JSON.
    try:
        params = json.loads(args.params)
        if not isinstance(params, dict):
            raise ValueError("Parameters must be a JSON object (dict)")
    except json.JSONDecodeError as e:
        print(json.dumps({
            "stage": "execution_error",
            "success": False,
            "error": f"Invalid JSON in --params: {e}",
        }))
        return 1

    # Auto-inject the cloud ID used by Rovo tool calls. Recipe prompts cannot
    # read shell variables directly; they must receive declared parameters.
    params.setdefault("atlassian_cloud_id", os.environ["ATLASSIAN_CLOUD_ID"])

    # Run the recipe.
    try:
        result = run_recipe(recipe_path, params)
    except Exception as e:
        print(json.dumps({
            "stage": "execution_error",
            "success": False,
            "error": str(e),
        }))
        return 1

    # Return the recipe's structured output as-is.
    print(json.dumps(result))
    return 0 if result.get("success", False) else 1


if __name__ == "__main__":
    sys.exit(recipe_main())
