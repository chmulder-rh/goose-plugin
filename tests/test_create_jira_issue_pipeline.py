"""Tests for skills/jira-issue-creator/scripts/create_jira_issue_pipeline.py"""

import json
import subprocess
import sys
from unittest.mock import patch, MagicMock

import pytest

from conftest import SCRIPTS_DIR


ALL_ENV_VARS = {
    "ATLASSIAN_AUTH": "dummy-token",
    "ATLASSIAN_CLOUD_ID": "dummy-cloud-id",
    "ATLASSIAN_INSTANCE": "example.atlassian.net",
}


def fake_completed_process(stdout: str, returncode: int = 0, stderr: str = ""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


class TestCheckRequiredEnvVars:
    def test_all_set_returns_empty_list(self, pipeline_module, monkeypatch):
        for k, v in ALL_ENV_VARS.items():
            monkeypatch.setenv(k, v)
        assert pipeline_module.check_required_env_vars() == []

    def test_none_set_returns_all_three(self, pipeline_module, clean_atlassian_env):
        missing = pipeline_module.check_required_env_vars()
        assert set(missing) == set(pipeline_module.REQUIRED_ENV_VARS)

    def test_partially_set_returns_only_missing(self, pipeline_module, clean_atlassian_env):
        clean_atlassian_env.setenv("ATLASSIAN_AUTH", "token")
        clean_atlassian_env.setenv("ATLASSIAN_CLOUD_ID", "cloud-id")
        missing = pipeline_module.check_required_env_vars()
        assert missing == ["ATLASSIAN_INSTANCE"]

    def test_blank_value_counts_as_missing(self, pipeline_module, clean_atlassian_env):
        clean_atlassian_env.setenv("ATLASSIAN_AUTH", "   ")
        clean_atlassian_env.setenv("ATLASSIAN_CLOUD_ID", "cloud-id")
        clean_atlassian_env.setenv("ATLASSIAN_INSTANCE", "example.atlassian.net")
        missing = pipeline_module.check_required_env_vars()
        assert missing == ["ATLASSIAN_AUTH"]


class TestRunRecipe:
    def test_parses_last_json_line_on_success(self, pipeline_module):
        stdout = "some log noise\nmore noise\n" + json.dumps({"valid": True, "mapped_summary": "x"})
        with patch("subprocess.run", return_value=fake_completed_process(stdout)):
            result = pipeline_module.run_recipe(SCRIPTS_DIR / "fake.yaml", {"a": "b"})
        assert result == {"valid": True, "mapped_summary": "x"}

    def test_raises_on_nonzero_exit(self, pipeline_module):
        with patch(
            "subprocess.run",
            return_value=fake_completed_process("", returncode=1, stderr="boom"),
        ):
            with pytest.raises(RuntimeError, match="goose run failed"):
                pipeline_module.run_recipe(SCRIPTS_DIR / "fake.yaml", {})

    def test_raises_on_empty_stdout(self, pipeline_module):
        with patch("subprocess.run", return_value=fake_completed_process("   \n  ")):
            with pytest.raises(RuntimeError, match="No output"):
                pipeline_module.run_recipe(SCRIPTS_DIR / "fake.yaml", {})

    def test_raises_on_unparsable_last_line(self, pipeline_module):
        with patch("subprocess.run", return_value=fake_completed_process("not json at all")):
            with pytest.raises(RuntimeError, match="Could not parse structured JSON"):
                pipeline_module.run_recipe(SCRIPTS_DIR / "fake.yaml", {})

    def test_builds_expected_command(self, pipeline_module):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env")
            return fake_completed_process(json.dumps({"ok": True}))

        with patch("subprocess.run", side_effect=fake_run):
            pipeline_module.run_recipe(
                pipeline_module.MAPPER_RECIPE, {"summary": "hello world", "team": "Console - UI"}
            )

        cmd = captured["cmd"]
        assert cmd[0:4] == ["goose", "run", "--recipe", str(pipeline_module.MAPPER_RECIPE)]
        assert "-q" in cmd
        assert "--params" in cmd
        # Parameters are now JSON-encoded to handle special characters
        assert 'summary="hello world"' in cmd
        assert 'team="Console - UI"' in cmd
        assert captured["env"]["GOOSE_MODE"] == "auto"


class TestMainEnvGuard:
    """main() should fail fast on missing env vars before touching subprocess at all."""

    def _argv(self):
        return [
            "create_jira_issue_pipeline.py",
            "--summary", "Fix bug",
            "--team", "Console - UI",
            "--issue-type", "Bug",
            "--activity-type", "Quality / Stability / Reliability",
            "--assignee-account-id", "unassigned",
        ]

    def test_missing_env_vars_short_circuits(self, pipeline_module, clean_atlassian_env, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", self._argv())
        with patch("subprocess.run") as mock_run:
            rc = pipeline_module.main()

        mock_run.assert_not_called()
        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["stage"] == "env_error"
        assert payload["success"] is False
        assert "ATLASSIAN_AUTH" in payload["error"]
        assert "ATLASSIAN_CLOUD_ID" in payload["error"]
        assert "ATLASSIAN_INSTANCE" in payload["error"]


class TestMainPipelineFlow:
    def _argv(self):
        return [
            "create_jira_issue_pipeline.py",
            "--summary", "Fix bug",
            "--team", "Console - UI",
            "--issue-type", "Bug",
            "--activity-type", "Quality / Stability / Reliability",
            "--assignee-account-id", "unassigned",
        ]

    def test_happy_path_reports_created(self, pipeline_module, monkeypatch, capsys):
        for k, v in ALL_ENV_VARS.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setattr(sys, "argv", self._argv())

        mapped_response = {
            "valid": True,
            "mapped_summary": "Fix bug",
            "issue_type": "Bug",
            "team_field_value": "uuid-123",
            "activity_type_field_value": {"value": "Quality / Stability / Reliability"},
            "security_field_value": None,
            "assignee_account_id": "unassigned",
        }
        created_response = {
            "success": True,
            "issue_key": "RHCLOUD-1",
            "issue_url": "https://example.atlassian.net/browse/RHCLOUD-1",
            "error": "",
        }

        call_count = {"n": 0}

        def fake_run(cmd, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return fake_completed_process(json.dumps(mapped_response))
            return fake_completed_process(json.dumps(created_response))

        with patch("subprocess.run", side_effect=fake_run):
            rc = pipeline_module.main()

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload == {
            "stage": "created",
            "success": True,
            "issue_key": "RHCLOUD-1",
            "issue_url": "https://example.atlassian.net/browse/RHCLOUD-1",
            "error": "",
        }

    def test_validation_failed_short_circuits_before_stage_b(self, pipeline_module, monkeypatch, capsys):
        for k, v in ALL_ENV_VARS.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setattr(sys, "argv", self._argv())

        mapped_response = {"valid": False, "errors": ["team is not a valid option"]}

        with patch("subprocess.run", return_value=fake_completed_process(json.dumps(mapped_response))) as mock_run:
            rc = pipeline_module.main()

        assert mock_run.call_count == 1  # never reached stage B
        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["stage"] == "validation_failed"
        assert payload["errors"] == ["team is not a valid option"]

    def test_mapper_error_reported(self, pipeline_module, monkeypatch, capsys):
        for k, v in ALL_ENV_VARS.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setattr(sys, "argv", self._argv())

        with patch("subprocess.run", return_value=fake_completed_process("", returncode=2, stderr="crashed")):
            rc = pipeline_module.main()

        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["stage"] == "mapper_error"
        assert payload["success"] is False

    def test_creator_error_reported(self, pipeline_module, monkeypatch, capsys):
        for k, v in ALL_ENV_VARS.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setattr(sys, "argv", self._argv())

        mapped_response = {
            "valid": True,
            "mapped_summary": "Fix bug",
            "issue_type": "Bug",
            "team_field_value": "uuid-123",
            "activity_type_field_value": {"value": "Quality / Stability / Reliability"},
            "security_field_value": None,
            "assignee_account_id": "unassigned",
        }

        call_count = {"n": 0}

        def fake_run(cmd, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return fake_completed_process(json.dumps(mapped_response))
            return fake_completed_process("", returncode=1, stderr="creator crashed")

        with patch("subprocess.run", side_effect=fake_run):
            rc = pipeline_module.main()

        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["stage"] == "creator_error"

    def test_creation_failed_when_creator_reports_failure(self, pipeline_module, monkeypatch, capsys):
        for k, v in ALL_ENV_VARS.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setattr(sys, "argv", self._argv())

        mapped_response = {
            "valid": True,
            "mapped_summary": "Fix bug",
            "issue_type": "Bug",
            "team_field_value": "uuid-123",
            "activity_type_field_value": {"value": "Quality / Stability / Reliability"},
            "security_field_value": None,
            "assignee_account_id": "unassigned",
        }
        created_response = {
            "success": False,
            "issue_key": "",
            "issue_url": "",
            "error": "Jira API rejected the request",
        }

        call_count = {"n": 0}

        def fake_run(cmd, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return fake_completed_process(json.dumps(mapped_response))
            return fake_completed_process(json.dumps(created_response))

        with patch("subprocess.run", side_effect=fake_run):
            rc = pipeline_module.main()

        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["stage"] == "creation_failed"
        assert payload["error"] == "Jira API rejected the request"

    def test_atlassian_instance_passed_to_creator_recipe(self, pipeline_module, monkeypatch):
        for k, v in ALL_ENV_VARS.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setattr(sys, "argv", self._argv())

        mapped_response = {
            "valid": True,
            "mapped_summary": "Fix bug",
            "issue_type": "Bug",
            "team_field_value": "uuid-123",
            "activity_type_field_value": {"value": "Quality / Stability / Reliability"},
            "security_field_value": None,
            "assignee_account_id": "unassigned",
        }
        created_response = {"success": True, "issue_key": "RHCLOUD-1", "issue_url": "u", "error": ""}

        captured_cmds = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(cmd)
            if len(captured_cmds) == 1:
                return fake_completed_process(json.dumps(mapped_response))
            return fake_completed_process(json.dumps(created_response))

        with patch("subprocess.run", side_effect=fake_run):
            pipeline_module.main()

        creator_cmd = captured_cmds[1]
        assert f"atlassian_instance={ALL_ENV_VARS['ATLASSIAN_INSTANCE']}" in creator_cmd


class TestCliSmoke:
    """A light end-to-end smoke test invoking the script as a real subprocess."""

    SCRIPT = str(SCRIPTS_DIR / "create_jira_issue_pipeline.py")

    def test_missing_env_vars_via_real_subprocess(self):
        import os

        env = {k: v for k, v in os.environ.items() if not k.startswith("ATLASSIAN_")}
        result = subprocess.run(
            [
                sys.executable, self.SCRIPT,
                "--summary", "test",
                "--team", "Console - UI",
                "--issue-type", "Bug",
                "--activity-type", "Quality / Stability / Reliability",
                "--assignee-account-id", "unassigned",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 1
        payload = json.loads(result.stdout)
        assert payload["stage"] == "env_error"
