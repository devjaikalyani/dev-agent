"""
test_tools.py — Unit tests for filesystem tools.
Run: pytest tests/ -v
"""
import os
import tempfile
import pathlib
import pytest
from unittest.mock import patch

# Add parent to path for imports
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

# Set dummy env vars so config imports without error
os.environ.setdefault("CEREBRAS_API_KEY", "test_key")
os.environ.setdefault("GITHUB_TOKEN", "test_token")

from tools.filesystem import (
    read_file, write_file, str_replace_in_file,
    list_directory, search_code, run_bash,
)


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temporary repo directory with some files."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello():\n    return 'world'\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text(
        "from src.main import hello\n\ndef test_hello():\n    assert hello() == 'world'\n"
    )
    (tmp_path / "README.md").write_text("# Test Repo\n")
    return str(tmp_path)


class TestReadFile:
    def test_reads_existing_file(self, tmp_repo):
        result = read_file.invoke({"repo_root": tmp_repo, "path": "src/main.py"})
        assert "def hello" in result

    def test_missing_file_returns_error(self, tmp_repo):
        result = read_file.invoke({"repo_root": tmp_repo, "path": "nonexistent.py"})
        assert "ERROR" in result

    def test_path_traversal_blocked(self, tmp_repo):
        with pytest.raises(PermissionError):
            read_file.invoke({"repo_root": tmp_repo, "path": "../../etc/passwd"})


class TestWriteFile:
    def test_creates_new_file(self, tmp_repo):
        result = write_file.invoke({
            "repo_root": tmp_repo,
            "path": "src/utils.py",
            "content": "def add(a, b):\n    return a + b\n",
        })
        assert "Successfully wrote" in result
        assert (pathlib.Path(tmp_repo) / "src" / "utils.py").exists()

    def test_creates_nested_dirs(self, tmp_repo):
        result = write_file.invoke({
            "repo_root": tmp_repo,
            "path": "deep/nested/file.py",
            "content": "x = 1\n",
        })
        assert "Successfully wrote" in result


class TestStrReplaceInFile:
    def test_successful_replace(self, tmp_repo):
        result = str_replace_in_file.invoke({
            "repo_root": tmp_repo,
            "path": "src/main.py",
            "old_str": "return 'world'",
            "new_str": "return 'hello world'",
        })
        assert "Replaced successfully" in result
        content = (pathlib.Path(tmp_repo) / "src" / "main.py").read_text()
        assert "hello world" in content

    def test_old_str_not_found(self, tmp_repo):
        result = str_replace_in_file.invoke({
            "repo_root": tmp_repo,
            "path": "src/main.py",
            "old_str": "this string does not exist",
            "new_str": "replacement",
        })
        assert "ERROR" in result

    def test_duplicate_old_str_blocked(self, tmp_repo):
        # Write a file with duplicate string
        write_file.invoke({
            "repo_root": tmp_repo,
            "path": "src/dup.py",
            "content": "x = 1\nx = 1\n",
        })
        result = str_replace_in_file.invoke({
            "repo_root": tmp_repo,
            "path": "src/dup.py",
            "old_str": "x = 1",
            "new_str": "x = 2",
        })
        assert "ERROR" in result and "2 times" in result


class TestListDirectory:
    def test_lists_files(self, tmp_repo):
        result = list_directory.invoke({"repo_root": tmp_repo, "path": "."})
        assert "src" in result
        assert "tests" in result

    def test_depth_limit(self, tmp_repo):
        result = list_directory.invoke({"repo_root": tmp_repo, "path": ".", "max_depth": 1})
        # At depth 1 we see dirs but not contents
        assert "src" in result


class TestRunBash:
    def test_basic_command(self, tmp_repo):
        result = run_bash.invoke({"repo_root": tmp_repo, "command": "echo hello"})
        assert "hello" in result

    def test_captures_exit_code(self, tmp_repo):
        result = run_bash.invoke({"repo_root": tmp_repo, "command": "exit 1"})
        assert "exit code: 1" in result

    def test_blocks_dangerous_commands(self, tmp_repo):
        result = run_bash.invoke({"repo_root": tmp_repo, "command": "rm -rf /"})
        assert "Blocked" in result


class TestSearchCode:
    def test_finds_pattern(self, tmp_repo):
        result = search_code.invoke({
            "repo_root": tmp_repo,
            "pattern": "def hello",
        })
        assert "def hello" in result

    def test_no_match_returns_message(self, tmp_repo):
        result = search_code.invoke({
            "repo_root": tmp_repo,
            "pattern": "xyzzy_pattern_that_cannot_exist",
        })
        assert "no matches" in result.lower() or result == "(no matches found)"
