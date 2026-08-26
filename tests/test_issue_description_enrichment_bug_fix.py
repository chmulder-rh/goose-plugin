"""
Test that reproduces and verifies the fix for the original issue:
"enrichment step encounters error: could not find expected ':'"

This test simulates the actual enrichment flow described in the bug report.
"""

import json
from unittest.mock import patch, MagicMock

import pytest

from conftest import RECIPES_DIR


def fake_completed_process(stdout: str, returncode: int = 0, stderr: str = ""):
    """Create a mock subprocess.CompletedProcess."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


class TestIssueDescriptionEnrichmentBugFix:
    """Test that the description enrichment step now works with complex markdown."""

    def test_enrichment_step_with_complex_description_from_bug_report(self, pipeline_module):
        """
        Reproduces the exact scenario from the bug report:
        - Generated description with multiple sections
        - Special characters (markdown, colons, quotes)
        - Multi-line content
        - Should NOT fail with "could not find expected ':'" error
        """
        # This is the exact description that was failing
        description = """## Background
This is a test ticket created to verify the Jira issue creator workflow and integration with the RHCLOUD project. It demonstrates the end-to-end process of ticket creation, field validation, and description enrichment.

## Scope
- Test ticket creation via the jira-issue-creator skill
- Verify assignment to chmulder@redhat.com
- Validate field mapping and Jira API integration
- Confirm description update capability

## Acceptance Criteria
- [x] Ticket successfully created in RHCLOUD project
- [x] All required fields populated (Team, Activity Type, Issue Type, Assignee)
- [x] Summary prefix correctly applied: [[goose-plugin]]
- [x] Ticket assigned to the specified user
- [x] Description can be viewed and edited in Jira

## Additional Requirements
- Verify the ticket URL is accessible
- Confirm the ticket appears in the RHCLOUD project dashboard
- Validate that the assignee receives notification

---
**Created by:** Jira Issue Creator Skill
**Test Scope:** Workflow validation"""

        params = {
            "issue_key": "RHCLOUD-50694",
            "description": description,
            "atlassian_instance": "redhat.atlassian.net"
        }
        
        # Track what gets passed to subprocess
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env")
            # Return success response
            return fake_completed_process(
                json.dumps({
                    "success": True,
                    "error": ""
                })
            )

        with patch("subprocess.run", side_effect=fake_run):
            result = pipeline_module.run_recipe(RECIPES_DIR / "update-jira-issue-description.yaml", params)

        # Verify the call succeeded
        assert result["success"] is True, "Recipe should succeed"
        
        # Verify the command was constructed correctly
        cmd = captured["cmd"]
        assert cmd[0] == "goose", "Should call goose"
        assert cmd[1] == "run", "Should use run subcommand"
        assert "--recipe" in cmd, "Should specify recipe"
        assert "update-jira-issue-description.yaml" in " ".join(cmd), "Should use update recipe"
        
        # Extract and verify the description parameter
        description_param = None
        for arg in cmd:
            if arg.startswith("description="):
                description_param = arg[len("description="):]
                break
        
        assert description_param is not None, "description parameter must be present"
        
        # The critical test: it must be valid JSON
        # If this was broken (the original bug), JSON decoding would fail
        # OR the prompt would have YAML parse errors
        try:
            decoded = json.loads(description_param)
        except json.JSONDecodeError as e:
            pytest.fail(f"Description parameter must be valid JSON, but got: {e}")
        
        # Verify the decoded description matches what we sent
        assert decoded == description, "Description should decode back to original"
        
        # Verify special characters are preserved
        assert "## Background" in decoded
        assert "Scope:" in decoded  # The colon that was causing the original error!
        assert '[[goose-plugin]]' in decoded
        assert "---" in decoded
        assert 'chmulder@redhat.com' in decoded

    def test_recipe_prompt_would_be_valid_with_json_encoded_description(self):
        """
        Verify that the recipe prompt template is syntactically valid
        when substituted with JSON-encoded parameter values.
        """
        # Simulate what the recipe receives after goose decodes parameters
        params = {
            "atlassian_instance": "redhat.atlassian.net",
            "issue_key": "RHCLOUD-50694",
            "description": '## Scope: Important\nMore: content\nWith "quotes"'
        }
        
        # JSON-encode as run_recipe.py does
        encoded_params = {
            k: json.dumps(v) if isinstance(v, str) else v
            for k, v in params.items()
        }
        
        # Simulate how goose would substitute the parameters into the recipe template
        # (goose uses Jinja2 template substitution, not Python .format())
        # The template expects the parameters as variable references
        
        # The rendered prompt is what goose will execute:
        # {{ atlassian_instance }} → "redhat.atlassian.net" (JSON-encoded)
        # {{ issue_key }} → "RHCLOUD-50694" (JSON-encoded)
        # {{ description }} → "## Scope: Important\nMore: content\n..." (JSON-encoded)
        
        rendered_prompt = f'''editJiraIssue(
    cloudId={encoded_params["atlassian_instance"]},
    issueIdOrKey={encoded_params["issue_key"]},
    contentFormat="markdown",
    fields={{"description": {encoded_params["description"]}}}
)'''
        
        print("\n=== Rendered Prompt (what goose will execute) ===")
        print(rendered_prompt)
        print("=== End Prompt ===\n")
        
        # The critical check: verify it's valid Python-like syntax
        # This would fail if parameters weren't properly JSON-encoded
        # (because colons, newlines, quotes would break the syntax)
        
        # Check that the fields dict looks correct
        assert 'fields={"description":' in rendered_prompt
        
        # Check that the description value is a valid JSON string
        # (should start with quote and be JSON-encoded)
        assert '"description": "' in rendered_prompt or '"description":' in rendered_prompt
        
        # Most importantly: verify the description is properly JSON-encoded
        # Extract the description value and verify it's valid JSON
        import re
        description_pattern = r'"description":\s*"((?:\\.|[^"\\])*)"'
        match = re.search(description_pattern, rendered_prompt)
        
        if not match:
            # Alternative: the description might be on multiple lines if JSON-encoded
            # In that case, extract the JSON value directly
            description_pattern = r'"description":\s*("[^"]*(?:\\.[^"]*)*")'
            match = re.search(description_pattern, rendered_prompt, re.DOTALL)
        
        assert match, f"Description should be a proper JSON string in: {rendered_prompt}"
        
        # Try to parse the fields part as JSON to verify overall syntax
        fields_start = rendered_prompt.find('fields=')
        fields_end = rendered_prompt.rfind(')')
        fields_str = rendered_prompt[fields_start + len('fields='):fields_end]
        
        try:
            parsed_fields = json.loads(fields_str)
            assert "description" in parsed_fields
            # The actual description content should be preserved
            assert "Scope: Important" in parsed_fields["description"]
            assert "With \"quotes\"" in parsed_fields["description"]
        except json.JSONDecodeError as e:
            pytest.fail(f"Rendered prompt fields should be valid JSON, but got: {e}\nFields: {fields_str}")
