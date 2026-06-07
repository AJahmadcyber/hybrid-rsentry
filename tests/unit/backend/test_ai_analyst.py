"""
tests/unit/backend/test_ai_analyst.py
Tests for backend/services/ai_analyst.py — prompt building, JSON extraction,
provider fallback chain, and graceful failure envelopes. No network/redis.
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from openai import AuthenticationError, RateLimitError, APIConnectionError

from backend.services import ai_analyst


def _fake_response(content: str):
    """Mimic the OpenAI client response object shape used by _call_nvidia."""
    msg = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=msg)
    return SimpleNamespace(choices=[choice])


def _client_returning(content: str):
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_response(content)
    client._model = "test-model"
    return client


# --- build_prompt -----------------------------------------------------------

class TestBuildPrompt:
    def test_includes_core_fields(self):
        p = ai_analyst.build_prompt({
            "event_type": "CANARY_TOUCHED", "severity": "CRITICAL",
            "host_id": "H1", "file_path": "/tmp/x", "process_name": "evil",
            "pid": 99, "entropy_delta": 7.5, "lineage_score": 80.0, "canary_hit": True,
        })
        assert "CANARY_TOUCHED" in p
        assert "CRITICAL" in p
        assert "evil" in p
        assert "7.5" in p  # entropy delta formatted

    def test_markov_reposition_context_injected(self):
        p = ai_analyst.build_prompt({
            "event_type": "CANARY_TOUCHED", "severity": "CRITICAL",
            "details": {"sub_type": "MARKOV_REPOSITION"},
        })
        assert "INTERNAL SYSTEM EVENT" in p
        assert "Benign" in p

    def test_handles_missing_fields(self):
        # Must not raise on a near-empty event
        p = ai_analyst.build_prompt({})
        assert "Analyze this detection event" in p


# --- _call_nvidia JSON extraction -------------------------------------------

class TestCallNvidia:
    def test_extracts_clean_json(self):
        client = _client_returning('{"threat_type":"Ransomware","risk_level":"CRITICAL"}')
        out = ai_analyst._call_nvidia(client, "prompt")
        assert out["threat_type"] == "Ransomware"

    def test_extracts_json_embedded_in_text(self):
        client = _client_returning('Here is the verdict: {"threat_type":"Benign"} done.')
        out = ai_analyst._call_nvidia(client, "prompt")
        assert out["threat_type"] == "Benign"

    def test_no_json_raises(self):
        client = _client_returning("sorry, I cannot help with that")
        with pytest.raises(json.JSONDecodeError):
            ai_analyst._call_nvidia(client, "prompt")

    def test_malformed_json_raises(self):
        client = _client_returning('{"threat_type": "Ransomware",,,}')
        with pytest.raises(json.JSONDecodeError):
            ai_analyst._call_nvidia(client, "prompt")


# --- _call_with_fallback ----------------------------------------------------

class TestFallbackChain:
    def test_skips_none_clients(self):
        good = _client_returning('{"ok":1}')
        out = ai_analyst._call_with_fallback([None, good], "p")
        assert out == {"ok": 1}

    def test_falls_through_to_second_on_ratelimit(self):
        bad = MagicMock()
        bad.chat.completions.create.side_effect = RateLimitError(
            "rate", response=MagicMock(), body=None)
        bad._model = "m"
        good = _client_returning('{"ok":2}')
        out = ai_analyst._call_with_fallback([bad, good], "p")
        assert out == {"ok": 2}

    def test_auth_error_stops_fallback(self):
        bad = MagicMock()
        bad.chat.completions.create.side_effect = AuthenticationError(
            "bad key", response=MagicMock(), body=None)
        bad._model = "m"
        never = _client_returning('{"ok":3}')
        with pytest.raises(AuthenticationError):
            ai_analyst._call_with_fallback([bad, never], "p")
        # second client must never be consulted
        never.chat.completions.create.assert_not_called()

    def test_all_fail_raises_last(self):
        bad = MagicMock()
        bad.chat.completions.create.side_effect = APIConnectionError(request=MagicMock())
        bad._model = "m"
        with pytest.raises(APIConnectionError):
            ai_analyst._call_with_fallback([bad], "p")


# --- analyze_event failure envelopes ----------------------------------------

class TestAnalyzeEventEnvelopes:
    def test_returns_result_on_success(self, mocker):
        mocker.patch.object(ai_analyst, "_rate_limit")
        mocker.patch.object(ai_analyst, "_get_client_cerebras", return_value=None)
        mocker.patch.object(ai_analyst, "_get_client_events",
                            return_value=_client_returning('{"threat_type":"Benign"}'))
        mocker.patch.object(ai_analyst, "_get_client_alerts", return_value=None)
        out = ai_analyst.analyze_event({"event_type": "ENTROPY_SPIKE"})
        assert out["threat_type"] == "Benign"
        assert "analysis_failed" not in out

    def test_auth_error_envelope(self, mocker):
        mocker.patch.object(ai_analyst, "_rate_limit")
        mocker.patch.object(ai_analyst, "_get_client_cerebras", return_value=None)
        bad = MagicMock()
        bad.chat.completions.create.side_effect = AuthenticationError(
            "bad", response=MagicMock(), body=None)
        bad._model = "m"
        mocker.patch.object(ai_analyst, "_get_client_events", return_value=bad)
        mocker.patch.object(ai_analyst, "_get_client_alerts", return_value=None)
        out = ai_analyst.analyze_event({"event_type": "ENTROPY_SPIKE"})
        assert out["analysis_failed"] is True
        assert out["error_type"] == "AUTH_ERROR"

    def test_json_error_envelope(self, mocker):
        mocker.patch.object(ai_analyst, "_rate_limit")
        mocker.patch.object(ai_analyst, "_get_client_cerebras", return_value=None)
        mocker.patch.object(ai_analyst, "_get_client_events",
                            return_value=_client_returning("no json here"))
        mocker.patch.object(ai_analyst, "_get_client_alerts", return_value=None)
        out = ai_analyst.analyze_event({"event_type": "ENTROPY_SPIKE"})
        assert out["analysis_failed"] is True
        assert out["error_type"] == "JSON_ERROR"


# --- _rate_limit ------------------------------------------------------------

class TestRateLimit:
    def test_proceeds_when_slot_free(self, mocker):
        fake_script = MagicMock(return_value="0")  # 0 = slot claimed
        fake_redis = MagicMock()
        fake_redis.register_script.return_value = fake_script
        mocker.patch.object(ai_analyst, "_get_redis", return_value=fake_redis)
        # should return promptly without sleeping
        sleep = mocker.patch("backend.services.ai_analyst.time.sleep")
        ai_analyst._rate_limit("k", 0.5)
        sleep.assert_not_called()

    def test_waits_then_proceeds(self, mocker):
        # first call says wait 0.01s, second says claimed
        fake_script = MagicMock(side_effect=["0.01", "0"])
        fake_redis = MagicMock()
        fake_redis.register_script.return_value = fake_script
        mocker.patch.object(ai_analyst, "_get_redis", return_value=fake_redis)
        sleep = mocker.patch("backend.services.ai_analyst.time.sleep")
        ai_analyst._rate_limit("k", 0.5)
        sleep.assert_called_once()
