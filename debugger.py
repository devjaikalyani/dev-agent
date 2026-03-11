"""debugger.py — Fixes failing tests using Mistral tool calling."""
from __future__ import annotations
import json, re
from .state import AgentState
from .mistral_client import chat
from tools.filesystem import read_file, str_replace_in_file, write_file
from rich.console import Console

console = Console()

_SYSTEM = """\
You are fixing failing tests.

## WORKFLOW
1. Read the test failure — find the EXACT assertion/error.
2. Look at the current file content shown — understand what needs to change.
3. Call str_replace_in_file with old_str copied EXACTLY from the file content.
4. Stop.

## IF str_replace RETURNS AN ERROR
- old_str didn't match. Call read_file for the absolute latest content.
- Copy old_str from that fresh output and retry.
- If it fails again, use write_file with the complete corrected file.

## CRITICAL
- old_str must be byte-for-byte identical to what is in the file
- Implement exactly what the test expects — nothing more, nothing less"""

_TOOLS = [
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read current file content. Use when str_replace fails.",
        "parameters": {"type": "object",
            "properties": {
                "repo_root": {"type": "string"},
                "path":      {"type": "string"},
            }, "required": ["repo_root", "path"]},
    }},
    {"type": "function", "function": {
        "name": "str_replace_in_file",
        "description": "Replace exact string. old_str must exactly match file content.",
        "parameters": {"type": "object",
            "properties": {
                "repo_root": {"type": "string"},
                "path":      {"type": "string"},
                "old_str":   {"type": "string"},
                "new_str":   {"type": "string"},
            }, "required": ["repo_root", "path", "old_str", "new_str"]},
    }},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Overwrite entire file. Use when str_replace keeps failing.",
        "parameters": {"type": "object",
            "properties": {
                "repo_root": {"type": "string"},
                "path":      {"type": "string"},
                "content":   {"type": "string"},
            }, "required": ["repo_root", "path", "content"]},
    }},
]

_DISPATCH = {
    "read_file":           lambda a: read_file.invoke(a),
    "str_replace_in_file": lambda a: str_replace_in_file.invoke(a),
    "write_file":          lambda a: write_file.invoke(a),
}


def _parse_args(raw) -> dict:
    if isinstance(raw, dict): return raw
    if isinstance(raw, str):
        try: return json.loads(raw)
        except Exception: return {}
    return {}


def _msg_to_dict(msg) -> dict:
    d: dict = {"role": "assistant", "content": msg.content or ""}
    if getattr(msg, "tool_calls", None):
        d["tool_calls"] = [
            {"id": tc.id, "type": "function",
             "function": {
                 "name": tc.function.name,
                 "arguments": (tc.function.arguments if isinstance(tc.function.arguments, str)
                               else json.dumps(tc.function.arguments)),
             }}
            for tc in msg.tool_calls
        ]
    return d


def debugger_node(state: AgentState) -> dict:
    retry     = state.get("retry_count", 0) + 1
    repo_path = state["repo_path"]
    console.print(f"[bold yellow]Debugging attempt {retry}...[/bold yellow]")

    # Pre-read every changed/planned file for fresh content
    file_blocks: list[str] = []
    seen: set[str] = set()
    candidates = [c["file"] for c in state.get("code_changes", [])] + state.get("files_to_edit", [])

    for rel_path in candidates:
        if not rel_path or rel_path in seen or not re.search(r'\.\w+$', rel_path):
            continue
        seen.add(rel_path)
        content = read_file.invoke({"repo_root": repo_path, "path": rel_path})
        if not content.startswith("ERROR"):
            file_blocks.append(f"### Current content of {rel_path}\n```python\n{content}\n```")
            console.print(f"[dim]  pre-read: {rel_path}[/dim]")

    file_section = "\n\n".join(file_blocks) or "(use read_file to get content)"

    messages: list[dict] = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",   "content":
            f"## Test failure (attempt {retry})\n"
            f"```\n{state.get('test_output', 'no output')[:2500]}\n```\n\n"
            f"## Current file contents\n{file_section}\n\n"
            f"## repo_root (use exactly)\n{repo_path}\n\n"
            f"Apply the fix now."
        },
    ]

    new_changes: list[dict] = []
    tokens = state.get("total_tokens", 0)

    for _ in range(8):
        msg, tok = chat(messages, tools=_TOOLS, temperature=0.0)
        tokens += tok
        messages.append(_msg_to_dict(msg))

        if not getattr(msg, "tool_calls", None):
            if msg.content:
                console.print(f"[dim]  LLM: {msg.content[:200]}[/dim]")
            break

        for tc in msg.tool_calls:
            name = tc.function.name
            args = _parse_args(tc.function.arguments)
            fn   = _DISPATCH.get(name)
            result = str(fn(args)) if fn else f"ERROR: unknown tool '{name}'"
            ok     = "ERROR" not in result

            if name == "str_replace_in_file":
                console.print(
                    f"[{'green' if ok else 'red'}]  "
                    f"str_replace({args.get('path','?')}) "
                    f"{'✓' if ok else '✗  ' + result[:100]}"
                    f"[/{'green' if ok else 'red'}]"
                )
                if not ok:
                    console.print(f"[dim]    old_str: {repr(args.get('old_str','')[:100])}[/dim]")
            elif name == "write_file":
                console.print(f"[{'green' if ok else 'red'}]  write_file({args.get('path','?')}) {'✓' if ok else '✗'}[/{'green' if ok else 'red'}]")
            elif name == "read_file":
                console.print(f"[dim]  read_file({args.get('path','?')}) → {len(result)} chars[/dim]")

            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "name": name, "content": result[:3000]})

            if name in ("str_replace_in_file", "write_file") and ok:
                new_changes.append({"tool": name, "file": args.get("path", "unknown")})

    console.print(f"[dim]  Debugger done — {len(new_changes)} edit(s)[/dim]")
    return {
        "retry_count":  retry,
        "code_changes": state.get("code_changes", []) + new_changes,
        "total_tokens": tokens,
        "messages":     state.get("messages", []),
    }