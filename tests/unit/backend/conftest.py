"""
tests/unit/backend/conftest.py

Backend test harness. Provides an in-memory SQLite database that stands in for
Postgres, an httpx client wired to the FastAPI app with get_db overridden, and
auto-patched Celery .delay() calls so no broker/redis is touched.

The models use sqlalchemy.dialects.postgresql.UUID; two small shims (registered
here, not in production code) teach SQLite how to store/bind those values.
"""
import os
import sqlite3
import uuid

# Production database.py builds its engine at import time from DATABASE_URL and
# raises if it is unset. Point it at a lazy (never-connected) async-pg URL so the
# import succeeds; real queries go through the SQLite override below.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test_rsentry")

import pytest
import pytest_asyncio
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from httpx import AsyncClient, ASGITransport


# --- SQLite compatibility shims for the postgres UUID column type -----------
@compiles(UUID, "sqlite")
def _compile_uuid_sqlite(element, compiler, **kw):  # noqa: ARG001
    return "CHAR(32)"


# sqlite3 cannot bind a uuid.UUID object directly — store as 32-char hex.
sqlite3.register_adapter(uuid.UUID, lambda u: u.hex)


# --- App + DB imports (safe now that DATABASE_URL is set) -------------------
from backend.main import app                       # noqa: E402
from backend.models.database import Base, get_db   # noqa: E402
import backend.models.schemas  # noqa: E402,F401  (registers ORM tables on Base)

# Names of every Celery task dispatched from the routers — patched per test.
_TASK_PATHS = [
    "backend.routers.events.push_event_ws",
    "backend.routers.events.push_alert_ws",
    "backend.routers.events.update_host_risk",
    "backend.routers.events.analyze_event_ai",
    "backend.routers.events.auto_ack_containment",
    "backend.routers.events.publish_markov_analysis",
]


@pytest_asyncio.fixture
async def db_engine():
    """Fresh in-memory SQLite engine per test. StaticPool keeps a single shared
    connection so the seeding session and the request handler see the same DB."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """A session for tests to seed/inspect data directly."""
    SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with SessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_engine):
    """httpx client bound to the ASGI app, with get_db overridden onto SQLite."""
    SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_get_db():
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def mock_tasks(mocker):
    """Patch every router-dispatched Celery task's .delay so nothing hits a broker.
    Returns a dict {task_name: mock} for assertions."""
    mocks = {}
    for path in _TASK_PATHS:
        name = path.rsplit(".", 1)[1]
        mocks[name] = mocker.patch(path + ".delay")
    return mocks
