"""
tests/unit/backend/test_tasks.py
Tests for backend/workers/tasks.py — _env() parsing (env precedence, inline
comment stripping, quote stripping), _run() loop helper, and WS push payloads.
"""
import json

import pytest

from backend.workers import tasks


# --- _env() -----------------------------------------------------------------

class TestEnv:
    def test_os_env_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("RS_TEST_KEY", "from_os")
        assert tasks._env("RS_TEST_KEY") == "from_os"

    def test_reads_from_dotenv_file(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text("RS_FILE_KEY=from_file\n")
        monkeypatch.setattr(tasks, "_ENV_FILE", env)
        monkeypatch.delenv("RS_FILE_KEY", raising=False)
        assert tasks._env("RS_FILE_KEY") == "from_file"

    def test_strips_inline_comment(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text("CANARY_COUNT=15 # number of canaries\n")
        monkeypatch.setattr(tasks, "_ENV_FILE", env)
        monkeypatch.delenv("CANARY_COUNT", raising=False)
        assert tasks._env("CANARY_COUNT") == "15"

    def test_strips_quotes(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text('SECRET_KEY="abc123"\n')
        monkeypatch.setattr(tasks, "_ENV_FILE", env)
        monkeypatch.delenv("SECRET_KEY", raising=False)
        assert tasks._env("SECRET_KEY") == "abc123"

    def test_single_quotes_stripped(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text("TOKEN='xyz'\n")
        monkeypatch.setattr(tasks, "_ENV_FILE", env)
        monkeypatch.delenv("TOKEN", raising=False)
        assert tasks._env("TOKEN") == "xyz"

    def test_skips_commented_line(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text("#DISABLED=should_not_read\n")
        monkeypatch.setattr(tasks, "_ENV_FILE", env)
        monkeypatch.delenv("DISABLED", raising=False)
        assert tasks._env("DISABLED", "fallback") == "fallback"

    def test_default_when_missing(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text("OTHER=1\n")
        monkeypatch.setattr(tasks, "_ENV_FILE", env)
        monkeypatch.delenv("ABSENT", raising=False)
        assert tasks._env("ABSENT", "dflt") == "dflt"

    def test_url_with_hash_not_truncated(self, tmp_path, monkeypatch):
        # only " #" (space-hash) starts an inline comment; '#' inside a value stays
        env = tmp_path / ".env"
        env.write_text("DATABASE_URL=postgresql://u:p#ass@localhost/db\n")
        monkeypatch.setattr(tasks, "_ENV_FILE", env)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert tasks._env("DATABASE_URL") == "postgresql://u:p#ass@localhost/db"


# --- _run() -----------------------------------------------------------------

class TestRun:
    def test_runs_coroutine_returns_value(self):
        async def coro():
            return 42
        assert tasks._run(coro()) == 21 * 2

    def test_propagates_exception(self):
        async def boom():
            raise ValueError("nope")
        with pytest.raises(ValueError, match="nope"):
            tasks._run(boom())


# --- WS push tasks ----------------------------------------------------------

class TestPushTasks:
    def test_push_alert_ws_payload(self, mocker):
        fake_r = mocker.MagicMock()
        mocker.patch.object(tasks, "_redis", return_value=fake_r)
        tasks.push_alert_ws("aid", "H1", "CRITICAL", "CANARY_TOUCHED")
        channel, raw = fake_r.publish.call_args[0]
        assert channel == "rsentry:alerts"
        body = json.loads(raw)
        assert body["type"] == "new_alert"
        assert body["alert_id"] == "aid"
        assert body["severity"] == "CRITICAL"

    def test_push_event_ws_payload(self, mocker):
        fake_r = mocker.MagicMock()
        mocker.patch.object(tasks, "_redis", return_value=fake_r)
        tasks.push_event_ws("eid", "H1", "ENTROPY_SPIKE", "HIGH",
                            "/tmp/x", 4.2, False, "proc", {"k": "v"})
        channel, raw = fake_r.publish.call_args[0]
        assert channel == "rsentry:events"
        body = json.loads(raw)
        assert body["type"] == "new_event"
        assert body["event_id"] == "eid"
        assert body["entropy_delta"] == 4.2
        assert body["details"] == {"k": "v"}
