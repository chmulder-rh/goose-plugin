"""Shared pytest fixtures/helpers for testing the plugin's standalone scripts.

The scripts under skills/jira-issue-creator/scripts/ are plain, dependency-free
Python files (not an installed package) so that they stay directly runnable via
`python3 <script>.py ...` as documented in SKILL.md. We load them here by file
path via importlib rather than installing them, to test the exact files that
ship in the plugin.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "skills" / "jira-issue-creator" / "scripts"
RECIPES_DIR = REPO_ROOT / "skills" / "jira-issue-creator" / "recipes"


def load_module(name: str, path: Path):
    """Import a standalone script file as a module by path, without installing it."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def get_recipe_questions_module():
    return load_module("get_recipe_questions", SCRIPTS_DIR / "get_recipe_questions.py")


@pytest.fixture()
def pipeline_module():
    return load_module("run_recipe", SCRIPTS_DIR / "run_recipe.py")


@pytest.fixture()
def clean_atlassian_env(monkeypatch):
    """Ensure the three Atlassian env vars start unset for a test, regardless of the host env."""
    for name in ("ATLASSIAN_AUTH", "ATLASSIAN_CLOUD_ID", "ATLASSIAN_INSTANCE"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch
