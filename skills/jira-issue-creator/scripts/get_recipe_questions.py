#!/usr/bin/env python3
"""
get_recipe_questions.py — deterministic extractor for a recipe's user-facing
parameters (question text + select options), for use by orchestrating skills.

This exists so that "questions and options to ask the user" have exactly ONE
source of truth: the `parameters:` block of the recipe file itself (currently
recipes/jira-issue-mapper.yaml). Skills should call this script rather than
hardcoding option lists in SKILL.md or trusting an LLM to eyeball-parse YAML,
so the two can never drift out of sync.

Usage:
    python3 get_recipe_questions.py <path-to-recipe.yaml>

Prints a JSON array to stdout, one object per parameter, in the order declared
in the recipe, e.g.:

[
  {
    "key": "team",
    "input_type": "select",
    "requirement": "required",
    "description": "Which team owns this ticket?",
    "options": ["Console - Framework", "Console - UI"],
    "default": null
  },
  {
    "key": "prefix",
    "input_type": "string",
    "requirement": "optional",
    "description": "Summary prefix e.g. 'scalprum' -> [scalprum] Fix bug. Empty string for none.",
    "options": null,
    "default": ""
  }
]
"""

import json
import sys

try:
    import yaml
except ImportError:
    print(json.dumps({"error": "PyYAML is required (pip install pyyaml)"}))
    sys.exit(1)


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: get_recipe_questions.py <path-to-recipe.yaml>"}))
        return 1

    recipe_path = sys.argv[1]
    try:
        with open(recipe_path, "r") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        print(json.dumps({"error": f"Could not read/parse {recipe_path}: {e}"}))
        return 1

    params = data.get("parameters") or []
    out = []
    for p in params:
        out.append({
            "key": p.get("key"),
            "input_type": p.get("input_type"),
            "requirement": p.get("requirement"),
            "description": p.get("description", ""),
            "options": p.get("options"),
            "default": p.get("default"),
        })

    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
