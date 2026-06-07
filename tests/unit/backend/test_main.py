"""
tests/unit/backend/test_main.py
Tests for backend/main.py — health/root endpoints and the AI health-check
request cap (HealthCheckRequest.events max_length=200).
"""
import pytest


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_root(client):
    r = await client.get("/")
    assert r.status_code == 200
    assert "R-Sentry" in r.json()["message"]


@pytest.mark.asyncio
async def test_ai_health_accepts_within_cap(client, mocker):
    mocker.patch("backend.workers.tasks.analyze_health_ai.delay")
    r = await client.post("/api/ai/health", json={"events": [{"e": 1}] * 10})
    assert r.status_code == 200
    assert r.json()["status"] == "analysis_queued"


@pytest.mark.asyncio
async def test_ai_health_rejects_over_cap(client):
    # 201 events exceeds Field(max_length=200) → 422 before any task dispatch
    r = await client.post("/api/ai/health", json={"events": [{"e": 1}] * 201})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_ai_health_empty_default(client, mocker):
    mocker.patch("backend.workers.tasks.analyze_health_ai.delay")
    r = await client.post("/api/ai/health", json={})
    assert r.status_code == 200
