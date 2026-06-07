"""
tests/unit/backend/test_routers_events.py
Tests for backend/routers/events.py — ingest decision logic (alert creation,
Markov internal-event skip, auto-containment), plus list/get.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from backend.models.schemas import Host, Alert, Event, Severity, EventType


def _payload(**over):
    base = {
        "host_id": "HOSTX",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "ENTROPY_SPIKE",
        "severity": "HIGH",
        "pid": 1234,
        "process_name": "evil",
        "file_path": "/tmp/x.docx",
        "lineage_score": 0.0,
        "entropy_delta": 0.0,
        "canary_hit": False,
        "details": {},
    }
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_ingest_creates_event_and_alert_for_high(client, db_session):
    r = await client.post("/api/events", json=_payload(severity="HIGH"))
    assert r.status_code == 201
    alerts = (await db_session.execute(select(Alert))).scalars().all()
    assert len(alerts) == 1 and alerts[0].severity == Severity.HIGH


@pytest.mark.asyncio
async def test_ingest_low_severity_no_alert(client, db_session):
    r = await client.post("/api/events", json=_payload(severity="LOW", event_type="HEARTBEAT"))
    assert r.status_code == 201
    alerts = (await db_session.execute(select(Alert))).scalars().all()
    assert alerts == []


@pytest.mark.asyncio
async def test_ingest_markov_internal_skips_alert(client, db_session):
    # MARKOV_REPOSITION sub_type is an internal event — must NOT create an alert
    r = await client.post("/api/events", json=_payload(
        severity="CRITICAL", event_type="CANARY_TOUCHED",
        details={"sub_type": "MARKOV_REPOSITION"},
    ))
    assert r.status_code == 201
    alerts = (await db_session.execute(select(Alert))).scalars().all()
    assert alerts == []


@pytest.mark.asyncio
async def test_ingest_upserts_host(client, db_session):
    await client.post("/api/events", json=_payload(host_id="NEWHOST"))
    host = (await db_session.execute(
        select(Host).where(Host.host_id == "NEWHOST")
    )).scalar_one_or_none()
    assert host is not None


@pytest.mark.asyncio
async def test_auto_contain_on_canary_critical(client, db_session):
    await client.post("/api/events", json=_payload(
        severity="CRITICAL", event_type="CANARY_TOUCHED", canary_hit=True,
    ))
    host = (await db_session.execute(
        select(Host).where(Host.host_id == "HOSTX")
    )).scalar_one()
    assert host.is_contained is True


@pytest.mark.asyncio
async def test_no_auto_contain_for_high(client, db_session):
    await client.post("/api/events", json=_payload(severity="HIGH", canary_hit=True))
    host = (await db_session.execute(
        select(Host).where(Host.host_id == "HOSTX")
    )).scalar_one()
    assert host.is_contained is False


@pytest.mark.asyncio
async def test_auto_contain_on_high_lineage(client, db_session):
    # CRITICAL with no canary but lineage >= 70 → contain
    await client.post("/api/events", json=_payload(
        severity="CRITICAL", lineage_score=85.0, canary_hit=False,
    ))
    host = (await db_session.execute(
        select(Host).where(Host.host_id == "HOSTX")
    )).scalar_one()
    assert host.is_contained is True


@pytest.mark.asyncio
async def test_ingest_dispatches_alert_tasks(client, mock_tasks):
    await client.post("/api/events", json=_payload(severity="HIGH"))
    # an alert was created → ws push + risk update + AI analysis enqueued
    mock_tasks["push_alert_ws"].assert_called()
    mock_tasks["update_host_risk"].assert_called()
    mock_tasks["analyze_event_ai"].assert_called()


@pytest.mark.asyncio
async def test_ingest_validation_entropy_out_of_range(client):
    # entropy_delta > 8.0 violates the Field(le=8.0) constraint
    r = await client.post("/api/events", json=_payload(entropy_delta=99.0))
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_list_events_and_get(client, db_session):
    await client.post("/api/events", json=_payload(severity="HIGH"))
    listing = await client.get("/api/events")
    assert listing.status_code == 200
    events = listing.json()
    assert len(events) == 1
    eid = events[0]["id"]
    single = await client.get(f"/api/events/{eid}")
    assert single.status_code == 200
    assert single.json()["id"] == eid
