from __future__ import annotations
from typing import TypedDict, Optional

class AgentState(TypedDict):
    # Input
    issue_url:      str
    issue_number:   int
    issue_title:    str
    issue_body:     str
    repo_owner:     str
    repo_name:      str
    repo_path:      str
    branch_name:    str
    # Planning
    action_plan:    list
    files_to_edit:  list
    repo_map:       str
    # Execution
    messages:       list
    code_changes:   list
    # Testing
    test_command:   str
    test_output:    str
    test_passed:    bool
    retry_count:    int
    max_retries:    int
    # Output
    pr_url:         Optional[str]
    pr_number:      Optional[int]
    error:          Optional[str]
    total_tokens:   int
