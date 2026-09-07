#!/usr/bin/env python3
"""Run the deterministic Jira field-mapping and issue-creation pipeline."""

from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from run_recipe import pipeline_main


if __name__ == "__main__":
    sys.exit(pipeline_main())
