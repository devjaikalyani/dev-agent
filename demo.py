"""
Local Demo Script
Creates a tiny broken Python project, then runs DevAgent on it
WITHOUT needing real GitHub credentials.

This lets you test the agent logic end-to-end locally.

Usage:
    python scripts/demo.py
"""

from __future__ import annotations
import os
import sys
import json
import tempfile
import subprocess
from pathlib import Path


BROKEN_CALCULATOR = '''\
"""A simple calculator with a bug."""


def divide(a: float, b: float) -> float:
    """Divide a by b. BUG: crashes on b=0."""
    return a / b  # BUG: no zero check!


def add(a: float, b: float) -> float:
    return a + b


def subtract(a: float, b: float) -> float:
    return a - b
'''

FAILING_TEST = '''\
"""Tests for calculator. The divide test is currently FAILING."""
import pytest
from calculator import divide, add, subtract


def test_add():
    assert add(2, 3) == 5


def test_subtract():
    assert subtract(5, 3) == 2


def test_divide_normal():
    assert divide(10, 2) == 5.0


def test_divide_by_zero():
    """This test FAILS because the bug hasn\'t been fixed."""
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        divide(10, 0)
'''


def create_demo_repo(base_dir: Path) -> Path:
    """Create a minimal Python repo with a known bug."""
    repo = base_dir / "demo_calculator"
    repo.mkdir()

    (repo / "calculator.py").write_text(BROKEN_CALCULATOR)
    (repo / "test_calculator.py").write_text(FAILING_TEST)
    (repo / "README.md").write_text("# Demo Calculator\nA simple calculator with a division bug.\n")

    # Init git repo
    for cmd in [
        ["git", "init"],
        ["git", "config", "user.email", "demo@test.com"],
        ["git", "config", "user.name", "Demo"],
        ["git", "add", "."],
        ["git", "commit", "-m", "Initial commit with bug"],
    ]:
        subprocess.run(cmd, cwd=str(repo), capture_output=True)

    return repo


def simulate_agent_run(repo_path: Path) -> None:
    """
    Simulate what DevAgent would do, without GitHub API.
    Directly calls agent nodes with a fake state.
    """
    print("\n" + "="*60)
    print("DevAgent Local Demo")
    print("="*60)
    print(f"Repo: {repo_path}")
    print()

    # Set up tools
    import tools.filesystem as fs
    fs.set_allowed_base(repo_path)

    from tools.bash_executor import run_tests

    # Show failing tests before fix
    print("BEFORE FIX — Running tests...")
    result_before = run_tests(str(repo_path))
    print(f"  Passed: {result_before['passed']}")
    print(f"  Output: {result_before['output'][-300:]}")
    print()

    # Fake state matching AgentState
    state = {
        "issue_url": "local://demo/issues/1",
        "issue_number": 1,
        "issue_title": "divide() crashes with ZeroDivisionError when b=0",
        "issue_body": (
            "When calling divide(10, 0), the function raises ZeroDivisionError "
            "instead of a descriptive ValueError. "
            "Expected: raise ValueError('Cannot divide by zero')"
        ),
        "repo_owner": "demo",
        "repo_name": "calculator",
        "repo_path": str(repo_path),
        "action_plan": [
            "Step 1: Read calculator.py to understand the divide function",
            "Step 2: Add a zero-check before the division",
            "Step 3: Raise ValueError with message 'Cannot divide by zero'",
        ],
        "files_to_edit": [str(repo_path / "calculator.py")],
        "messages": [],
        "code_changes": [],
        "test_result": None,
        "retry_count": 0,
        "branch_name": "devagent/fix-1-demo",
        "pr_url": None,
        "error": None,
        "status": "running",
    }

    # Check if Cerebras key is available
    api_key = os.getenv("CEREBRAS_API_KEY")
    if not api_key:
        print("No CEREBRAS_API_KEY found — demonstrating the FIX manually.\n")
        print("What the Coder node would do:")
        print("  str_replace(calculator.py,")
        print("    old: 'return a / b  # BUG: no zero check!'")
        print("    new: 'if b == 0:\\n        raise ValueError(\"Cannot divide by zero\")\\n    return a / b'")
        print()

        # Apply the fix manually to show the test pass
        calc_path = repo_path / "calculator.py"
        original = calc_path.read_text()
        fixed = original.replace(
            "return a / b  # BUG: no zero check!",
            "if b == 0:\n        raise ValueError(\"Cannot divide by zero\")\n    return a / b"
        )
        calc_path.write_text(fixed)
        print("Fix applied manually. Running tests...")

    else:
        print("CEREBRAS_API_KEY found. Running full agent pipeline...")
        # Run real Coder node
        from agent.coder import coder_node
        print("  Running Coder node...")
        coder_result = coder_node(state)
        state.update(coder_result)
        print(f"  Changes: {state.get('code_changes')}")

    # Show tests after fix
    print("\nAFTER FIX — Running tests...")
    result_after = run_tests(str(repo_path))
    print(f"  Passed: {result_after['passed']}")
    print(f"  Output: {result_after['output'][-300:]}")
    print()

    if result_after["passed"]:
        print("✅ Demo complete! The agent fixed the bug and all tests pass.")
        print()
        print("To run with a real GitHub issue:")
        print("  python main.py --issue https://github.com/OWNER/REPO/issues/N")
    else:
        print("❌ Tests still failing. Check your Cerebras API key and model.")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        repo = create_demo_repo(Path(tmp))
        simulate_agent_run(repo)
