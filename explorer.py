"""
explorer.py — Explorer node.
Reads relevant files, passes clean context to coder.
Zero LLM calls — pure filesystem reads.

FIXES:
- Only puts REAL file paths into files_to_edit (not "search_results" fake keys)
- Passes file contents as assistant message so coder gets clean conversation history
"""
from __future__ import annotations
from .state import AgentState
from tools.filesystem import read_file, list_directory, search_code
from rich.console import Console

console = Console()


def explorer_node(state: AgentState) -> dict:
    console.print("[bold cyan]Exploring codebase...[/bold cyan]")

    repo_path  = state["repo_path"]
    files_hint = state.get("files_to_edit", [])

    real_files: dict[str, str] = {}   # path → content, ONLY real file paths

    # 1. Read every file the planner suggested
    for rel_path in files_hint:
        # Skip fake/synthetic keys
        if not rel_path or rel_path.startswith("_") or "." not in rel_path:
            continue
        content = read_file.invoke({"repo_root": repo_path, "path": rel_path})
        if not content.startswith("ERROR"):
            real_files[rel_path] = content
            console.print(f"[dim]  read: {rel_path} ({len(content)} chars)[/dim]")
        else:
            console.print(f"[dim]  {content}[/dim]")

    # 2. If no files found, search by function name from issue title
    if not real_files:
        words = [w for w in state.get("issue_title", "").split()
                 if len(w) > 3 and w.replace("_","").isalpha()]
        query = words[0] if words else "def "
        hits = search_code.invoke({
            "repo_root": repo_path,
            "pattern":   query,
            "file_pattern": "*.py",
        })
        # Extract actual file paths from grep output: "path/file.py:line:content"
        import re
        found_paths = list(dict.fromkeys(
            m.group(1) for line in hits.splitlines()
            if (m := re.match(r"^([^:]+\.py):", line))
        ))
        for p in found_paths[:4]:
            content = read_file.invoke({"repo_root": repo_path, "path": p})
            if not content.startswith("ERROR"):
                real_files[p] = content
                console.print(f"[dim]  found+read: {p}[/dim]")

    # 3. Always read test files — coder needs to know what's expected
    test_hits = search_code.invoke({
        "repo_root": repo_path,
        "pattern":   "def test_",
        "file_pattern": "*.py",
    })
    import re
    test_paths = list(dict.fromkeys(
        m.group(1) for line in test_hits.splitlines()
        if (m := re.match(r"^([^:]+\.py):", line))
    ))
    for tp in test_paths[:2]:
        if tp not in real_files:
            content = read_file.invoke({"repo_root": repo_path, "path": tp})
            if not content.startswith("ERROR"):
                real_files[tp] = content
                console.print(f"[dim]  read test: {tp}[/dim]")

    console.print(f"[dim]  Explorer done — {len(real_files)} file(s) read, 0 API calls[/dim]")

    # Build a SINGLE clean system-level context block
    # Use role="system" so it doesn't create double-user-message issue
    context_parts = []
    for path, content in real_files.items():
        context_parts.append(f"### File: {path}\n```\n{content}\n```")

    context_msg = {
        "role":    "system",
        "content": "## Codebase Files\n\n" + "\n\n".join(context_parts),
    }

    return {
        "messages":      [context_msg],          # fresh, clean message list
        "files_to_edit": list(real_files.keys()), # ONLY real file paths
        "total_tokens":  state.get("total_tokens", 0),
    }