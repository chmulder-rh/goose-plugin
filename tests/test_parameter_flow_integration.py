"""Integration tests for the parameter flow from validation to recipe execution."""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from conftest import SCRIPTS_DIR, RECIPES_DIR


def fake_completed_process(stdout: str, returncode: int = 0, stderr: str = ""):
    """Create a mock subprocess.CompletedProcess."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


class TestParameterFlowWithMultilineDescription:
    """Test the complete flow: validation -> JSON encoding -> recipe execution."""

    def test_multiline_description_flows_through_pipeline(self, pipeline_module):
        """
        Simulate: validate_and_map_fields.py outputs mapped fields →
                  run_recipe.py JSON-encodes them →
                  goose recipe receives properly formatted parameters →
                  recipe prompt is valid Python/MCP code
        """
        # Step 1: Simulated output from validate_and_map_fields.py
        mapped_fields = {
            "valid": True,
            "errors": [],
            "mapped_summary": "[test] Fix the thing",
            "issue_type": "Bug",
            "team_field_value": "cc1c0d99-0567-45c8-bf77-8e6149d7ed83",  # UUID string
            "activity_type_field_value": {"value": "Quality / Stability / Reliability"},  # dict
            "security_field_value": None,
            "assignee_account_id": "user123"
        }
        
        # Step 2: These go to run_recipe.py which will JSON-encode them
        # Simulate run_recipe.py being called with params from the mapped fields
        create_params = {
            "mapped_summary": mapped_fields["mapped_summary"],
            "issue_type": mapped_fields["issue_type"],
            "team_field_value": mapped_fields["team_field_value"],  # UUID string
            "activity_type_field_value": json.dumps(mapped_fields["activity_type_field_value"]),  # Already JSON
            "security_field_value": json.dumps(mapped_fields["security_field_value"]) if mapped_fields["security_field_value"] else "",
            "assignee_account_id": mapped_fields["assignee_account_id"],
            "atlassian_instance": "redhat.atlassian.net",
        }
        
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env")
            return fake_completed_process(json.dumps({"success": True, "issue_key": "RHCLOUD-1", "issue_url": "...", "error": ""}))

        with patch("subprocess.run", side_effect=fake_run):
            result = pipeline_module.run_recipe(RECIPES_DIR / "create-jira-issue.yaml", create_params)

        assert result["success"] is True
        
        # Verify the command was built correctly
        cmd = captured["cmd"]
        
        # All parameters should be JSON-encoded
        assert any('mapped_summary="[test] Fix the thing"' in arg for arg in cmd), \
            "Summary should be JSON-encoded"
        assert any('issue_type="Bug"' in arg for arg in cmd), \
            "Issue type should be JSON-encoded"
        assert any('team_field_value="cc1c0d99-0567-45c8-bf77-8e6149d7ed83"' in arg for arg in cmd), \
            "Team field value should be JSON-encoded as a string"

    def test_description_with_special_chars_flows_correctly(self, pipeline_module):
        """Test that a multi-line description with special characters is properly encoded."""
        description = """## Background
This is a test ticket.

## Scope
- Security & Compliance items
- Activity: Test
- Some field: value with colon

## Acceptance Criteria
- [x] Item 1 with "quotes"
- [x] Item 2"""
        
        params = {
            "issue_key": "RHCLOUD-50694",
            "description": description,
            "atlassian_instance": "redhat.atlassian.net"
        }
        
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return fake_completed_process(json.dumps({"success": True, "error": ""}))

        with patch("subprocess.run", side_effect=fake_run):
            result = pipeline_module.run_recipe(RECIPES_DIR / "update-jira-issue-description.yaml", params)

        cmd = captured["cmd"]
        
        # Find the description parameter
        description_arg = None
        for arg in cmd:
            if arg.startswith("description="):
                description_arg = arg[len("description="):]
                break
        
        assert description_arg is not None, "description parameter not found in command"
        
        # It should be valid JSON and decode back to the original
        decoded_description = json.loads(description_arg)
        assert decoded_description == description
        
        # Verify special characters are preserved
        assert "## Scope" in decoded_description
        assert "Security & Compliance items" in decoded_description
        assert "Activity: Test" in decoded_description
        assert 'Item 1 with "quotes"' in decoded_description

    def test_update_description_recipe_receives_json_encoded_params(self, pipeline_module):
        """
        Test that update-jira-issue-description recipe receives properly formatted parameters.
        The recipe expects: cloudId, issueIdOrKey, description (all JSON-encoded)
        """
        params = {
            "issue_key": "RHCLOUD-123",
            "description": "## Test\nWith newlines\nAnd special: chars",
            "atlassian_instance": "example.atlassian.net"
        }
        
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            # Verify command structure
            assert "goose" in cmd
            assert "run" in cmd
            assert "--recipe" in cmd
            assert "-q" in cmd
            return fake_completed_process(json.dumps({"success": True, "error": ""}))

        with patch("subprocess.run", side_effect=fake_run):
            pipeline_module.run_recipe(RECIPES_DIR / "update-jira-issue-description.yaml", params)

        cmd = captured["cmd"]
        
        # Verify all expected parameters are present and JSON-encoded
        cmd_str = " ".join(cmd)
        
        # Find and verify each parameter
        found_params = {}
        for arg in cmd:
            if "=" in arg and arg.startswith("--params"):
                continue  # Skip the --params flag itself
            if "=" in arg and not arg.startswith("-"):
                key, value = arg.split("=", 1)
                found_params[key] = value
        
        assert "issue_key" in found_params, "issue_key not found in params"
        assert "description" in found_params, "description not found in params"
        assert "atlassian_instance" in found_params, "atlassian_instance not found in params"
        
        # Verify they're JSON-encoded
        assert json.loads(found_params["issue_key"]) == "RHCLOUD-123"
        assert json.loads(found_params["description"]) == "## Test\nWith newlines\nAnd special: chars"
        assert json.loads(found_params["atlassian_instance"]) == "example.atlassian.net"
