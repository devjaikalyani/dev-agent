# DevAgent — Autonomous Software Engineering Agent

> Give it a GitHub issue URL. It opens a tested Pull Request. Zero human intervention.

DevAgent is an agentic AI system that reads a GitHub issue, navigates the codebase, writes a fix, runs the test suite, and opens a pull request — all autonomously. Built with **LangGraph** for orchestration and **Mistral API** for LLM inference (free tier, no credit card required).

```
$ python main.py --issue https://github.com/owner/repo/issues/42

  Planning...       1 API call  →  JSON action plan
  Exploring...      0 API calls →  reads files from disk
  Writing fix...    tool loop   →  str_replace_in_file ✓
  Running tests...  0 API calls →  pytest passes ✓
  Opening PR...     1 API call  →  PR #43 opened
```

---

## Table of Contents

- [How It Works](#how-it-works)
- [Agent Pipeline](#agent-pipeline)
- [File Structure](#file-structure)
- [Setup & Installation](#setup--installation)
- [Running the Project](#running-the-project)
- [Configuration Reference](#configuration-reference)
- [Internal Architecture](#internal-architecture)
- [Debugging](#debugging)

---

## How It Works

DevAgent is a **stateful directed graph** with 6 nodes. Each node is a Python function that receives the current `AgentState` dict, does its work, and returns updated fields. LangGraph wires them together and handles routing.

```
GitHub Issue URL
       │
       ▼
  ┌─────────┐    1 LLM call
  │ Planner │──  Reads issue + repo tree → JSON:
  └─────────┘    { action_plan, files_to_edit, test_command }
       │
       ▼
  ┌──────────┐   0 LLM calls
  │ Explorer │──  Reads flagged files from disk,
  └──────────┘    greps for test files, builds context
       │
       ▼
  ┌────────┐     tool-calling loop (max 10 iters)
  │ Coder  │──  str_replace_in_file / write_file / read_file
  └────────┘
       │
       ▼
  ┌────────┐    0 LLM calls
  │ Tester │──  runs pytest / npm test / cargo test (auto-detected)
  └────────┘
       │
       ├── PASS ─────────────────────────┐
       │                                 ▼
       │                         ┌────────────┐  1 LLM call
       │                         │  PR Opener │─ commit → push → open PR
       │                         └────────────┘
       └── FAIL ──┐
                  ▼
            ┌──────────┐  tool-calling loop (max 8 iters)
            │ Debugger │─ pre-reads changed files, patches fix
            └──────────┘
                  │
                  └──→ back to Tester  (up to MAX_RETRIES=5)
                        exhausted → exits with error
```

The LLM is only called when reasoning is needed. Explorer and Tester do **zero** API calls, keeping runs fast (~13s on a simple fix) and cheap.

---

## Agent Pipeline

### Node 1 — Planner `agent/planner.py`
**1 API call.** Receives the issue title, body, and a 2-level directory tree of the repo. Returns structured JSON:
- `action_plan` — up to 5 steps describing what to do
- `files_to_edit` — which files need changing
- `test_command` — how to run the test suite

Uses `json_mode=True` so the response is always valid JSON, no markdown fences.

### Node 2 — Explorer `agent/explorer.py`
**0 API calls.** Reads every file the Planner flagged. If no files are found, falls back to `grep` using keywords from the issue title. Always reads test files too so the Coder knows what the tests expect. Produces a single file-context string injected into the Coder's prompt.

### Node 3 — Coder `agent/coder.py`
**Tool-calling loop, max 10 iterations.** Given the issue, plan, and file contents in one clean message, calls tools to make the fix:

| Tool                  | Purpose                                                |
| --------------------- | ------------------------------------------------------ |
| `read_file`           | Gets current file content before editing               |
| `str_replace_in_file` | Replaces an exact substring (preferred)                |
| `write_file`          | Overwrites entire file (fallback if str_replace fails) |
| `search_code`         | Grep search if a file needs to be located              |

Every tool call result is logged with ✓ or ✗. If `str_replace_in_file` returns an error, the attempted `old_str` is printed so you can see the mismatch.

### Node 4 — Tester `agent/tester.py`
**0 API calls.** Runs the test suite via `subprocess`. Auto-detects runner:

| File present                                  | Command                             |
| --------------------------------------------- | ----------------------------------- |
| `pytest.ini` / `setup.cfg` / `pyproject.toml` | `python -m pytest -x -v --tb=short` |
| `tox.ini`                                     | `python -m tox`                     |
| `Makefile`                                    | `make test`                         |
| `package.json`                                | `npm test`                          |
| `Cargo.toml`                                  | `cargo test`                        |
| `go.mod`                                      | `go test ./...`                     |
| *(fallback)*                                  | `python -m pytest -x -v --tb=short` |

`test_passed = True` only when exit code is `0` AND no `N failed` pattern in output.

### Node 5 — Debugger `agent/debugger.py`
**Tool-calling loop, max 8 iterations.** Called when tests fail. Before the first LLM call it pre-reads every changed file so the model sees the current exact content. Provides the full test failure output and lets the model patch the fix. Routes back to Tester after each attempt.

### Node 6 — PR Opener `agent/pr_opener.py`
**1 API call.** Commits changes to `devagent/fix-{N}-{slug}`, generates a PR description (Summary / Changes / Testing / Closes #N), pushes, and opens the PR via GitHub API.

---

## File Structure

```
DevAgent/
│
├── main.py                     # CLI entry point (Typer)
├── config.py                   # Loads .env, exposes all constants
├── requirements.txt            # Python dependencies
├── setup.py                    # Package setup
├── pyproject.toml              # Build config
├── .env.example                # Environment variable template
│
├── agent/                      # Core agent logic
│   ├── __init__.py
│   ├── graph.py                # LangGraph StateGraph — wires all 6 nodes
│   ├── state.py                # AgentState TypedDict — shared memory
│   ├── mistral_client.py       # Mistral API wrapper (single chat() function)
│   ├── planner.py              # Node 1: issue → action plan
│   ├── explorer.py             # Node 2: reads codebase files
│   ├── coder.py                # Node 3: writes the code fix
│   ├── tester.py               # Node 4: runs test suite
│   ├── debugger.py             # Node 5: patches failing tests
│   └── pr_opener.py            # Node 6: commits, pushes, opens PR
│
├── tools/                      # LangChain tool definitions
│   ├── __init3__.py             # Exports ALL_TOOLS list
│   ├── filesystem.py           # read_file, write_file, str_replace_in_file,
│   │                           # list_directory, search_code, run_bash
│   ├── github_client.py        # fetch_issue, clone_repo, create_pull_request
│   └── bash_executor.py        # Safe subprocess wrapper with timeout
│
├── scripts/
│   ├── test_single.py          # Local integration test (no GitHub needed)
│   │                           # Shows before/after diff + side-by-side view
│   ├── eval_swebench.py        # SWE-bench Lite evaluator
│   └── demo.py                 # Quick demo script
│
├── tests/                      # Unit + integration tests
│   ├── __init2__.py
│   ├── test_tools.py           # Filesystem tool tests
│   ├── test_github_client.py   # URL parsing + mocked API
│   ├── test_planner.py         # Planner node (mocked LLM)
│   ├── test_graph_routing.py   # LangGraph conditional edge logic
│   ├── test_agent_nodes.py     # Node integration tests
│   ├── test_filesystem.py      # Path safety tests
│   ├── test_bash_executor.py   # Bash executor tests
│   └── test_state.py           # AgentState tests
│
└── sandbox/                    # Docker sandbox (optional hardening)
    ├── Dockerfile              # python:3.11-slim, non-root, no network
    ├── run_sandboxed.py        # Runs test suite inside container
    └── run_tests.sh            # Container entry script
```

---

## Setup & Installation

### Prerequisites
- Python 3.11+
- Git

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/DevAgent.git
cd DevAgent
```

### 2. Create a virtual environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Get your API keys

**Mistral API** (free, no credit card needed):
1. Go to [console.mistral.ai](https://console.mistral.ai)
2. Sign up → **API Keys** → Create new key
3. Copy the key

**GitHub Personal Access Token** (needed to open PRs):
1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. Generate new token → Classic
3. Select scopes: `repo` (full control)
4. Copy the token

### 5. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in your keys:

```bash
MISTRAL_API_KEY=your_mistral_api_key_here
MISTRAL_MODEL=mistral-small-latest
GITHUB_TOKEN=your_github_pat_here
```

---

## Running the Project

### Local test — verify setup works first

Creates a tiny buggy Python repo locally, runs DevAgent on it, and shows a full before/after diff. **No GitHub credentials needed.**

```bash
python scripts/test_single.py
```

You should see:

```
✓ DevAgent fixed the bug in ~13s!
  Retries used:  0
  Total tokens:  ~20,000
  Approx cost:   $0.00
```

### Run on a real GitHub issue

```bash
python main.py --issue https://github.com/owner/repo/issues/42
```

**CLI flags:**

```bash
--issue URL          # (required) GitHub issue URL
--dry-run            # plan only — no code changes made
--no-pr              # fix and test, but skip opening the PR
--verbose / -v       # show detailed step-by-step output
```

### Run the unit tests

```bash
pytest tests/ -v                          # all tests
pytest tests/test_tools.py -v             # filesystem tools only
pytest tests/test_graph_routing.py -v     # routing logic only
```

### Run SWE-bench evaluation

```bash
python scripts/eval_swebench.py --limit 10    # 10 issues
python scripts/eval_swebench.py --limit 50    # full evaluation run
```

---

## Configuration Reference

| Variable          | Default                | Description                                                |
| ----------------- | ---------------------- | ---------------------------------------------------------- |
| `MISTRAL_API_KEY` | *(required)*           | Free from [console.mistral.ai](https://console.mistral.ai) |
| `MISTRAL_MODEL`   | `mistral-small-latest` | Model to use (see below)                                   |
| `GITHUB_TOKEN`    | *(required for PR)*    | PAT with `repo` scope                                      |
| `MAX_RETRIES`     | `5`                    | Max debug→test retry loops                                 |
| `MAX_TOKENS`      | `4096`                 | Max tokens per LLM response                                |
| `SANDBOX_TIMEOUT` | `120`                  | Seconds before test run times out                          |
| `CLONE_DIR`       | `/tmp/devagent_repos`  | Where repos are cloned                                     |
| `DEVAGENT_DEBUG`  | `0`                    | Set to `1` for full LLM trace logs                         |

**Free-tier Mistral models with tool calling:**

| Model                  | Notes                                              |
| ---------------------- | -------------------------------------------------- |
| `mistral-small-latest` | ✅ Recommended — fast, reliable tool use            |
| `open-mistral-nemo`    | Fastest, lighter — good for simple fixes           |
| `codestral-latest`     | Coding specialist — needs a separate codestral key |

---

## Internal Architecture

### AgentState — the shared memory

Every node reads from and writes to a single `AgentState` TypedDict. LangGraph merges the returned dict back into the state after each node.

```
issue fields → planner → (action_plan, files_to_edit, test_command)
                       → explorer → (messages with file context)
                                  → coder → (code_changes, messages)
                                          → tester → (test_passed, test_output)
                                                   → pr_opener → (pr_url)
                                                   → debugger  → (retry_count, code_changes)
```

### LLM Client — `mistral_client.chat()`

All LLM calls go through one function. The caller builds the complete `messages` list — the client adds nothing to it. This prevents the double-system-message bug that silently breaks tool-calling flows.

```python
chat(messages, tools=None, temperature=0.0, json_mode=False)
  → (message_object, tokens_used)
```

Handles Mistral's quirk where `tool_calls[i].function.arguments` may come back as a Python `dict` instead of a JSON string — both are handled in every node via `_parse_args()`.

### File Editing Strategy

The Coder and Debugger prefer `str_replace_in_file` over `write_file`:

1. **`str_replace_in_file`** — replaces an exact substring. Minimal diff, safe, fails loudly if `old_str` doesn't match.
2. **`write_file`** — overwrites the entire file. Used as fallback if str_replace fails twice.

The Debugger pre-reads every changed file before its first LLM call so `old_str` is always taken from the current file content.

### Path Safety

All filesystem tools resolve paths through `_safe_path()`:

```python
def _safe_path(repo_root, rel_path):
    resolved = (Path(repo_root) / rel_path).resolve()
    if not str(resolved).startswith(str(Path(repo_root).resolve())):
        raise PermissionError("Path traversal blocked")
    return resolved
```

Any attempt to escape the repo root (e.g. `../../etc/passwd`) raises `PermissionError` before touching disk.

---

## Debugging

**Enable full LLM trace:**

```bash
# .env
DEVAGENT_DEBUG=1
```

Prints every API request (message roles, tool names) and every response (tool calls + arguments, text) to stdout.

**Common issues:**

| Symptom                                                | Likely cause                   | Fix                                                    |
| ------------------------------------------------------ | ------------------------------ | ------------------------------------------------------ |
| `No tool calls — LLM said: ...`                        | Model ignoring tool schema     | Switch to `mistral-small-latest`                       |
| `str_replace ✗ ERROR: old_str not found`               | Whitespace mismatch in old_str | Enable `DEVAGENT_DEBUG=1`, check what old_str was sent |
| `MISTRAL_API_KEY not set`                              | Missing or wrong `.env`        | Run `cp .env.example .env` and add key                 |
| `Failed to clone repo`                                 | Bad GitHub token               | Ensure PAT has `repo` scope                            |
| Tests time out                                         | Slow test suite                | Set `SANDBOX_TIMEOUT=300` in `.env`                    |
| `AttributeError: module 'config' has no attribute ...` | Stale `.pyc` cache             | Run `find . -name "*.pyc" -delete`                     |

---

## Tech Stack

| Layer               | Technology                                                                                       |
| ------------------- | ------------------------------------------------------------------------------------------------ |
| LLM                 | [Mistral API](https://console.mistral.ai) — `mistral-small-latest`                               |
| Agent orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) — StateGraph                              |
| GitHub integration  | [PyGitHub](https://github.com/PyGithub/PyGithub) + [GitPython](https://gitpython.readthedocs.io) |
| CLI                 | [Typer](https://typer.tiangolo.com)                                                              |
| Terminal output     | [Rich](https://rich.readthedocs.io)                                                              |
| Tool definitions    | [LangChain](https://python.langchain.com) `@tool` decorator                                      |
| Testing             | [pytest](https://pytest.org)                                                                     |
