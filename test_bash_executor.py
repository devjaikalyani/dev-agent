"""Tests for bash executor (local fallback mode)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tools.bash_executor import run_in_sandbox, format_result

def test_simple_python(tmp_path):
    result = run_in_sandbox("python3 -c \"print(\'hello\')\"", str(tmp_path))
    assert result["exit_code"] == 0
    assert "hello" in result["stdout"]

def test_blocked_pattern(tmp_path):
    result = run_in_sandbox("rm -rf /", str(tmp_path))
    assert result["exit_code"] == 1
    assert "BLOCKED" in result["stderr"]

def test_format_result_pass():
    r = {"stdout":"all good","stderr":"","exit_code":0,"timed_out":False}
    fmt = format_result(r)
    assert "PASSED" in fmt

def test_format_result_fail():
    r = {"stdout":"","stderr":"error","exit_code":1,"timed_out":False}
    fmt = format_result(r)
    assert "FAILED" in fmt
