"""
test_github_client.py — Tests for GitHub client (uses mocks — no real API calls).
"""
import sys
import os
import pathlib
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
os.environ.setdefault("CEREBRAS_API_KEY", "test_key")
os.environ.setdefault("GITHUB_TOKEN", "test_token")

from tools.github_client import parse_issue_url


class TestParseIssueUrl:
    def test_standard_url(self):
        owner, repo, number = parse_issue_url(
            "https://github.com/openai/openai-python/issues/123"
        )
        assert owner == "openai"
        assert repo == "openai-python"
        assert number == 123

    def test_url_with_anchor(self):
        owner, repo, number = parse_issue_url(
            "https://github.com/django/django/issues/456#issuecomment-789"
        )
        assert owner == "django"
        assert repo == "django"
        assert number == 456

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError):
            parse_issue_url("https://example.com/not-github")
