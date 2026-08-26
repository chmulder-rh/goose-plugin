#!/usr/bin/env python3
"""
validate_and_map_fields.py — Pure validation and field mapping for RHCLOUD Jira ticket creation.

This script contains ZERO LLM logic. It:
1. Validates that all input fields match allowed values.
2. Maps human-readable inputs to raw Jira API values (UUIDs, field objects).
3. Reports the result as structured JSON.

No tools, no API calls, no LLM reasoning—just deterministic data transformation.

Usage:
    python3 validate_and_map_fields.py \
        --summary "Fix bug in login page" \
        --prefix "" \
        --team "Console - UI" \
        --issue-type "Bug" \
        --activity-type "Quality / Stability / Reliability" \
        --assignee-account-id "unassigned"

Prints a single JSON object to stdout:
    {
      "valid": true,
      "errors": [],
      "mapped_summary": "Fix bug in login page",
      "issue_type": "Bug",
      "team_field_value": "cc1c0d99-0567-45c8-bf77-8e6149d7ed83",
      "activity_type_field_value": {"value": "Quality / Stability / Reliability"},
      "security_field_value": null,
      "assignee_account_id": "unassigned"
    }

or, on validation failure:
    {
      "valid": false,
      "errors": [
        "team must be one of: Console - Framework, Console - UI",
        "summary must not be empty"
      ],
      "mapped_summary": "",
      "issue_type": "",
      "team_field_value": "",
      "activity_type_field_value": {},
      "security_field_value": null,
      "assignee_account_id": ""
    }
"""

import argparse
import json
import sys


# Allowed values (single source of truth for validation)
ALLOWED_TEAMS = {
    "Console - Framework": "ae9633ff-0523-49b5-b99b-16342fc5a327",
    "Console - UI": "cc1c0d99-0567-45c8-bf77-8e6149d7ed83",
}

ALLOWED_ISSUE_TYPES = {
    "Story", "Bug", "Spike", "Epic", "Risk", "Weakness", "Vulnerability"
}

ALLOWED_ACTIVITY_TYPES = {
    "Quality / Stability / Reliability",
    "Security & Compliance",
    "Incidents & Support",
    "Future Sustainability",
    "Associate Wellness & Development",
    "Product / Portfolio Work",
}


def validate_and_map(summary: str, prefix: str, team: str, issue_type: str,
                     activity_type: str, assignee_account_id: str) -> dict:
    """
    Validate all fields and map to Jira API values.
    
    Returns a dict with:
      - valid (bool): True if all fields pass validation
      - errors (list): Array of error messages; empty if valid
      - Mapped field values (empty strings/objects if invalid)
    """
    errors = []
    
    # Validate summary
    if not summary or not summary.strip():
        errors.append("summary must not be empty")
    
    # Validate team
    if team not in ALLOWED_TEAMS:
        errors.append(f"team must be one of: {', '.join(sorted(ALLOWED_TEAMS.keys()))}")
    
    # Validate issue_type
    if issue_type not in ALLOWED_ISSUE_TYPES:
        errors.append(f"issue_type must be one of: {', '.join(sorted(ALLOWED_ISSUE_TYPES))}")
    
    # Validate activity_type
    if activity_type not in ALLOWED_ACTIVITY_TYPES:
        errors.append(f"activity_type must be one of: {', '.join(sorted(ALLOWED_ACTIVITY_TYPES))}")
    
    # Validate assignee_account_id
    if not assignee_account_id or not assignee_account_id.strip():
        errors.append("assignee_account_id must not be empty (use 'unassigned' for no assignee)")
    
    # If any validation failed, return errors and empty mapped fields
    if errors:
        return {
            "valid": False,
            "errors": errors,
            "mapped_summary": "",
            "issue_type": "",
            "team_field_value": "",
            "activity_type_field_value": {},
            "security_field_value": None,
            "assignee_account_id": "",
        }
    
    # All valid—compute mappings
    # mapped_summary: apply prefix if present
    mapped_summary = summary.strip()
    if prefix and prefix.strip():
        # Strip any existing brackets (for idempotency) before adding them
        prefix_clean = prefix.strip().strip("[]")
        if prefix_clean:  # Only add if there's content after stripping brackets
            mapped_summary = f"[{prefix_clean}] {mapped_summary}"
    
    # team_field_value: map to UUID
    team_field_value = ALLOWED_TEAMS[team]
    
    # activity_type_field_value: wrap in object for customfield_10464
    activity_type_field_value = {"value": activity_type}
    
    # security_field_value: set only if activity_type is "Security & Compliance"
    security_field_value = None
    if activity_type == "Security & Compliance":
        security_field_value = {"name": "Red Hat Employee"}
    
    return {
        "valid": True,
        "errors": [],
        "mapped_summary": mapped_summary,
        "issue_type": issue_type,
        "team_field_value": team_field_value,
        "activity_type_field_value": activity_type_field_value,
        "security_field_value": security_field_value,
        "assignee_account_id": assignee_account_id.strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and map RHCLOUD Jira issue fields"
    )
    parser.add_argument("--summary", required=True)
    parser.add_argument("--prefix", default="")
    parser.add_argument("--team", required=True)
    parser.add_argument("--issue-type", required=True, dest="issue_type")
    parser.add_argument("--activity-type", required=True, dest="activity_type")
    parser.add_argument("--assignee-account-id", required=True, dest="assignee_account_id")
    args = parser.parse_args()
    
    result = validate_and_map(
        summary=args.summary,
        prefix=args.prefix,
        team=args.team,
        issue_type=args.issue_type,
        activity_type=args.activity_type,
        assignee_account_id=args.assignee_account_id,
    )
    
    print(json.dumps(result))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
