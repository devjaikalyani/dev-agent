"""Tests for filesystem tools."""
import pathlib, tempfile, pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tools.filesystem import read_file, write_file, str_replace, create_file, search_code, find_files, list_dir

def test_write_and_read(tmp_path):
    p = tmp_path / "hello.txt"
    write_file(str(p), "hello world")
    assert read_file(str(p)) == "hello world"

def test_read_missing():
    result = read_file("/nonexistent/path.txt")
    assert "ERROR" in result

def test_str_replace(tmp_path):
    p = tmp_path / "code.py"
    p.write_text("def foo():\n    return 1\n")
    result = str_replace(str(p), "return 1", "return 42")
    assert "OK" in result
    assert "return 42" in p.read_text()

def test_str_replace_not_found(tmp_path):
    p = tmp_path / "code.py"
    p.write_text("def foo():\n    pass\n")
    result = str_replace(str(p), "NOTEXIST", "replacement")
    assert "ERROR" in result

def test_create_file(tmp_path):
    p = tmp_path / "new.py"
    result = create_file(str(p), "print('hi')")
    assert "OK" in result
    assert p.exists()

def test_create_file_exists(tmp_path):
    p = tmp_path / "exists.py"
    p.write_text("")
    result = create_file(str(p), "content")
    assert "ERROR" in result

def test_list_dir(tmp_path):
    (tmp_path / "a.py").write_text("")
    (tmp_path / "subdir").mkdir()
    result = list_dir(str(tmp_path))
    assert "a.py" in result

def test_find_files(tmp_path):
    (tmp_path / "test_foo.py").write_text("")
    (tmp_path / "bar.py").write_text("")
    result = find_files("test_*.py", str(tmp_path))
    assert "test_foo.py" in result
    assert "bar.py" not in result

def test_truncation(tmp_path):
    p = tmp_path / "big.txt"
    p.write_text("x" * 20000)
    result = read_file(str(p), max_chars=100)
    assert "TRUNCATED" in result
    assert len(result) < 500
