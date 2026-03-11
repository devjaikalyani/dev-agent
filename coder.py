"""
coder.py — Writes the code fix using Mistral tool calling.

Mistral note: tool_calls[i].function.arguments may be a dict OR a JSON string.
Always use _parse_args() to handle both.
"""
from __future__ import annotations
import json
from .state import AgentState
from .mistral_client import chat   # actually mistral_client now
from tools.filesystem import read_file, write_file, str_replace_in_file, search_code
from rich.console import Console

console = Console()

_SYSTEM = """\
You are an expert software engineer fixing a GitHub issue.

The source files are shown in the user message.

## WORKFLOW
1. Call str_replace_in_file to apply the fix.
   - old_str MUST be copied EXACTLY from the file shown — character for character.
   - If unsure, call read_file first to get the fresh exact content, then copy from that.
2. If str_replace_in_file returns an error, call read_file to see the current file, then retry.
3. If str_replace fails twice on the same file, use write_file with the complete corrected file content.
4. Stop once the fix is applied.

## RULES
- Minimal change only — do not refactor unrelated code
- Match existing indentation and style exactly
- repo_root is provided in the task — use it exactly as given in every tool call"""

_TOOLS = [
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read current file content. Call before str_replace if unsure of exact text.",
        "parameters": {"type": "object",
            "properties": {
                "repo_root": {"type": "string", "description": "Absolute path to repo root"},
                "path":      {"type": "string", "description": "Relative path e.g. src/calculator.py"},
            }, "required": ["repo_root", "path"]},
    }},
    {"type": "function", "function": {
        "name": "str_replace_in_file",
        "description": "Replace an EXACT string in a file. old_str must match the file content exactly.",
        "parameters": {"type": "object",
            "properties": {
                "repo_root": {"type": "string"},
                "path":      {"type": "string"},
                "old_str":   {"type": "string", "description": "Exact text to replace — must appear once"},
                "new_str":   {"type": "string", "description": "Replacement text"},
            }, "required": ["repo_root", "path", "old_str", "new_str"]},
    }},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Overwrite entire file. Use ONLY when str_replace_in_file fails twice.",
        "parameters": {"type": "object",
            "properties": {
                "repo_root": {"type": "string"},
                "path":      {"type": "string"},
                "content":   {"type": "string", "description": "Complete corrected file content"},
            }, "required": ["repo_root", "path", "content"]},
    }},
    {"type": "function", "function": {
        "name": "search_code",
        "description": "Search for a pattern in the repo — use only to find a file path.",
        "parameters": {"type": "object",
            "properties": {
                "repo_root":    {"type": "string"},
                "pattern":      {"type": "string"},
                "file_pattern": {"type": "string", "description": "Optional file pattern e.g. '*.py'"},
            }, "required": ["repo_root", "pattern"]},
    }},
]

def _safe_search_call(args: dict) -> str:
    """Safely call search_code with proper argument handling."""
    # Ensure required fields are present
    if "repo_root" not in args:
        return "ERROR: Missing required argument 'repo_root' for search_code"
    if "pattern" not in args:
        # Try to find pattern in alternative keys
        pattern = args.get("query") or args.get("search") or args.get("q")
        if pattern:
            args["pattern"] = pattern
        else:
            return "ERROR: Missing required argument 'pattern' for search_code"
    
    # Ensure file_pattern exists
    if "file_pattern" not in args:
        args["file_pattern"] = ""
    
    return str(search_code.invoke(args))

_DISPATCH = {
    "read_file":           lambda a: str(read_file.invoke(a)),
    "str_replace_in_file": lambda a: str(str_replace_in_file.invoke(a)),
    "write_file":          lambda a: str(write_file.invoke(a)),
    "search_code":         lambda a: _safe_search_call(a),
}


def _parse_args(raw) -> dict:
    """Mistral may return arguments as dict or JSON string — handle both."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _msg_to_dict(msg) -> dict:
    """Convert Mistral message object → plain dict for history."""
    d: dict = {"role": "assistant", "content": msg.content or ""}
    if getattr(msg, "tool_calls", None):
        d["tool_calls"] = [
            {"id": tc.id, "type": "function",
             "function": {
                 "name":      tc.function.name,
                 "arguments": (tc.function.arguments if isinstance(tc.function.arguments, str)
                               else json.dumps(tc.function.arguments)),
             }}
            for tc in msg.tool_calls
        ]
    return d


def coder_node(state: AgentState) -> dict:
    console.print("[bold cyan]Writing fix...[/bold cyan]")

    repo_path = state["repo_path"]
    plan_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(state["action_plan"]))

    # Pull file context from explorer
    file_context = ""
    for m in state.get("messages", []):
        c = m.get("content", "")
        if m.get("role") == "user" and c.startswith("###"):
            file_context = c
            break

    messages: list[dict] = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",   "content":
            f"## Issue #{state['issue_number']}: {state['issue_title']}\n\n"
            f"{state['issue_body']}\n\n"
            f"## Action plan\n{plan_text}\n\n"
            f"## repo_root (use this exact string in every tool call)\n{repo_path}\n\n"
            f"## Source files\n{file_context}\n\n"
            f"Apply the fix now."
        },
    ]

    code_changes: list[dict] = []
    tokens = state.get("total_tokens", 0)

    for _ in range(10):
        msg, tok = chat(messages, tools=_TOOLS, temperature=0.0)
        tokens += tok
        messages.append(_msg_to_dict(msg))

        if not getattr(msg, "tool_calls", None):
            if msg.content:
                console.print(f"[yellow]  No tool calls — LLM: {msg.content[:300]}[/yellow]")
            break

        for tc in msg.tool_calls:
            name = tc.function.name
            args = _parse_args(tc.function.arguments)
            
            # Debug print for search_code
            if name == "search_code":
                console.print(f"[yellow]DEBUG - search_code args: {json.dumps(args, indent=2)}[/yellow]")

            fn     = _DISPATCH.get(name)
            if not fn:
                result = f"ERROR: unknown tool '{name}'"
                ok = False
            else:
                result = fn(args)
                ok = "ERROR" not in result

            # Verbose per-tool logging
            if name == "read_file":
                console.print(f"[dim]  read_file({args.get('path','?')}) → {len(result)} chars[/dim]")
            elif name == "str_replace_in_file":
                console.print(
                    f"[{'green' if ok else 'red'}]  "
                    f"str_replace({args.get('path','?')}) "
                    f"{'✓' if ok else '✗  ' + result[:120]}"
                    f"[/{'green' if ok else 'red'}]"
                )
                if not ok:
                    console.print(f"[dim]    old_str attempted: {repr(args.get('old_str','')[:120])}[/dim]")
            elif name == "write_file":
                console.print(f"[{'green' if ok else 'red'}]  write_file({args.get('path','?')}) {'✓' if ok else '✗'}[/{'green' if ok else 'red'}]")
            elif name == "search_code":
                console.print(f"[dim]  search_code({args.get('pattern','?')}) → {len(result)} chars[/dim]")
            else:
                console.print(f"[dim]  {name}(...)[/dim]")

            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "name": name, "content": result[:3000]})

            if name in ("str_replace_in_file", "write_file") and ok:
                code_changes.append({"tool": name, "file": args.get("path", "unknown")})

    console.print(f"[dim]  Coder done — {len(code_changes)} edit(s): {[c['file'] for c in code_changes]}[/dim]")
    return {"messages": messages, "code_changes": code_changes, "total_tokens": tokens}