"""Tests for the optional --epic-key validation in validate_and_map_fields.py."""

import json
import subprocess

from conftest import SCRIPTS_DIR

VALIDATOR = SCRIPTS_DIR / "validate_and_map_fields.py"

BASE_ARGS = [
    "--summary", "Fix bug",
    "--team", "Console - UI",
    "--issue-type", "Bug",
    "--activity-type", "Quality / Stability / Reliability",
    "--assignee-account-id", "unassigned",
]


def run_validator(*extra):
    return subprocess.run(
        ["python3", str(VALIDATOR), *BASE_ARGS, *extra],
        capture_output=True, text=True, timeout=10,
    )


class TestEpicKeyValidation:
    def test_valid_epic_key_passes_through(self):
        result = run_validator("--epic-key", "RHCLOUD-100")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["valid"] is True
        assert payload["epic_key"] == "RHCLOUD-100"

    def test_missing_epic_key_defaults_to_empty(self):
        result = run_validator()
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["valid"] is True
        assert payload["epic_key"] == ""

    def test_invalid_epic_key_blocks_validation(self):
        result = run_validator("--epic-key", "CONSOLE-123")
        assert result.returncode == 1
        payload = json.loads(result.stdout)
        assert payload["valid"] is False
        assert any("epic_key" in e for e in payload["errors"])
        assert payload["epic_key"] == ""

    def test_lowercase_project_prefix_rejected(self):
        result = run_validator("--epic-key", "rhcloud-100")
        assert result.returncode == 1
        payload = json.loads(result.stdout)
        assert payload["valid"] is False
