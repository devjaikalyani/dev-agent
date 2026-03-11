"""
test_graph_routing.py — Tests for LangGraph conditional routing logic.
"""
import sys
import os
import pathlib
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
os.environ.setdefault("CEREBRAS_API_KEY", "test_key")
os.environ.setdefault("GITHUB_TOKEN", "test_token")

from agent.graph import route_after_test


class TestRouteAfterTest:
    def test_routes_to_open_pr_on_pass(self):
        state = {"test_passed": True, "retry_count": 0}
        assert route_after_test(state) == "open_pr"

    def test_routes_to_debug_on_fail_with_retries_remaining(self):
        state = {"test_passed": False, "retry_count": 2}
        assert route_after_test(state) == "debug"

    def test_routes_to_failed_on_max_retries(self):
        state = {"test_passed": False, "retry_count": 5}
        assert route_after_test(state) == "failed"

    def test_routes_to_debug_on_first_failure(self):
        state = {"test_passed": False, "retry_count": 0}
        assert route_after_test(state) == "debug"

    def test_routes_to_failed_just_at_limit(self):
        from config import cfg
        state = {"test_passed": False, "retry_count": cfg.MAX_RETRIES}
        assert route_after_test(state) == "failed"
