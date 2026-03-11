"""
test_planner.py — Tests for Planner node (mocks Cerebras API).
"""
import sys
import os
import pathlib
import json
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
os.environ.setdefault("CEREBRAS_API_KEY", "test_key")
os.environ.setdefault("GITHUB_TOKEN", "test_token")


MOCK_PLAN = {
    "analysis": "The function calculate_total() doesn't handle None values, causing AttributeError.",
    "action_plan": [
        "Step 1: Read src/calculator.py to understand the current implementation",
        "Step 2: Add None check at the start of calculate_total()",
        "Step 3: Run pytest to verify the fix",
    ],
    "files_likely_involved": ["src/calculator.py"],
    "test_command": "pytest tests/ -v",
    "complexity": "low",
}


class TestPlannerNode:
    @patch("agent.planner.get_llm")
    @patch("agent.planner.list_directory")
    def test_planner_returns_plan(self, mock_list_dir, mock_get_llm, tmp_path):
        # Setup mocks
        mock_list_dir.invoke = MagicMock(return_value="src/\ntests/\nREADME.md")
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content=json.dumps(MOCK_PLAN))
        mock_get_llm.return_value = mock_llm

        from agent.planner import planner_node

        state = {
            "issue_number": 42,
            "issue_title": "calculate_total crashes on None input",
            "issue_body": "When passing None to calculate_total(), it raises AttributeError.",
            "repo_path": str(tmp_path),
            "action_plan": [],
            "files_to_edit": [],
        }

        result = planner_node(state)

        assert "action_plan" in result
        assert len(result["action_plan"]) == 3
        assert "files_to_edit" in result
        assert "src/calculator.py" in result["files_to_edit"]

    @patch("agent.planner.get_llm")
    @patch("agent.planner.list_directory")
    def test_planner_handles_malformed_json(self, mock_list_dir, mock_get_llm, tmp_path):
        mock_list_dir.invoke = MagicMock(return_value="src/")
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="This is not JSON at all")
        mock_get_llm.return_value = mock_llm

        from agent.planner import planner_node

        state = {
            "issue_number": 1,
            "issue_title": "Test issue",
            "issue_body": "Test body",
            "repo_path": str(tmp_path),
            "action_plan": [],
            "files_to_edit": [],
        }

        # Should not raise — falls back to default plan
        result = planner_node(state)
        assert "action_plan" in result
        assert len(result["action_plan"]) > 0
