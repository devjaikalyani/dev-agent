"""
tester.py — Tester node. No API calls — pure subprocess.
Auto-detects test runner and reports pass/fail.
Now installs package in development mode before testing.
"""
from __future__ import annotations
import re
import subprocess
import sys
from pathlib import Path
from .state import AgentState
from rich.console import Console

console = Console()

_RUNNERS = [
    ("pytest.ini",     "python -m pytest -x -v --tb=short"),
    ("setup.cfg",      "python -m pytest -x -v --tb=short"),
    ("pyproject.toml", "python -m pytest -x -v --tb=short"),
    ("tox.ini",        "python -m tox"),
    ("Makefile",       "make test"),
    ("package.json",   "npm test"),
    ("Cargo.toml",     "cargo test"),
    ("go.mod",         "go test ./..."),
]

def _detect_cmd(repo_path: str) -> str:
    root = Path(repo_path)
    for fname, cmd in _RUNNERS:
        if (root / fname).exists():
            return cmd
    return "python -m pytest -x -v --tb=short"

def _install_dependencies(repo_path: str) -> tuple[bool, str]:
    """Install the package in development mode and its dependencies."""
    root = Path(repo_path)
    
    # Check for different package management files
    if (root / "pyproject.toml").exists():
        # Modern Python with pyproject.toml
        try:
            # Try to install with pip first
            result = subprocess.run(
                f"cd {repo_path} && pip install -e .",
                shell=True, capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                return True, "Package installed successfully"
            
            # If that fails, try installing dependencies only
            result = subprocess.run(
                f"cd {repo_path} && pip install .",
                shell=True, capture_output=True, text=True, timeout=60
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, "Timeout installing dependencies"
    
    elif (root / "setup.py").exists():
        # Legacy Python with setup.py
        try:
            result = subprocess.run(
                f"cd {repo_path} && pip install -e .",
                shell=True, capture_output=True, text=True, timeout=60
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, "Timeout installing dependencies"
    
    elif (root / "requirements.txt").exists():
        # Just requirements.txt, no package
        try:
            result = subprocess.run(
                f"cd {repo_path} && pip install -r requirements.txt",
                shell=True, capture_output=True, text=True, timeout=60
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, "Timeout installing dependencies"
    
    # No package management files found
    return True, "No dependencies to install"

def tester_node(state: AgentState) -> dict:
    console.print("[bold cyan]Running tests...[/bold cyan]")

    repo_path = state["repo_path"]
    cmd       = state.get("test_command") or _detect_cmd(repo_path)

    # First, install dependencies
    console.print("  [dim]Installing dependencies...[/dim]")
    install_ok, install_output = _install_dependencies(repo_path)
    
    if not install_ok:
        console.print("  [yellow]Warning: Failed to install dependencies[/yellow]")
        console.print(f"  [dim]{install_output[:200]}[/dim]")
    
    # Run the actual tests
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=repo_path,
            capture_output=True, text=True, timeout=120,
        )
        output    = result.stdout + result.stderr
        exit_code = result.returncode
    except subprocess.TimeoutExpired:
        output    = "ERROR: tests timed out after 120s"
        exit_code = 1

    passed = (exit_code == 0)

    # Extra check: even exit 0 with "failed" text = failure
    if passed and re.search(r"\d+ failed", output):
        passed = False

    status = "[green]PASSED ✓[/green]" if passed else "[red]FAILED ✗[/red]"
    console.print(f"  Tests: {status}")
    if not passed:
        # Show last 20 lines of output for quick diagnosis
        lines = [l for l in output.splitlines() if l.strip()][-20:]
        if lines:
            console.print("[dim]" + "\n".join(f"  {l}" for l in lines) + "[/dim]")

    return {
        "test_output": output[:4000],
        "test_passed": passed,
        "retry_count": state.get("retry_count", 0),
        "total_tokens": state.get("total_tokens", 0),
    }