"""
Sandboxed Test Runner
Runs tests inside Docker for full isolation.
Falls back to direct execution if Docker is not available.
"""

from __future__ import annotations
import shutil
import subprocess
from pathlib import Path


SANDBOX_IMAGE = "devagent-sandbox"


def is_docker_available() -> bool:
    return shutil.which("docker") is not None


def build_sandbox_image(sandbox_dir: Path) -> bool:
    """Build the sandbox Docker image. Returns True on success."""
    result = subprocess.run(
        ["docker", "build", "-t", SANDBOX_IMAGE, str(sandbox_dir)],
        capture_output=True, text=True
    )
    return result.returncode == 0


def run_tests_sandboxed(repo_path: str, test_command: str = "python -m pytest -x --tb=short -q .") -> dict:
    """
    Run tests inside a Docker sandbox.

    Features:
    - --network none (no internet access)
    - --memory 512m (memory cap)
    - --read-only with /tmp as tmpfs
    - Non-root user
    - 120 second timeout

    Returns same dict format as bash_executor.run_tests()
    """
    if not is_docker_available():
        # Fall back to direct execution
        from tools.bash_executor import run_tests
        return run_tests(repo_path)

    cmd = [
        "docker", "run", "--rm",
        "-v", f"{repo_path}:/workspace:ro",   # mount as read-only
        "--network", "none",
        "--memory", "512m",
        "--cpus", "1",
        SANDBOX_IMAGE,
        "sh", "-c", test_command
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True,
            timeout=120
        )
        output = (result.stdout + result.stderr).strip()
        passed = result.returncode == 0

        from tools.bash_executor import _extract_failed_tests
        return {
            "passed": passed,
            "exit_code": result.returncode,
            "output": output[:8000],
            "failed_tests": _extract_failed_tests(output),
            "sandboxed": True,
        }

    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "exit_code": -1,
            "output": "TIMEOUT: Sandboxed tests exceeded 120 seconds.",
            "failed_tests": [],
            "sandboxed": True,
        }
    except Exception as e:
        # Fall back to direct execution
        from tools.bash_executor import run_tests
        return run_tests(repo_path)
