"""
Agent Node Tests
Tests each node in isolation using mocked Cerebras responses.
No real API calls needed.
"""

from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


def make_base_state(tmp_path: Path) -> dict:
    """Build a minimal AgentState for testing."""
    return {
        "issue_url": "https://github.com/test/repo/issues/1",
        "issue_number": 1,
        "issue_title": "Fix division by zero in calculator",
        "issue_body": "When dividing by zero, the app crashes with ZeroDivisionError.",
        "repo_owner": "test",
        "repo_name": "repo",
        "repo_path": str(tmp_path),
        "action_plan": [],
        "files_to_edit": [],
        "messages": [],
        "code_changes": [],
        "test_result": None,
        "retry_count": 0,
        "branch_name": "devagent/fix-1-test",
        "pr_url": None,
        "error": None,
        "status": "running",
    }


class TestPlannerNode:
    def test_planner_produces_plan(self, tmp_path):
        """Planner should return action_plan and files_to_edit."""
        # Create a dummy file structure
        (tmp_path / "calculator.py").write_text("def divide(a, b): return a / b")

        mock_response = MagicMock()
        mock_response.content = '''{
            "action_plan": ["Step 1: Read calculator.py", "Step 2: Add zero check"],
            "files_to_investigate": ["calculator.py"],
            "root_cause_hypothesis": "Missing division by zero check."
        }'''
        mock_response.tool_calls = []
        mock_response.input_tokens = 100
        mock_response.output_tokens = 50
        mock_response.latency_ms = 200

        with patch("agent.planner.cerebras") as mock_cerebras:
            mock_cerebras.chat.return_value = mock_response

            from agent.planner import planner_node
            state = make_base_state(tmp_path)
            result = planner_node(state)

        assert len(result["action_plan"]) == 2
        assert "Step 1" in result["action_plan"][0]
        assert len(result["files_to_edit"]) == 1
        assert "running" == result["status"]

    def test_planner_handles_invalid_json(self, tmp_path):
        """Planner should not crash on bad JSON from LLM."""
        mock_response = MagicMock()
        mock_response.content = "I cannot create a plan right now."
        mock_response.tool_calls = []
        mock_response.input_tokens = 50
        mock_response.output_tokens = 10
        mock_response.latency_ms = 100

        with patch("agent.planner.cerebras") as mock_cerebras:
            mock_cerebras.chat.return_value = mock_response

            from agent.planner import planner_node
            state = make_base_state(tmp_path)
            result = planner_node(state)

        # Should have a fallback plan
        assert len(result["action_plan"]) >= 1


class TestTesterNode:
    def test_tester_passes_when_tests_pass(self, tmp_path):
        """Tester node should set test_result.passed = True on success."""
        with patch("agent.tester.run_tests") as mock_run:
            mock_run.return_value = {
                "passed": True,
                "exit_code": 0,
                "output": "1 passed in 0.1s",
                "failed_tests": [],
            }

            from agent.tester import tester_node
            state = make_base_state(tmp_path)
            result = tester_node(state)

        assert result["test_result"]["passed"] is True
        assert result["retry_count"] == 1

    def test_tester_increments_retry_count(self, tmp_path):
        """retry_count should increment on each test run."""
        with patch("agent.tester.run_tests") as mock_run:
            mock_run.return_value = {
                "passed": False,
                "exit_code": 1,
                "output": "FAILED test_foo",
                "failed_tests": ["test_foo"],
            }

            from agent.tester import tester_node
            state = make_base_state(tmp_path)
            state["retry_count"] = 2
            result = tester_node(state)

        assert result["retry_count"] == 3


class TestGraphRouting:
    def test_routes_to_open_pr_on_pass(self):
        """route_after_test should return 'open_pr' when tests pass."""
        from agent.graph import route_after_test
        state = {
            "test_result": {"passed": True},
            "retry_count": 1,
        }
        assert route_after_test(state) == "open_pr"

    def test_routes_to_debug_on_failure(self):
        from agent.graph import route_after_test
        state = {
            "test_result": {"passed": False},
            "retry_count": 1,
        }
        assert route_after_test(state) == "debug"

    def test_routes_to_exceeded_on_max_retries(self):
        from agent.graph import route_after_test
        # Mock settings
        with patch("agent.graph.settings") as mock_settings:
            mock_settings.max_retries = 5
            state = {
                "test_result": {"passed": False},
                "retry_count": 5,
            }
            assert route_after_test(state) == "exceeded_retries"


class TestCoderExtractChanges:
    def test_extracts_str_replace_calls(self):
        import json
        from agent.coder import _extract_code_changes

        history = [
            {
                "role": "assistant",
                "content": "I'll fix the bug.",
                "tool_calls": [
                    {
                        "function": {
                            "name": "str_replace",
                            "arguments": json.dumps({
                                "path": "/repo/calculator.py",
                                "old_str": "return a / b",
                                "new_str": "if b == 0: raise ValueError('div by zero')\n    return a / b"
                            })
                        }
                    }
                ]
            }
        ]

        changes = _extract_code_changes(history)
        assert len(changes) == 1
        assert changes[0]["file"] == "/repo/calculator.py"
        assert "edit" in changes[0]["description"].lower()
