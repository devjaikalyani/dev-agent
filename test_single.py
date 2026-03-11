"""
test_single.py — Local integration test with before/after diff viewer.

Creates a tiny Python project with a known bug, runs DevAgent,
then shows you the original repo, all changes made, and the final state.

Usage:
  python scripts/test_single.py
"""
from __future__ import annotations

import copy
import difflib
import shutil
import sys
import os
import tempfile
import pathlib
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.columns import Columns
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()


# ─────────────────────────────────────────────────────────────────────────────
# 1.  Create the buggy toy repo
# ─────────────────────────────────────────────────────────────────────────────

SOURCE_FILES = {
    "src/__init__.py": "",
    "src/calculator.py": '''\
def safe_divide(a: float, b: float) -> float:
    """Divide a by b. Should handle division by zero gracefully."""
    return a / b   # BUG: raises ZeroDivisionError when b == 0
''',
    "tests/__init__.py": "",
    "tests/test_calculator.py": '''\
import pytest
from src.calculator import safe_divide


def test_normal_division():
    assert safe_divide(10, 2) == 5.0


def test_divide_by_zero_returns_none():
    result = safe_divide(10, 0)
    assert result is None, f"Expected None, got {result}"


def test_divide_by_zero_does_not_raise():
    try:
        result = safe_divide(5, 0)
    except ZeroDivisionError:
        pytest.fail("safe_divide should not raise ZeroDivisionError")
''',
    "pytest.ini": "[pytest]\ntestpaths = tests\n",
}

ISSUE = {
    "number": 1,
    "title":  "safe_divide crashes with ZeroDivisionError when b=0",
    "body": (
        "## Bug Report\n\n"
        "Calling `safe_divide(10, 0)` raises `ZeroDivisionError` instead of returning `None`.\n\n"
        "**Steps to reproduce:**\n"
        "```python\n"
        "from src.calculator import safe_divide\n"
        "safe_divide(10, 0)  # ZeroDivisionError: division by zero\n"
        "```\n\n"
        "**Expected:** returns `None`\n"
        "**Actual:** raises `ZeroDivisionError`"
    ),
}


def create_repo(tmp_path: pathlib.Path) -> None:
    for rel, content in SOURCE_FILES.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)


# ─────────────────────────────────────────────────────────────────────────────
# 2.  Snapshot helpers
# ─────────────────────────────────────────────────────────────────────────────

def snapshot(repo: pathlib.Path) -> dict[str, str]:
    """Capture contents of all .py files in the repo."""
    snap: dict[str, str] = {}
    for f in sorted(repo.rglob("*.py")):
        if any(p in str(f) for p in ["__pycache__", ".venv"]):
            continue
        rel = str(f.relative_to(repo))
        snap[rel] = f.read_text()
    return snap


# ─────────────────────────────────────────────────────────────────────────────
# 3.  Display helpers
# ─────────────────────────────────────────────────────────────────────────────

def show_repo_snapshot(snap: dict[str, str], title: str, border_color: str = "dim") -> None:
    console.print(f"\n[bold {border_color}]{'─'*70}[/bold {border_color}]")
    console.print(f"[bold {border_color}]  {title}[/bold {border_color}]")
    console.print(f"[bold {border_color}]{'─'*70}[/bold {border_color}]")
    for path, content in snap.items():
        console.print(f"\n[bold cyan]  📄 {path}[/bold cyan]")
        syntax = Syntax(
            content,
            "python",
            theme="monokai",
            line_numbers=True,
            indent_guides=True,
        )
        console.print(syntax)


