"""
tests/unit/test_sre_agent.py

Unit tests for the SRE-GPT Agent:
  - compute_fingerprint()
  - ingest() — new incident creation
  - ingest() — 60-second dedup window
  - _extract_prometheus(), _extract_pagerduty()
  - _normalise_severity() alias mapping
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from opsmindai.agents.sre_gpt.alert_ingester import (
    _extract_grafana,
    _extract_pagerduty,
    _extract_prometheus,
    _normalise_severity,
    compute_fingerprint,
    detect_source,
    ingest,
)
from opsmindai.schemas.incidents import (
    AlertPayload,
    AlertSource,
    IncidentSeverity,
    NormalisedAlert,
)


# ── compute_fingerprint ───────────────────────────────────────────────────────

class TestComputeFingerprint:

    def test_deterministic(self):
        fp1 = compute_fingerprint("svc", "AlertName", {"env": "prod"})
        fp2 = compute_fingerprint("svc", "AlertName", {"env": "prod"})
        assert fp1 == fp2

    def test_different_services_differ(self):
        fp1 = compute_fingerprint("svc-a", "Alert", {})
        fp2 = compute_fingerprint("svc-b", "Alert", {})
        assert fp1 != fp2

    def test_different_alert_names_differ(self):
        fp1 = compute_fingerprint("svc", "AlertA", {})
        fp2 = compute_fingerprint("svc", "AlertB", {})
        assert fp1 != fp2

    def test_label_order_ignored(self):
        fp1 = compute_fingerprint("svc", "Alert", {"a": "1", "b": "2"})
        fp2 = compute_fingerprint("svc", "Alert", {"b": "2", "a": "1"})
        assert fp1 == fp2

    def test_returns_64_char_hex(self):
        fp = compute_fingerprint("svc", "Alert", {})
        assert len(fp) == 64
        int(fp, 16)   # raises if not hex


# ── _extract_prometheus ───────────────────────────────────────────────────────

class TestExtractPrometheus:

    def test_extracts_first_alert(self):
        raw = {
            "alerts": [
                {
                    "labels": {
                        "alertname": "HighCPU",
                        "job": "api-service",
                        "severity": "high",
                    },
                    "annotations": {"summary": "CPU usage high"},
                    "status": "firing",
                }
            ]
        }
        result = _extract_prometheus(raw)
        assert result["alert_name"] == "HighCPU"
        assert result["service"] == "api-service"
        assert result["severity"] == "high"

    def test_empty_alerts_returns_empty(self):
        result = _extract_prometheus({"alerts": []})
        assert result == {}

    def test_missing_severity_defaults(self):
        raw = {"alerts": [{"labels": {"alertname": "TestAlert", "job": "svc"}, "annotations": {}}]}
        result = _extract_prometheus(raw)
        assert result["severity"] == "medium"

    def test_service_falls_back_to_job(self):
        raw = {
            "alerts": [{"labels": {"alertname": "A", "job": "my-svc"}, "annotations": {}}]
        }
        result = _extract_prometheus(raw)
        assert result["service"] == "my-svc"


# ── _extract_pagerduty ────────────────────────────────────────────────────────

class TestExtractPagerduty:

    def test_extracts_from_messages_format(self):
        raw = {
            "messages": [
                {
                    "event": {
                        "data": {
                            "title": "DB Connection Pool Exhausted",
                            "severity": "critical",
                            "service": {"summary": "database-service"},
                            "summary": "Connection pool at 100%",
                        }
                    }
                }
            ]
        }
        result = _extract_pagerduty(raw)
        assert result["alert_name"] == "DB Connection Pool Exhausted"
        assert result["service"] == "database-service"
        assert result["severity"] == "critical"

    def test_extracts_from_direct_event_format(self):
        raw = {
            "event": {
                "data": {
                    "title": "Memory Leak",
                    "severity": "high",
                    "custom_details": {"service": "cache-service"},
                    "summary": "Memory usage increasing",
                }
            }
        }
        result = _extract_pagerduty(raw)
        assert result["alert_name"] == "Memory Leak"
        assert result["service"] == "cache-service"


# ── _extract_grafana ──────────────────────────────────────────────────────────

class TestExtractGrafana:

    def test_extracts_from_alerts_array(self):
        raw = {
            "alerts": [
                {
                    "labels": {
                        "alertname": "DiskFull",
                        "service": "storage-service",
                        "severity": "critical",
                    },
                    "annotations": {},
                }
            ]
        }
        result = _extract_grafana(raw)
        assert result["alert_name"] == "DiskFull"
        assert result["service"] == "storage-service"
        assert result["severity"] == "critical"

    def test_extracts_from_common_labels_when_no_alerts(self):
        raw = {
            "title": "FallbackAlert",
            "alerts": [],
            "commonLabels": {"service": "fallback-svc", "severity": "medium"},
        }
        result = _extract_grafana(raw)
        assert result["alert_name"] == "FallbackAlert"
        assert result["service"] == "fallback-svc"


# ── _normalise_severity ───────────────────────────────────────────────────────

class TestNormaliseSeverity:

    @pytest.mark.parametrize("raw,expected", [
        ("critical",  IncidentSeverity.CRITICAL),
        ("high",      IncidentSeverity.HIGH),
        ("medium",    IncidentSeverity.MEDIUM),
        ("low",       IncidentSeverity.LOW),
        ("p1",        IncidentSeverity.CRITICAL),
        ("p2",        IncidentSeverity.HIGH),
        ("p3",        IncidentSeverity.MEDIUM),
        ("p4",        IncidentSeverity.LOW),
        ("warning",   IncidentSeverity.MEDIUM),
        ("warn",      IncidentSeverity.MEDIUM),
        ("error",     IncidentSeverity.HIGH),
        ("fatal",     IncidentSeverity.CRITICAL),
        ("info",      IncidentSeverity.LOW),
        ("CRITICAL",  IncidentSeverity.CRITICAL),
        ("unknown",   IncidentSeverity.MEDIUM),   # falls back to medium
        ("",          IncidentSeverity.MEDIUM),
    ])
    def test_alias_mapping(self, raw, expected):
        assert _normalise_severity(raw) == expected


# ── detect_source ─────────────────────────────────────────────────────────────

class TestDetectSource:

    def test_pagerduty_messages_format(self):
        raw = {"messages": [{"event": {"event_type": "incident.trigger"}}]}
        assert detect_source(raw) == AlertSource.PAGERDUTY

    def test_grafana_common_labels(self):
        raw = {"commonLabels": {"service": "svc"}, "alerts": []}
        assert detect_source(raw) == AlertSource.GRAFANA

    def test_prometheus_alerts_array(self):
        raw = {"alerts": [{"labels": {}}]}
        assert detect_source(raw) == AlertSource.PROMETHEUS

    def test_empty_defaults_to_prometheus(self):
        assert detect_source({}) == AlertSource.PROMETHEUS


# ── ingest() ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestIngest:

    async def test_new_alert_returns_normalised_alert_not_duplicate(
        self, mock_redis, sample_alert_payload
    ):
        alert, is_dup = await ingest(sample_alert_payload, mock_redis)

        assert isinstance(alert, NormalisedAlert)
        assert is_dup is False
        assert alert.service == "payment-service"
        assert alert.alert_name == "HighErrorRate"
        assert alert.incident_id.startswith("inc_")

    async def test_new_alert_stored_in_redis(self, mock_redis, sample_alert_payload):
        alert, _ = await ingest(sample_alert_payload, mock_redis)

        dedup_key = f"incident:dedup:{alert.fingerprint}"
        stored_id = await mock_redis.get(dedup_key)
        assert stored_id == alert.incident_id

    async def test_duplicate_suppressed_within_60s(self, mock_redis, sample_alert_payload):
        # First ingest
        alert1, is_dup1 = await ingest(sample_alert_payload, mock_redis)
        assert is_dup1 is False

        # Second ingest with same payload — Redis still has the dedup key
        alert2, is_dup2 = await ingest(sample_alert_payload, mock_redis)
        assert is_dup2 is True
        assert alert2.incident_id == alert1.incident_id

    async def test_severity_normalised_from_raw_payload(self, mock_redis):
        payload = AlertPayload(
            source=AlertSource.PROMETHEUS,
            service="svc",
            alert_name="Alert",
            severity=IncidentSeverity.MEDIUM,
            labels={},
            annotations={},
            raw_payload={
                "alerts": [
                    {
                        "labels": {"alertname": "Alert", "job": "svc", "severity": "p1"},
                        "annotations": {},
                    }
                ]
            },
        )
        alert, _ = await ingest(payload, mock_redis)
        assert alert.severity == IncidentSeverity.CRITICAL   # p1 → critical

    async def test_different_services_not_deduplicated(
        self, mock_redis, sample_alert_payload
    ):
        payload2 = AlertPayload(
            source=AlertSource.PROMETHEUS,
            service="auth-service",   # different service
            alert_name="HighErrorRate",
            severity=IncidentSeverity.CRITICAL,
            labels={"alertname": "HighErrorRate", "job": "auth-service"},
            annotations={},
            raw_payload={},
        )
        alert1, dup1 = await ingest(sample_alert_payload, mock_redis)
        alert2, dup2 = await ingest(payload2, mock_redis)

        assert dup1 is False
        assert dup2 is False
        assert alert1.incident_id != alert2.incident_id
