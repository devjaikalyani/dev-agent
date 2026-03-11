"""
main.py — DevAgent CLI entry point.

Usage:
  python main.py --issue https://github.com/owner/repo/issues/42
  python main.py --issue URL --dry-run     # plan only, no code changes
  python main.py --issue URL --no-pr       # fix but don't open a PR
"""
from __future__ import annotations

import sys
import time
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich import print as rprint

import config
from tools.github_client import (
    fetch_issue, 
    clone_repo, 
    parse_issue_url,
    fork_repo,
)

console = Console()
app_cli = typer.Typer(
    name="devagent",
    help="Autonomous software engineering agent powered by Mistral.",
    add_completion=False,
)


def _print_banner() -> None:
    console.print(Panel.fit(
        "[bold green]DevAgent[/bold green] — Agentic SWE powered by [bold cyan]Mistral[/bold cyan]\n"
        f"[dim]Model: {config.MISTRAL_MODEL}  |  Max retries: {config.MAX_RETRIES}[/dim]",
        border_style="green",
    ))


def _print_state_summary(state: dict) -> None:
    """Pretty-print final state after the run."""
    table = Table(title="Run Summary", border_style="dim")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Issue",       f"#{state.get('issue_number')} — {state.get('issue_title', '')[:60]}")
    table.add_row("Repo",        f"{state.get('repo_owner')}/{state.get('repo_name')}")
    table.add_row("Tests",       "✓ PASSED" if state.get("test_passed") else "✗ FAILED")
    table.add_row("Retries",     str(state.get("retry_count", 0)))
    table.add_row("Files changed", str(len(state.get("code_changes", []))))
    table.add_row("PR URL",      state.get("pr_url") or "—")
    table.add_row("Error",       state.get("error") or "—")

    console.print(table)


@app_cli.command()
def run(
    issue: str = typer.Option(..., "--issue", "-i", help="GitHub issue URL"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan only — no code changes"),
    no_pr: bool = typer.Option(False, "--no-pr", help="Fix code but skip opening a PR"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed agent output"),
) -> None:
    """Run DevAgent on a GitHub issue."""

    _print_banner()

    # ── Validate config ──────────────────────────────────────────────────────
    try:
        config.validate()
    except EnvironmentError as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(1)

    start_time = time.time()

    # ── Step 1: Parse issue URL ──────────────────────────────────────────────
    console.print(f"\n[bold]Step 1:[/bold] Parsing issue URL...")
    try:
        owner, repo_name, issue_num = parse_issue_url(issue)
        console.print(f"  [green]✓[/green] {owner}/{repo_name}#{issue_num}")
    except Exception as e:
        console.print(f"[red]Failed to parse issue URL:[/red] {e}")
        raise typer.Exit(1)

    # ── Step 2: Fetch issue ──────────────────────────────────────────────────
    console.print(f"\n[bold]Step 2:[/bold] Fetching issue from GitHub...")
    try:
        issue_data = fetch_issue(owner, repo_name, issue_num)
        # Add parsed info to issue_data
        issue_data["repo_owner"] = owner
        issue_data["repo_name"] = repo_name
        issue_data["number"] = issue_num
    except Exception as e:
        console.print(f"[red]Failed to fetch issue:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"  [green]✓[/green] #{issue_data['number']}: {issue_data['title']}")

    # ── Step 3: Fork repository (if not dry run and not no_pr) ───────────────
    use_fork = not (dry_run or no_pr)
    fork_owner = owner
    
    if use_fork:
        console.print(f"\n[bold]Step 3:[/bold] Forking repository...")
        try:
            fork_owner = fork_repo(owner, repo_name)
            console.print(f"  [green]✓[/green] Forked to {fork_owner}/{repo_name}")
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to fork, using original repo: {e}[/yellow]")
            fork_owner = owner

    # ── Step 4: Clone repo ───────────────────────────────────────────────────
    console.print(f"\n[bold]Step 4:[/bold] Cloning repository...")
    try:
        # Clone from fork if available, otherwise from original
        repo_path = clone_repo(fork_owner, repo_name, use_fork=(fork_owner != owner))
        console.print(f"  [green]✓[/green] Cloned to {repo_path}")
    except Exception as e:
        console.print(f"[red]Failed to clone repo:[/red] {e}")
        raise typer.Exit(1)

    if dry_run:
        console.print("\n[yellow]Dry-run mode — stopping before code changes.[/yellow]")
        raise typer.Exit(0)

    # ── Step 5: Build initial state ──────────────────────────────────────────
    initial_state = {
        "issue_url":    issue,
        "issue_number": issue_num,
        "issue_title":  issue_data["title"],
        "issue_body":   issue_data["body"],
        "repo_owner":   owner,  # Original repo owner for PR
        "repo_name":    repo_name,
        "fork_owner":   fork_owner,  # Fork owner for pushing
        "repo_path":    repo_path,
        "no_pr":        no_pr,  # Pass the flag to the graph
        # Initialised fields
        "action_plan":   [],
        "files_to_edit": [],
        "messages":      [],
        "code_changes":  [],
        "test_output":   None,
        "test_passed":   False,
        "retry_count":   0,
        "branch_name":   None,
        "pr_url":        None,
        "error":         None,
    }

    # ── Step 6: Run the agent graph ──────────────────────────────────────────
    console.print(f"\n[bold]Step 5:[/bold] Running DevAgent...\n")

    from agent.graph import app  # import here to avoid circular at top

    node_labels = {
        "plan":    "🧠 Planning fix...",
        "explore": "🔍 Exploring codebase...",
        "code":    "✏️  Writing code...",
        "test":    "🧪 Running tests...",
        "debug":   "🔧 Debugging failures...",
        "open_pr": "📬 Opening pull request...",
    }

    final_state = initial_state.copy()

    # Stream node-by-node updates
    for chunk in app.stream(initial_state, stream_mode="updates"):
        for node_name, node_output in chunk.items():
            label = node_labels.get(node_name, f"⚙️  {node_name}...")
            console.print(f"  [cyan]{label}[/cyan]")

            if verbose and isinstance(node_output, dict):
                if "action_plan" in node_output:
                    for step in node_output["action_plan"]:
                        console.print(f"    [dim]  • {step}[/dim]")
                if "test_output" in node_output and node_output["test_output"]:
                    status = "✓ PASS" if node_output.get("test_passed") else "✗ FAIL"
                    console.print(f"    [dim]  Tests: {status}[/dim]")
                if "pr_url" in node_output and node_output["pr_url"]:
                    console.print(f"    [green]  PR: {node_output['pr_url']}[/green]")

            # Accumulate state
            if isinstance(node_output, dict):
                final_state.update(node_output)

    # ── Results ──────────────────────────────────────────────────────────────
    elapsed = time.time() - start_time
    console.print(f"\n[bold]Completed in {elapsed:.1f}s[/bold]\n")
    _print_state_summary(final_state)

    if final_state.get("pr_url") and not no_pr:
        console.print(f"\n[bold green]✓ PR opened:[/bold green] {final_state['pr_url']}")
        raise typer.Exit(0)
    elif final_state.get("test_passed"):
        console.print(f"\n[bold green]✓ Bug fixed successfully![/bold green] (PR not opened due to --no-pr flag)")
        raise typer.Exit(0)
    elif not final_state.get("test_passed"):
        console.print(f"\n[bold red]✗ Agent could not fix the issue after {config.MAX_RETRIES} retries.[/bold red]")
        console.print("[dim]Check logs/ directory for full output.[/dim]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app_cli()