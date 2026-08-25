"""Tests for skills/jira-issue-creator/scripts/get_recipe_questions.py"""

import json
import subprocess
import sys

from conftest import RECIPES_DIR, SCRIPTS_DIR


class TestExtractQuestions:
    def test_extracts_all_fields_in_order(self, get_recipe_questions_module):
        data = {
            "parameters": [
                {
                    "key": "team",
                    "input_type": "select",
                    "requirement": "required",
                    "description": "Which team owns this ticket?",
                    "options": ["Console - Framework", "Console - UI"],
                },
                {
                    "key": "prefix",
                    "input_type": "string",
                    "requirement": "optional",
                    "description": "Summary prefix",
                    "default": "",
                },
            ]
        }
        result = get_recipe_questions_module.extract_questions(data)
        assert result == [
            {
                "key": "team",
                "input_type": "select",
                "requirement": "required",
                "description": "Which team owns this ticket?",
                "options": ["Console - Framework", "Console - UI"],
                "default": None,
            },
            {
                "key": "prefix",
                "input_type": "string",
                "requirement": "optional",
                "description": "Summary prefix",
                "options": None,
                "default": "",
            },
        ]

    def test_missing_parameters_key_returns_empty_list(self, get_recipe_questions_module):
        assert get_recipe_questions_module.extract_questions({"title": "no params here"}) == []

    def test_empty_parameters_list_returns_empty_list(self, get_recipe_questions_module):
        assert get_recipe_questions_module.extract_questions({"parameters": []}) == []

    def test_none_data_returns_empty_list(self, get_recipe_questions_module):
        assert get_recipe_questions_module.extract_questions(None) == []

    def test_missing_description_defaults_to_empty_string(self, get_recipe_questions_module):
        data = {"parameters": [{"key": "x", "input_type": "string", "requirement": "required"}]}
        result = get_recipe_questions_module.extract_questions(data)
        assert result[0]["description"] == ""

    def test_real_mapper_recipe_has_expected_keys(self, get_recipe_questions_module):
        """Guard against the real recipe file and this script silently drifting apart."""
        import yaml

        with open(RECIPES_DIR / "jira-issue-mapper.yaml") as f:
            data = yaml.safe_load(f)

        result = get_recipe_questions_module.extract_questions(data)
        keys = [q["key"] for q in result]
        assert keys == [
            "summary",
            "prefix",
            "team",
            "issue_type",
            "activity_type",
            "assignee_account_id",
        ]
        team_question = next(q for q in result if q["key"] == "team")
        assert team_question["input_type"] == "select"
        assert "Console - Framework" in team_question["options"]


class TestMainCli:
    """End-to-end tests that actually run the script as a subprocess."""

    SCRIPT = str(SCRIPTS_DIR / "get_recipe_questions.py")

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, self.SCRIPT, *args],
            capture_output=True,
            text=True,
        )

    def test_wrong_arg_count_prints_usage_error(self):
        result = self.run_cli()
        assert result.returncode == 1
        payload = json.loads(result.stdout)
        assert "Usage" in payload["error"]

    def test_nonexistent_file_prints_error(self):
        result = self.run_cli("/nonexistent/path/to/recipe.yaml")
        assert result.returncode == 1
        payload = json.loads(result.stdout)
        assert "error" in payload

    def test_malformed_yaml_prints_error(self, tmp_path):
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("key: [unterminated")
        result = self.run_cli(str(bad_file))
        assert result.returncode == 1
        payload = json.loads(result.stdout)
        assert "error" in payload

    def test_valid_recipe_prints_json_array(self, tmp_path):
        recipe_file = tmp_path / "recipe.yaml"
        recipe_file.write_text(
            "parameters:\n"
            "  - key: foo\n"
            "    input_type: string\n"
            "    requirement: required\n"
            "    description: A foo value\n"
        )
        result = self.run_cli(str(recipe_file))
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload == [
            {
                "key": "foo",
                "input_type": "string",
                "requirement": "required",
                "description": "A foo value",
                "options": None,
                "default": None,
            }
        ]

    def test_real_recipe_file_runs_successfully(self):
        result = self.run_cli(str(RECIPES_DIR / "jira-issue-mapper.yaml"))
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert isinstance(payload, list)
        assert len(payload) == 6
