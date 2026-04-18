"""Tests for the chained / signed audit logger (framework §8)."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from vpcsc_mcp.tools.observability import (
    AuditChainError,
    AuditLogger,
    _canonical_dumps,
    audit_log,
    reset_audit_logger_for_tests,
    set_principal,
)


@pytest.fixture
def audit_dir(tmp_path):
    return tmp_path / "audit"


@pytest.fixture
def audit_logger(audit_dir, tmp_path):
    key = b"test-key-32-bytes-long-for-hmac-aaa"
    logger_ = AuditLogger(
        directory=audit_dir, dlq_path=tmp_path / "dlq.jsonl", key=key,
    )
    return logger_


def test_append_produces_chain(audit_logger):
    a = audit_logger.append({"event": "tool_call", "tool": "a"})
    b = audit_logger.append({"event": "tool_call", "tool": "b"})
    c = audit_logger.append({"event": "tool_call", "tool": "c"})

    assert a["prev_hash"] == AuditLogger.GENESIS
    assert a["chain_hash"] != AuditLogger.GENESIS
    assert b["prev_hash"] == a["chain_hash"]
    assert c["prev_hash"] == b["chain_hash"]
    assert a["seq"] == 0
    assert b["seq"] == 1
    assert c["seq"] == 2


def test_append_is_written_to_disk(audit_logger, audit_dir):
    audit_logger.append({"event": "tool_call", "tool": "x"})
    audit_files = list(audit_dir.glob("audit-*.jsonl"))
    assert len(audit_files) == 1
    content = audit_files[0].read_text().strip().splitlines()
    assert len(content) == 1
    entry = json.loads(content[0])
    assert entry["tool"] == "x"
    assert "chain_hash" in entry


def test_chain_verify_detects_tampering(audit_dir, tmp_path):
    key = b"key-aaa"
    first = AuditLogger(directory=audit_dir, key=key)
    first.append({"event": "tool_call", "tool": "a"})
    first.append({"event": "tool_call", "tool": "b"})

    # Tamper with the first entry's tool field
    log_file = next(audit_dir.glob("audit-*.jsonl"))
    lines = log_file.read_text().splitlines()
    entry_a = json.loads(lines[0])
    entry_a["tool"] = "tampered"
    lines[0] = json.dumps(entry_a)
    log_file.write_text("\n".join(lines) + "\n")

    with pytest.raises(AuditChainError):
        AuditLogger(directory=audit_dir, key=key)


def test_export_signed_is_verifiable(audit_logger):
    audit_logger.append({"event": "tool_call", "tool": "a"})
    audit_logger.append({"event": "tool_call", "tool": "b"})
    bundle = audit_logger.export_signed()

    # Recompute the signature to verify
    canonical = _canonical_dumps(bundle["payload"])
    expected = hmac.new(
        b"test-key-32-bytes-long-for-hmac-aaa",
        canonical.encode(),
        hashlib.sha256,
    ).hexdigest()
    assert bundle["signature"] == expected
    assert bundle["algorithm"] == "HMAC-SHA256"
    assert bundle["payload"]["count"] == 2
    assert bundle["payload"]["chain_head"] == audit_logger._last_hash  # noqa: SLF001


def test_daily_manifest_is_signed(audit_logger, audit_dir):
    audit_logger.append({"event": "tool_call", "tool": "a"})
    manifest = audit_logger.write_daily_manifest()
    assert manifest is not None
    assert "signature" in manifest
    assert manifest["algorithm"] == "HMAC-SHA256"
    assert manifest["entry_count"] == 1
    assert list(audit_dir.glob("manifest-*.json"))


def test_write_failure_goes_to_dlq(tmp_path, monkeypatch):
    dlq = tmp_path / "dlq.jsonl"
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    logger_ = AuditLogger(
        directory=audit_dir, dlq_path=dlq, key=b"k",
    )
    # Simulate a disk write failure by patching the write path
    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(logger_, "_write_to_disk", boom)
    logger_.append({"event": "tool_call", "tool": "doomed"})
    assert dlq.exists()
    assert "doomed" in dlq.read_text()
    assert logger_.stats()["dlq_entries"] == 1


def test_dlq_replay_drains_entries(tmp_path, monkeypatch):
    dlq = tmp_path / "dlq.jsonl"
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    logger_ = AuditLogger(directory=audit_dir, dlq_path=dlq, key=b"k")

    # Force one entry to the DLQ
    calls = {"n": 0}
    original_write = logger_._write_to_disk  # noqa: SLF001

    def fail_once(entry):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("transient")
        original_write(entry)

    monkeypatch.setattr(logger_, "_write_to_disk", fail_once)
    logger_.append({"event": "tool_call", "tool": "retry-me"})
    assert logger_.stats()["dlq_entries"] == 1

    # Now replay with a working writer
    monkeypatch.setattr(logger_, "_write_to_disk", original_write)
    drained = logger_.replay_dlq()
    assert drained == 1


def test_audit_log_records_principal(tmp_path, monkeypatch):
    monkeypatch.setenv("VPCSC_MCP_AUDIT_DIR", str(tmp_path))
    reset_audit_logger_for_tests(None)
    try:
        tok = set_principal("agent-alice")
        try:
            entry = audit_log(tool="test", args=["x"])
        finally:
            from vpcsc_mcp.tools.observability import reset_principal
            reset_principal(tok)
        assert entry["principal"] == "agent-alice"
    finally:
        reset_audit_logger_for_tests(None)
