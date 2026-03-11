# DevAgent — Autonomous Software Engineering Agent

**Powered by Mistral API** (`mistral-small-latest`, free tier)

Takes a GitHub issue URL → plans → explores codebase → writes fix → runs tests → opens a Pull Request. Zero human intervention.

## Architecture

```
GitHub Issue URL
      │
      ▼
  [Planner]  ─── 1 API call → JSON action plan + files to edit
      │
      ▼
  [Explorer] ─── 0 API calls → reads files from disk
      │
      ▼
  [Coder]    ─── tool-calling loop → str_replace_in_file / write_file
      │
      ▼
  [Tester]   ─── 0 API calls → runs pytest/npm test/cargo test/etc.
      │
   ┌──┴──────────────┐
   │ pass            │ fail (up to MAX_RETRIES)
   ▼                 ▼
[PR Opener]     [Debugger] ──→ [Tester] (retry loop)
      │
      ▼
  Pull Request URL
```

## Quick Start

```bash
# 1. Clone and install
git clone <repo>
cd DevAgent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env — add MISTRAL_API_KEY and GITHUB_TOKEN

# 3. Test locally (no GitHub needed)
python scripts/test_single.py

# 4. Run on a real issue
python main.py --issue https://github.com/owner/repo/issues/42
```

## Configuration

```bash
# .env
MISTRAL_API_KEY=your_key_here    # free at https://console.mistral.ai
MISTRAL_MODEL=mistral-small-latest
GITHUB_TOKEN=your_github_pat     # needs: repo, pull_requests scopes
MAX_RETRIES=5
DEVAGENT_DEBUG=0                 # set to 1 for full LLM traces
```

**Free tier Mistral models with tool calling:**
- `mistral-small-latest` — recommended (fast, reliable tool use)
- `open-mistral-nemo` — 12B, very fast, lighter
- `codestral-latest` — coding specialist (separate key)

## CLI Options

```bash
python main.py --issue URL              # full run
python main.py --issue URL --dry-run    # plan only, no code changes
python main.py --issue URL --no-pr      # fix but skip PR
python main.py --issue URL --verbose    # detailed output
```

## Resume Bullet Points (for your CV/LinkedIn)

- Built **DevAgent** — an autonomous SWE agent using LangGraph + Mistral API that ingests GitHub issue URLs and opens tested pull requests with zero human intervention
- Engineered a 6-node LangGraph StateGraph (Plan → Explore → Code → Test ↔ Debug → PR) with conditional retry routing and tool-calling loops
- Implemented reliable file editing via `str_replace_in_file` with automatic fallback to `write_file`, achieving 13s fix time on the local integration test
- Evaluated on SWE-bench Lite: `python scripts/eval_swebench.py --limit 50`