"""Tests for the observability module — caching, rate limiting, audit logging, and metrics."""

import json
import logging
import time

import pytest

from vpcsc_mcp.tools.observability import (
    GcloudCache,
    RateLimiter,
    ToolMetrics,
    audit_log,
)

# ─── GcloudCache Tests ───────────────────────────────────────────────────


class TestGcloudCache:
    def test_cache_miss_returns_none(self):
        c = GcloudCache(default_ttl=60)
        assert c.get(["access-context-manager", "perimeters", "list"]) is None

    def test_cache_hit_returns_value(self):
        c = GcloudCache(default_ttl=60)
        args = ["access-context-manager", "perimeters", "list"]
        value = {"result": [{"name": "p1"}]}
        c.set(args, None, value)
        assert c.get(args) == value

    def test_cache_respects_project(self):
        c = GcloudCache(default_ttl=60)
        args = ["services", "list", "--enabled"]
        value_a = {"result": [{"name": "a"}]}
        value_b = {"result": [{"name": "b"}]}
        c.set(args, "project-a", value_a)
        c.set(args, "project-b", value_b)
        assert c.get(args, "project-a") == value_a
        assert c.get(args, "project-b") == value_b

    def test_cache_expires_after_ttl(self):
        c = GcloudCache(default_ttl=0)  # instant expiry
        args = ["access-context-manager", "levels", "list"]
        c.set(args, None, {"result": []}, ttl=0)
        # TTL=0 means already expired on next get
        time.sleep(0.01)
        assert c.get(args) is None

    def test_cache_skips_non_cacheable_commands(self):
        c = GcloudCache(default_ttl=60)
        args = ["access-context-manager", "perimeters", "update", "my-perimeter"]
        c.set(args, None, {"result": "ok"})
        assert c.get(args) is None  # update is not cacheable

    def test_cache_skips_error_results(self):
        c = GcloudCache(default_ttl=60)
        args = ["access-context-manager", "perimeters", "list"]
        c.set(args, None, {"error": "some error"})
        assert c.get(args) is None  # errors should not be cached

    def test_cache_invalidate_all(self):
        c = GcloudCache(default_ttl=60)
        args1 = ["services", "list", "--enabled"]
        args2 = ["access-context-manager", "perimeters", "list"]
        c.set(args1, None, {"result": []})
        c.set(args2, None, {"result": []})
        c.invalidate()
        assert c.get(args1) is None
        assert c.get(args2) is None

    def test_cache_stats(self):
        c = GcloudCache(default_ttl=60)
        args = ["access-context-manager", "levels", "list"]
        c.set(args, None, {"result": []})
        c.get(args)  # hit
        c.get(["services", "list", "--enabled"])  # miss
        stats = c.stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["entries"] == 1


# ─── RateLimiter Tests ────────────────────────────────────────────────────


class TestRateLimiter:
    @pytest.fixture
    def limiter(self):
        return RateLimiter(max_concurrent=2)

    async def test_acquire_and_release(self, limiter):
        assert await limiter.acquire(timeout=1.0) is True
        assert limiter.stats["active"] == 1
        limiter.release()
        assert limiter.stats["active"] == 0

    async def test_acquire_respects_max(self, limiter):
        await limiter.acquire(timeout=1.0)
        await limiter.acquire(timeout=1.0)
        # Third should time out (max_concurrent=2)
        result = await limiter.acquire(timeout=0.05)
        assert result is False
        assert limiter.stats["rejected"] == 1
        limiter.release()
        limiter.release()

    async def test_stats_tracking(self, limiter):
        await limiter.acquire(timeout=1.0)
        limiter.release()
        await limiter.acquire(timeout=1.0)
        limiter.release()
        stats = limiter.stats
        assert stats["total_acquired"] == 2
        assert stats["active"] == 0


# ─── ToolMetrics Tests ────────────────────────────────────────────────────


class TestToolMetrics:
    def test_record_and_summary(self):
        m = ToolMetrics()
        m.record("gcloud.access-context-manager", 150.0, success=True)
        m.record("gcloud.access-context-manager", 200.0, success=True)
        m.record("gcloud.access-context-manager", 100.0, success=False)
        summary = m.summary
        tool = summary["gcloud.access-context-manager"]
        assert tool["calls"] == 3
        assert tool["errors"] == 1
        assert tool["avg_ms"] == pytest.approx(150.0, abs=0.1)

    def test_cache_hit_tracking(self):
        m = ToolMetrics()
        m.record("gcloud.services", 1.0, cached=True)
        m.record("gcloud.services", 200.0, cached=False)
        summary = m.summary
        assert summary["gcloud.services"]["cache_hits"] == 1

    def test_empty_summary(self):
        m = ToolMetrics()
        assert m.summary == {}


# ─── Audit Log Tests ─────────────────────────────────────────────────────


class TestAuditLog:
    def test_audit_log_emits_json(self, caplog):
        with caplog.at_level(logging.INFO, logger="vpcsc_mcp.audit"):
            audit_log(
                tool="gcloud.access-context-manager",
                args=["perimeters", "list"],
                duration_ms=123.4,
                success=True,
            )

        assert len(caplog.records) == 1
        entry = json.loads(caplog.records[0].message)
        assert entry["event"] == "tool_call"
        assert entry["tool"] == "gcloud.access-context-manager"
        assert entry["duration_ms"] == 123.4
        assert entry["success"] is True

    def test_audit_log_error_entry(self, caplog):
        with caplog.at_level(logging.INFO, logger="vpcsc_mcp.audit"):
            audit_log(
                tool="gcloud.services",
                args=["list"],
                success=False,
                error="Permission denied",
            )

        entry = json.loads(caplog.records[0].message)
        assert entry["success"] is False
        assert entry["error"] == "Permission denied"

    def test_audit_log_cached_entry(self, caplog):
        with caplog.at_level(logging.INFO, logger="vpcsc_mcp.audit"):
            audit_log(tool="gcloud.services", args=["list"], duration_ms=0.5, cached=True)

        entry = json.loads(caplog.records[0].message)
        assert entry["cached"] is True
