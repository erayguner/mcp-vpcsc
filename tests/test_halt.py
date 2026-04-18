"""Tests for the halt / kill-switch registry (framework §14)."""

from __future__ import annotations

import pytest

from vpcsc_mcp.tools.halt import HaltRegistry, check_halt, registry
from vpcsc_mcp.tools.observability import reset_principal, set_principal


@pytest.fixture(autouse=True)
def clear_halts():
    registry.clear_for_tests()
    yield
    registry.clear_for_tests()


def test_halt_global_matches_any_tool():
    registry.halt("global", "incident 42", "alice")
    assert check_halt(tool="gcloud.access-context-manager") is not None
    assert check_halt(tool="gcloud.services") is not None


def test_halt_by_principal_scopes_correctly():
    registry.halt("principal:agent-bob", "suspicious", "alice")
    tok = set_principal("agent-bob")
    try:
        assert check_halt(tool="gcloud.services") is not None
    finally:
        reset_principal(tok)

    tok = set_principal("agent-carol")
    try:
        assert check_halt(tool="gcloud.services") is None
    finally:
        reset_principal(tok)


def test_halt_by_tool():
    registry.halt("tool:gcloud.services", "outage drill", "alice")
    assert check_halt(tool="gcloud.services") is not None
    assert check_halt(tool="gcloud.access-context-manager") is None


def test_resume_removes_halt():
    registry.halt("global", "x", "alice")
    assert registry.resume("global", "alice") is True
    assert check_halt() is None


def test_resume_nonexistent_returns_false():
    assert registry.resume("global", "alice") is False


def test_list_halts_shape():
    registry.halt("global", "r", "a")
    halts = registry.list_halts()
    assert len(halts) == 1
    h = halts[0]
    assert set(h.keys()) == {"scope", "reason", "actor", "halted_at"}


def test_halt_requires_reason_and_scope():
    reg = HaltRegistry()
    with pytest.raises(ValueError):
        reg.halt("", "r", "a")
    with pytest.raises(ValueError):
        reg.halt("global", "", "a")