def show_diff(before: dict[str, str], after: dict[str, str]) -> None:
    console.print(f"\n[bold yellow]{'─'*70}[/bold yellow]")
    console.print(f"[bold yellow]  CHANGES MADE BY DEVAGENT[/bold yellow]")
    console.print(f"[bold yellow]{'─'*70}[/bold yellow]")

    all_files = sorted(set(before) | set(after))
    changed = False

    for path in all_files:
        before_lines = before.get(path, "").splitlines(keepends=True)
        after_lines  = after.get(path, "").splitlines(keepends=True)

        if before_lines == after_lines:
            continue   # unchanged

        changed = True

        if path not in before:
            console.print(f"\n[bold green]  ➕ NEW FILE: {path}[/bold green]")
            syntax = Syntax("".join(after_lines), "python", theme="monokai", line_numbers=True)
            console.print(syntax)
            continue

        if path not in after:
            console.print(f"\n[bold red]  ➖ DELETED: {path}[/bold red]")
            continue

        # Unified diff
        console.print(f"\n[bold magenta]  ✏️  MODIFIED: {path}[/bold magenta]")
        diff = list(difflib.unified_diff(
            before_lines, after_lines,
            fromfile=f"BEFORE  {path}",
            tofile=f"AFTER   {path}",
            n=3,
        ))

        diff_text = ""
        for line in diff:
            diff_text += line if line.endswith("\n") else line + "\n"

        # Colour the diff manually
        coloured = Text()
        for line in diff_text.splitlines():
            if line.startswith("+++") or line.startswith("---"):
                coloured.append(line + "\n", style="bold white")
            elif line.startswith("@@"):
                coloured.append(line + "\n", style="bold cyan")
            elif line.startswith("+"):
                coloured.append(line + "\n", style="bold green")
            elif line.startswith("-"):
                coloured.append(line + "\n", style="bold red")
            else:
                coloured.append(line + "\n", style="dim")

        console.print(coloured)

    if not changed:
        console.print("\n  [yellow]No file changes detected.[/yellow]")


def show_side_by_side(before_content: str, after_content: str, filename: str) -> None:
    """Show before/after a single file side by side in a table."""
    before_lines = before_content.splitlines()
    after_lines  = after_content.splitlines()
    max_lines    = max(len(before_lines), len(after_lines))

    table = Table(
        title=f"Side-by-side: {filename}",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold",
    )
    table.add_column("BEFORE", style="red", no_wrap=True, max_width=55)
    table.add_column("AFTER",  style="green", no_wrap=True, max_width=55)

    for i in range(max_lines):
        b_line = before_lines[i] if i < len(before_lines) else ""
        a_line = after_lines[i]  if i < len(after_lines)  else ""
        changed_line = b_line != a_line
        row_style = "bold" if changed_line else ""
        table.add_row(b_line, a_line, style=row_style)

    console.print(table)


def show_test_result(passed: bool, output: str, retries: int, elapsed: float, tokens: int) -> None:
    console.print(f"\n[bold]{'─'*70}[/bold]")
    console.print(f"[bold]  RUN SUMMARY[/bold]")
    console.print(f"[bold]{'─'*70}[/bold]")

    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column("Key",   style="cyan", min_width=20)
    table.add_column("Value", style="white")

    table.add_row("Result",        "[bold green]✓ PASSED[/bold green]" if passed else "[bold red]✗ FAILED[/bold red]")
    table.add_row("Retries used",  str(retries))
    table.add_row("Time elapsed",  f"{elapsed:.1f}s")
    table.add_row("Total tokens",  f"{tokens:,}")
    table.add_row("Approx cost",   f"$0.00 (NVIDIA free tier)")

    console.print(table)

    if not passed:
        console.print("\n[red]  Test output (last 30 lines):[/red]")
        lines = [l for l in output.splitlines() if l.strip()][-30:]
        console.print("[dim]" + "\n".join(f"    {l}" for l in lines) + "[/dim]")


# ─────────────────────────────────────────────────────────────────────────────
# 4.  Main runner
# ─────────────────────────────────────────────────────────────────────────────

