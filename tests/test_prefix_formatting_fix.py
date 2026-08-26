"""Tests for prefix formatting bug fix: [[test]] should become [test]"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from conftest import SCRIPTS_DIR


def fake_completed_process(stdout: str, returncode: int = 0, stderr: str = ""):
    """Create a mock subprocess.CompletedProcess."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


class TestPrefixFormatting:
    """Test that prefix formatting is handled correctly without double brackets."""

    def test_prefix_without_brackets_gets_brackets_added(self):
        """
        When SKILL returns prefix="goose-plugin" (no brackets),
        validate_and_map_fields should add brackets: [goose-plugin]
        """
        # Simulate running validate_and_map_fields.py
        script = SCRIPTS_DIR / "validate_and_map_fields.py"
        
        result = __import__('subprocess').run(
            [
                'python3', str(script),
                '--summary', 'Fix bug',
                '--prefix', 'goose-plugin',  # No brackets
                '--team', 'Console - UI',
                '--issue-type', 'Bug',
                '--activity-type', 'Quality / Stability / Reliability',
                '--assignee-account-id', 'unassigned'
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        
        output = json.loads(result.stdout)
        assert output['valid'] is True
        assert output['mapped_summary'] == '[goose-plugin] Fix bug'

    def test_prefix_with_brackets_doesnt_double_bracket(self):
        """
        Backward compatibility: if user accidentally passes prefix="[goose-plugin]",
        it should still result in [goose-plugin], not [[goose-plugin]]
        """
        script = SCRIPTS_DIR / "validate_and_map_fields.py"
        
        result = __import__('subprocess').run(
            [
                'python3', str(script),
                '--summary', 'Fix bug',
                '--prefix', '[goose-plugin]',  # With brackets (old format)
                '--team', 'Console - UI',
                '--issue-type', 'Bug',
                '--activity-type', 'Quality / Stability / Reliability',
                '--assignee-account-id', 'unassigned'
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        
        output = json.loads(result.stdout)
        assert output['valid'] is True
        # Should NOT double-bracket
        assert output['mapped_summary'] == '[goose-plugin] Fix bug'
        assert output['mapped_summary'] != '[[goose-plugin]] Fix bug'

    def test_empty_prefix_no_brackets_added(self):
        """Empty prefix should result in no brackets or prefix at all."""
        script = SCRIPTS_DIR / "validate_and_map_fields.py"
        
        result = __import__('subprocess').run(
            [
                'python3', str(script),
                '--summary', 'Fix bug',
                '--prefix', '',  # Empty
                '--team', 'Console - UI',
                '--issue-type', 'Bug',
                '--activity-type', 'Quality / Stability / Reliability',
                '--assignee-account-id', 'unassigned'
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output['valid'] is True
        assert output['mapped_summary'] == 'Fix bug'

    def test_custom_prefix_formatting(self):
        """Custom prefixes should be formatted correctly."""
        script = SCRIPTS_DIR / "validate_and_map_fields.py"
        
        test_cases = [
            ('my-feature', '[my-feature] Fix bug'),
            ('ticket-123', '[ticket-123] Fix bug'),
            ('[already-bracketed]', '[already-bracketed] Fix bug'),  # Backward compat
            ('test[]extra[]brackets', '[test[]extra[]brackets] Fix bug'),  # Edge case
        ]
        
        for prefix_input, expected_summary in test_cases:
            result = __import__('subprocess').run(
                [
                    'python3', str(script),
                    '--summary', 'Fix bug',
                    '--prefix', prefix_input,
                    '--team', 'Console - UI',
                    '--issue-type', 'Bug',
                    '--activity-type', 'Quality / Stability / Reliability',
                    '--assignee-account-id', 'unassigned'
                ],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            assert result.returncode == 0, f"Failed for prefix={prefix_input}: {result.stderr}"
            output = json.loads(result.stdout)
            assert output['valid'] is True
            assert output['mapped_summary'] == expected_summary, \
                f"For prefix '{prefix_input}', expected '{expected_summary}' but got '{output['mapped_summary']}'"

    def test_whitespace_handling_in_prefix(self):
        """Whitespace in prefix should be stripped but prefix added."""
        script = SCRIPTS_DIR / "validate_and_map_fields.py"
        
        result = __import__('subprocess').run(
            [
                'python3', str(script),
                '--summary', 'Fix bug',
                '--prefix', '  goose-plugin  ',  # With whitespace
                '--team', 'Console - UI',
                '--issue-type', 'Bug',
                '--activity-type', 'Quality / Stability / Reliability',
                '--assignee-account-id', 'unassigned'
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output['valid'] is True
        assert output['mapped_summary'] == '[goose-plugin] Fix bug'  # Whitespace stripped
