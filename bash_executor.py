"""
Safe bash execution.
Uses Docker if available; falls back to restricted local subprocess.
"""
from __future__ import annotations
import os
import subprocess
import pathlib

DOCKER_IMAGE     = "python:3.11-slim"
SAFE_CMDS        = {"pytest","python","python3","pip","npm","node","go","cargo","make","ruby","bundle"}
BLOCKED_PATTERNS = ["rm -rf /", "dd if=", "> /dev/", "mkfs", ":(){"]


def _docker_ok() -> bool:
    try:
        r = subprocess.run(["docker","info"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def run_in_sandbox(command: str, repo_path: str, timeout: int | None = None) -> dict:
    if timeout is None:
        timeout = int(os.environ.get("SANDBOX_TIMEOUT", "120"))
    for pat in BLOCKED_PATTERNS:
        if pat in command:
            return {"stdout":"","stderr":f"BLOCKED: {pat}","exit_code":1,"timed_out":False}
    if _docker_ok():
        return _run_docker(command, repo_path, timeout)
    return _run_local(command, repo_path, timeout)


def _run_docker(command: str, repo_path: str, timeout: int) -> dict:
    abs_repo = str(pathlib.Path(repo_path).resolve())
    cmd = [
        "docker","run","--rm","--network=none","--memory=512m","--cpus=1.0",
        "-v", f"{abs_repo}:/workspace", "-w","/workspace",
        DOCKER_IMAGE, "bash","-c",
        f"pip install -r requirements.txt -q 2>/dev/null || true; {command}",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"stdout":r.stdout[:6000],"stderr":r.stderr[:3000],"exit_code":r.returncode,"timed_out":False}
    except subprocess.TimeoutExpired:
        return {"stdout":"","stderr":"TIMED OUT","exit_code":1,"timed_out":True}
    except Exception as e:
        return {"stdout":"","stderr":str(e),"exit_code":1,"timed_out":False}


def _run_local(command: str, repo_path: str, timeout: int) -> dict:
    first = command.strip().split()[0] if command.strip() else ""
    if first not in SAFE_CMDS:
        return {"stdout":"","stderr":f"LOCAL: '{first}' not in safe list {SAFE_CMDS}","exit_code":1,"timed_out":False}
    try:
        r = subprocess.run(command, shell=True, cwd=repo_path, capture_output=True, text=True, timeout=timeout)
        return {"stdout":r.stdout[:6000],"stderr":r.stderr[:3000],"exit_code":r.returncode,"timed_out":False}
    except subprocess.TimeoutExpired:
        return {"stdout":"","stderr":"TIMED OUT","exit_code":1,"timed_out":True}
    except Exception as e:
        return {"stdout":"","stderr":str(e),"exit_code":1,"timed_out":False}


def format_result(r: dict) -> str:
    parts = []
    if r["timed_out"]:
        parts.append("TIMED OUT")
    else:
        parts.append("PASSED" if r["exit_code"] == 0 else f"FAILED (exit {r['exit_code']})")
    if r["stdout"]:
        parts.append("-- stdout --\n" + r["stdout"])
    if r["stderr"]:
        parts.append("-- stderr --\n" + r["stderr"])
    return "\n".join(parts)
