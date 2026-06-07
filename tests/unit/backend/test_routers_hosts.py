"""
tests/unit/backend/test_routers_hosts.py
Tests for backend/routers/hosts.py — list, get, risk summary, contain/release.
"""
from datetime import datetime, timezone

import pytest

from backend.models.schemas import Host, Event, Alert, Severity, EventType


async def _seed_host(session, host_id="HOSTH", contained=False, risk=0.0):
    session.add(Host(host_id=host_id, is_contained=contained, risk_score=risk))
    await session.commit()


@pytest.mark.asyncio
async def test_list_hosts_empty(client):
    r = await client.get("/api/hosts")
    assert r.status_code == 200 and r.json() == []


@pytest.mark.asyncio
async def test_list_and_filter_contained(client, db_session):
    await _seed_host(db_session, "H_FREE", contained=False)
    await _seed_host(db_session, "H_LOCKED", contained=True)
    all_hosts = (await client.get("/api/hosts")).json()
    assert len(all_hosts) == 2
    locked = (await client.get("/api/hosts", params={"contained": True})).json()
    assert len(locked) == 1 and locked[0]["host_id"] == "H_LOCKED"


@pytest.mark.asyncio
async def test_get_host_404(client):
    r = await client.get("/api/hosts/NOPE")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_risk_summary(client, db_session):
    await _seed_host(db_session, "HRISK", risk=42.0)
    # add a critical event + unacked alert
    ev = Event(host_id="HRISK", timestamp=datetime.now(timezone.utc),
               event_type=EventType.CANARY_TOUCHED, severity=Severity.CRITICAL,
               file_path="/tmp/a", process_name="p")
    db_session.add(ev)
    await db_session.flush()
    db_session.add(Alert(event_id=ev.id, host_id="HRISK", severity=Severity.CRITICAL))
    await db_session.commit()

    r = await client.get("/api/hosts/HRISK/risk")
    assert r.status_code == 200
    body = r.json()
    assert body["risk_score"] == 42.0
    assert body["open_alerts"]["CRITICAL"] == 1
    assert body["alert_count"] == 1
    assert body["event_count"] == 1
    assert len(body["recent_critical_events"]) == 1


@pytest.mark.asyncio
async def test_risk_summary_404(client):
    r = await client.get("/api/hosts/GHOST/risk")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_contain_and_release(client, db_session):
    await _seed_host(db_session, "HTOGGLE", contained=False)
    c = await client.post("/api/hosts/HTOGGLE/contain")
    assert c.status_code == 200 and c.json()["status"] == "contained"
    got = (await client.get("/api/hosts/HTOGGLE")).json()
    assert got["is_contained"] is True

    rel = await client.delete("/api/hosts/HTOGGLE/contain")
    assert rel.status_code == 200 and rel.json()["status"] == "released"
    got2 = (await client.get("/api/hosts/HTOGGLE")).json()
    assert got2["is_contained"] is False


@pytest.mark.asyncio
async def test_contain_404(client):
    r = await client.post("/api/hosts/GHOST/contain")
    assert r.status_code == 404
