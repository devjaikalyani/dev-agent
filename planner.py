"""planner.py — ONE API call → JSON plan."""
from __future__ import annotations
import json
from .state import AgentState
from .mistral_client import chat
from tools.filesystem import list_directory
from rich.console import Console

console = Console()

_SYSTEM = """\
You are a senior software engineer. Given a GitHub issue and repo structure, \
output ONLY a valid JSON object — no markdown fences, no explanation:
{
  "action_plan": ["step 1", "step 2", "step 3"],
  "files_to_edit": ["src/calculator.py"],
  "test_command": "python -m pytest tests/ -v",
  "reasoning": "one sentence root cause"
}
Max 5 steps. Max 4 files. ONLY the raw JSON object."""


def planner_node(state: AgentState) -> dict:
    console.print("[bold cyan]Planning...[/bold cyan]")

    repo_map = list_directory.invoke({"repo_root": state["repo_path"], "path": ".", "max_depth": 2})

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",   "content":
            f"Issue #{state['issue_number']}: {state['issue_title']}\n\n"
            f"{state['issue_body']}\n\n"
            f"Repo structure:\n{repo_map}"},
    ]

    msg, tokens = chat(messages, max_tokens=512, temperature=0.0, json_mode=True)
    resp = msg.content or ""

    try:
        raw  = resp.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data = json.loads(raw)
    except Exception:
        data = {"action_plan": ["Explore repo", "Identify root cause", "Apply fix", "Run tests"],
                "files_to_edit": [], "test_command": "python -m pytest tests/ -v", "reasoning": resp[:200]}

    plan  = data.get("action_plan", [])
    files = data.get("files_to_edit", [])
    tcmd  = data.get("test_command", "python -m pytest tests/ -v")

    console.print(f"[dim]  {len(plan)} steps | files: {files}[/dim]")
    for i, s in enumerate(plan, 1):
        console.print(f"[dim]    {i}. {s}[/dim]")

    return {
        "action_plan":   plan,
        "files_to_edit": files,
        "repo_map":      repo_map,
        "test_command":  tcmd,
        "messages":      [],
        "total_tokens":  state.get("total_tokens", 0) + tokens,
    }