def run_test() -> bool:
    console.print(Panel.fit(
        "[bold green]DevAgent[/bold green] — Local Integration Test\n"
        "[dim]Bug: safe_divide() crashes on b=0 | Fix: return None[/dim]",
        border_style="green",
    ))

    # Create repo
    tmp_dir = pathlib.Path(tempfile.mkdtemp(prefix="devagent_test_"))
    create_repo(tmp_dir)
    console.print(f"\n[bold]Repo created:[/bold] {tmp_dir}")

    # Snapshot BEFORE
    snap_before = snapshot(tmp_dir)

    # ── Show original repo ───────────────────────────────────────────────────
    show_repo_snapshot(snap_before, "ORIGINAL REPOSITORY (before DevAgent)", border_color="blue")

    console.print(f"\n\n[bold green]Running DevAgent...[/bold green]")
    console.print("[dim](PR opening is skipped in local test mode)[/dim]\n")

    # Build initial state
    initial_state = {
        "issue_url":     "https://github.com/test/repo/issues/1",
        "issue_number":  ISSUE["number"],
        "issue_title":   ISSUE["title"],
        "issue_body":    ISSUE["body"],
        "repo_owner":    "test",
        "repo_name":     "repo",
        "repo_path":     str(tmp_dir),
        "branch_name":   "",
        "action_plan":   [],
        "files_to_edit": [],
        "repo_map":      "",
        "test_command":  "",
        "messages":      [],
        "code_changes":  [],
        "test_output":   "",
        "test_passed":   False,
        "retry_count":   0,
        "max_retries":   5,
        "pr_url":        None,
        "pr_number":     None,
        "error":         None,
        "total_tokens":  0,
    }

    # Monkey-patch PR opener to skip GitHub API
    import agent.pr_opener as pr_mod
    original_pr_node = pr_mod.pr_opener_node

    def mock_pr_node(state):
        console.print("  [dim][PR opener skipped — local test mode][/dim]")
        return {
            "branch_name":  "devagent/fix-1-test",
            "pr_url":       "https://github.com/test/repo/pull/1",
            "total_tokens": state.get("total_tokens", 0),
        }

    pr_mod.pr_opener_node = mock_pr_node

    start = time.time()
    final: dict = {}

    try:
        from agent import graph as graph_mod
        graph_mod.app = graph_mod.build_graph()

        for chunk in graph_mod.app.stream(initial_state, stream_mode="updates"):
            for node_name, node_output in chunk.items():
                if isinstance(node_output, dict):
                    final.update(node_output)
    finally:
        pr_mod.pr_opener_node = original_pr_node

    elapsed = time.time() - start

    # Snapshot AFTER
    snap_after = snapshot(tmp_dir)

    # ── Show diff ────────────────────────────────────────────────────────────
    show_diff(snap_before, snap_after)

    # ── Show final repo ──────────────────────────────────────────────────────
    show_repo_snapshot(snap_after, "FINAL REPOSITORY (after DevAgent)", border_color="green")

    # ── Side-by-side for changed files ───────────────────────────────────────
    changed_paths = [p for p in snap_after if snap_before.get(p) != snap_after[p]]
    if changed_paths:
        console.print(f"\n[bold yellow]{'─'*70}[/bold yellow]")
        console.print(f"[bold yellow]  SIDE-BY-SIDE VIEW[/bold yellow]")
        console.print(f"[bold yellow]{'─'*70}[/bold yellow]")
        for p in changed_paths:
            show_side_by_side(snap_before.get(p, ""), snap_after.get(p, ""), p)

    # ── Summary ──────────────────────────────────────────────────────────────
    show_test_result(
        passed  = final.get("test_passed", False),
        output  = final.get("test_output", ""),
        retries = final.get("retry_count", 0),
        elapsed = elapsed,
        tokens  = final.get("total_tokens", 0),
    )

    if final.get("test_passed"):
        console.print(f"\n[bold green]✓ DevAgent fixed the bug in {elapsed:.1f}s![/bold green]")
    else:
        console.print(f"\n[bold red]✗ DevAgent could not fix the bug after {final.get('retry_count', 0)} retries.[/bold red]")

    return final.get("test_passed", False)


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)