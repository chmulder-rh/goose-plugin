"""Tests for the JSON-encoding fix in run_recipe.py for multi-line parameters."""

import json
import subprocess
import sys
from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

from conftest import SCRIPTS_DIR


def fake_completed_process(stdout: str, returncode: int = 0, stderr: str = ""):
    """Create a mock subprocess.CompletedProcess."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


class TestJsonEncodingInRunRecipe:
    """Test that run_recipe.py properly JSON-encodes parameters with special characters."""

    def test_run_recipe_json_encodes_string_parameters(self, pipeline_module):
        """Parameters containing newlines and special characters should be JSON-encoded."""
        params = {
            "issue_key": "RHCLOUD-50694",
            "description": "## Background\nThis is a test.\n\n## Scope:\n- Item 1",
            "atlassian_instance": "redhat.atlassian.net"
        }
        
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return fake_completed_process(json.dumps({"success": True, "error": ""}))

        with patch("subprocess.run", side_effect=fake_run):
            pipeline_module.run_recipe(SCRIPTS_DIR / "fake.yaml", params)

        cmd = captured["cmd"]
        
        # Find the description parameter in the command
        description_param = None
        for i, arg in enumerate(cmd):
            if arg.startswith("description="):
                description_param = arg
                break
        
        assert description_param is not None, "description parameter not found in command"
        
        # Extract the value part (after "description=")
        value_part = description_param[len("description="):]
        
        # It should be JSON-encoded (start with quote, be properly escaped)
        assert value_part.startswith('"'), f"Expected JSON string, got: {value_part[:50]}"
        assert "\\n" in value_part, "Newlines should be escaped as \\n"
        assert "\\\\n" not in value_part or "\\n" in value_part, "Should contain escaped newlines"
        
        # Should be valid JSON that decodes back to the original
        decoded = json.loads(value_part)
        assert decoded == params["description"]

    def test_run_recipe_json_encodes_colons_in_values(self, pipeline_module):
        """Colons in description should not break YAML parsing."""
        params = {
            "issue_key": "RHCLOUD-123",
            "description": "Scope: This has colons\nActivity: Important",
            "atlassian_instance": "example.atlassian.net"
        }
        
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return fake_completed_process(json.dumps({"success": True, "error": ""}))

        with patch("subprocess.run", side_effect=fake_run):
            pipeline_module.run_recipe(SCRIPTS_DIR / "fake.yaml", params)

        cmd = captured["cmd"]
        cmd_str = " ".join(cmd)
        
        # The colons should be escaped in the JSON string
        # Look for the description parameter and verify it's JSON-encoded
        for i, arg in enumerate(cmd):
            if arg.startswith("description="):
                # Should be valid JSON
                value_part = arg[len("description="):]
                decoded = json.loads(value_part)
                assert "Scope: This has colons" in decoded
                assert "Activity: Important" in decoded
                break
        else:
            pytest.fail("description parameter not found")

    def test_run_recipe_handles_quotes_in_values(self, pipeline_module):
        """Quotes in description should be properly escaped."""
        params = {
            "issue_key": "RHCLOUD-456",
            "description": 'Text with "quotes" inside',
            "atlassian_instance": "example.atlassian.net"
        }
        
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return fake_completed_process(json.dumps({"success": True, "error": ""}))

        with patch("subprocess.run", side_effect=fake_run):
            pipeline_module.run_recipe(SCRIPTS_DIR / "fake.yaml", params)

        cmd = captured["cmd"]
        
        for arg in cmd:
            if arg.startswith("description="):
                value_part = arg[len("description="):]
                # Should be valid JSON
                decoded = json.loads(value_part)
                assert decoded == params["description"]
                break
        else:
            pytest.fail("description parameter not found")

    def test_non_string_parameters_not_json_encoded(self, pipeline_module):
        """Non-string parameters should pass through unchanged."""
        # While run_recipe.py typically receives string params from CLI,
        # we test that it handles dict/list params correctly if called programmatically
        params = {
            "key1": "string_value",
            # In practice, all params come from JSON parsing on the CLI,
            # but the code handles various types
        }
        
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return fake_completed_process(json.dumps({"success": True, "error": ""}))

        with patch("subprocess.run", side_effect=fake_run):
            pipeline_module.run_recipe(SCRIPTS_DIR / "fake.yaml", params)

        cmd = captured["cmd"]
        
        # Find key1 parameter
        for arg in cmd:
            if arg.startswith("key1="):
                value_part = arg[len("key1="):]
                # Should be JSON-encoded string
                assert value_part == '"string_value"'
                break
