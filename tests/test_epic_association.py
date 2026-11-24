"""Tests for the epic-association recipes: param encoding, prompt rendering,
recipe structure. All subprocess calls mocked; no network."""

import json
import re
from unittest.mock import patch, MagicMock

import yaml

from conftest import RECIPES_DIR

CLOUD_ID = "2b9e35e3-6bd3-4cec-b838-f4249ee02432"

GETTER = RECIPES_DIR / "get-jira-issue.yaml"
CREATOR = RECIPES_DIR / "create-jira-issue.yaml"
ASSOCIATOR = RECIPES_DIR / "associate-jira-issue-with-epic.yaml"


def fake_completed_process(stdout, returncode=0, stderr=""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


def params_from_cmd(cmd):
    """Return the --params key=value arguments as a decoded dict."""
    return {
        arg.split("=", 1)[0]: json.loads(arg.split("=", 1)[1])
        for arg in cmd
        if "=" in arg and not arg.startswith("-") and not arg.endswith(".yaml")
    }


def render_prompt(recipe_path, values):
    """Substitute {{ param }} placeholders the way goose does (values are
    JSON-encoded by run_recipe.py), dropping {% if %} blocks for empty values."""
    prompt = yaml.safe_load(recipe_path.read_text())["prompt"]

    def keep_or_drop(match):
        return match.group(2) if values.get(match.group(1).strip()) else ""

    prompt = re.sub(
        r"\{%\s*if\s+(\w+)\s*%\}(.*?)\{%\s*endif\s*%\}", keep_or_drop, prompt, flags=re.S
    )
    for key, value in values.items():
        prompt = prompt.replace("{{ " + key + " }}", json.dumps(value))
    return prompt


def additional_fields(rendered):
    start = rendered.find("additional_fields=") + len("additional_fields=")
    return json.loads(rendered[start:rendered.rfind(")")])


class TestParamMarshalling:
    def test_getter_receives_issue_key_json_encoded(self, pipeline_module):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return fake_completed_process(json.dumps(
                {"success": True, "summary": "An epic", "issue_type": "Epic", "error": ""}))

        with patch("subprocess.run", side_effect=fake_run):
            result = pipeline_module.run_recipe(
                GETTER, {"issue_key": "RHCLOUD-100", "atlassian_cloud_id": CLOUD_ID})

        assert result["success"] is True
        assert params_from_cmd(captured["cmd"])["issue_key"] == "RHCLOUD-100"

    def test_associator_receives_both_keys_json_encoded(self, pipeline_module):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return fake_completed_process(json.dumps({"success": True, "error": ""}))

        with patch("subprocess.run", side_effect=fake_run):
            pipeline_module.run_recipe(
                ASSOCIATOR,
                {"issue_key": "RHCLOUD-53737", "epic_key": "RHCLOUD-53736",
                 "atlassian_cloud_id": CLOUD_ID})

        values = params_from_cmd(captured["cmd"])
        assert values["issue_key"] == "RHCLOUD-53737"
        assert values["epic_key"] == "RHCLOUD-53736"


class TestPromptRendering:
    def test_creator_prompt_sets_parent_when_epic_key_present(self):
        rendered = render_prompt(CREATOR, {
            "atlassian_cloud_id": CLOUD_ID, "mapped_summary": "A story",
            "issue_type": "Story", "team_field_value": "ae9633ff-0523-49b5-b99b-16342fc5a327",
            "activity_type_field_value": {"value": "Future Sustainability"},
            "security_field_value": "", "assignee_account_id": "unassigned",
            "epic_key": "RHCLOUD-53736"})

        fields = additional_fields(rendered)
        assert fields["parent"] == {"key": "RHCLOUD-53736"}
        assert "security" not in fields

    def test_creator_prompt_omits_parent_without_epic_key(self):
        rendered = render_prompt(CREATOR, {
            "atlassian_cloud_id": CLOUD_ID, "mapped_summary": "A story",
            "issue_type": "Story", "team_field_value": "ae9633ff-0523-49b5-b99b-16342fc5a327",
            "activity_type_field_value": {"value": "Future Sustainability"},
            "security_field_value": "", "assignee_account_id": "unassigned",
            "epic_key": ""})

        fields = additional_fields(rendered)
        assert "parent" not in fields
        assert "customfield_10001" in fields

    def test_associator_prompt_renders_valid_parent_payload(self):
        rendered = render_prompt(
            ASSOCIATOR,
            {"atlassian_cloud_id": CLOUD_ID, "issue_key": "RHCLOUD-53737",
             "epic_key": "RHCLOUD-53736"})

        fields_str = rendered[rendered.find("fields=") + len("fields="):rendered.rfind(")")]
        assert json.loads(fields_str) == {"parent": {"key": "RHCLOUD-53736"}}

    def test_getter_prompt_requests_summary_and_issuetype(self):
        rendered = render_prompt(
            GETTER, {"atlassian_cloud_id": CLOUD_ID, "issue_key": "RHCLOUD-53736"})

        assert 'issueIdOrKey="RHCLOUD-53736"' in rendered
        assert 'fields=["summary", "issuetype", "parent"]' in rendered


class TestRecipeStructure:
    """Drift guards: the new recipes must keep their declared contracts."""

    def test_getter_declares_expected_params(self):
        data = yaml.safe_load(GETTER.read_text())
        assert [p["key"] for p in data["parameters"]] == ["issue_key", "atlassian_cloud_id"]
        assert data["response"]["json_schema"]["required"] == [
            "success", "summary", "issue_type", "parent_key", "error"]

    def test_associator_declares_expected_params(self):
        data = yaml.safe_load(ASSOCIATOR.read_text())
        assert [p["key"] for p in data["parameters"]] == [
            "issue_key", "epic_key", "atlassian_cloud_id"]
        assert data["response"]["json_schema"]["required"] == ["success", "error"]
