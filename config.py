"""Load .env and expose config constants."""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).parent / ".env"
load_dotenv(_env_path)
print(f"Loading .env from: {_env_path}")

# ── Mistral API ───────────────────────────────────────────────────────────────
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")

# Free-tier models with tool calling support:
#   mistral-small-latest       ← best free option (fast, great tool use)
#   codestral-latest           ← coding specialist (may need separate key)
#   open-mistral-nemo          ← 12B, very fast, free
MISTRAL_MODEL   = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")

print(f"MISTRAL_API_KEY set: {bool(MISTRAL_API_KEY)}")
print(f"Calling Mistral API with model: {MISTRAL_MODEL}")

MAX_TOKENS      = int(os.environ.get("MAX_TOKENS", "4096"))

# ── GitHub ────────────────────────────────────────────────────────────────────
GITHUB_TOKEN    = os.environ.get("GITHUB_TOKEN", "")

# ── Agent behaviour ───────────────────────────────────────────────────────────
MAX_RETRIES     = int(os.environ.get("MAX_RETRIES", "5"))
SANDBOX_TIMEOUT = int(os.environ.get("SANDBOX_TIMEOUT", "120"))
CLONE_DIR       = Path(os.environ.get("CLONE_DIR", "/tmp/devagent_repos"))
TOOL_OUTPUT_LIMIT = 4_000
DEBUG           = os.environ.get("DEVAGENT_DEBUG", "0") == "1"

CLONE_DIR.mkdir(parents=True, exist_ok=True)

# Add this to config.py
MISTRAL_RATE_LIMIT_DELAY = int(os.environ.get("MISTRAL_RATE_LIMIT_DELAY", "2"))  # seconds
MISTRAL_MAX_RETRIES = int(os.environ.get("MISTRAL_MAX_RETRIES", "5"))

def validate() -> None:
    missing = []
    if not MISTRAL_API_KEY: missing.append("MISTRAL_API_KEY")
    if not GITHUB_TOKEN:    missing.append("GITHUB_TOKEN")
    if missing:
        raise EnvironmentError(
            f"Missing env vars: {', '.join(missing)}\n"
            "Copy .env.example → .env and fill in your keys.\n"
            "Get MISTRAL_API_KEY free at: https://console.mistral.ai"
        )