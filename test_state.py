"""Tests for AgentState TypedDict."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agent.state import AgentState

def test_state_can_be_created():
    s: AgentState = {
        "issue_url":    "https://github.com/owner/repo/issues/1",
        "issue_number": 1,
        "issue_title":  "Test issue",
        "issue_body":   "Body",
        "repo_owner":   "owner",
        "repo_name":    "repo",
        "repo_path":    "/tmp/repo",
        "branch_name":  "devagent/fix-1",
        "action_plan":  ["step 1"],
        "files_to_edit":["foo.py"],
        "repo_map":     "repo/",
        "messages":     [],
        "code_changes": [],
        "test_command": "pytest",
        "test_output":  "",
        "test_passed":  False,
        "retry_count":  0,
        "max_retries":  5,
        "pr_url":       None,
        "pr_number":    None,
        "error":        None,
        "total_tokens": 0,
    }
    assert s["issue_number"] == 1
    assert s["test_passed"] is False
    assert s["pr_url"] is None
