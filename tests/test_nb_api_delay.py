"""Tests for NB_API_DELAY_SECONDS throttling."""
import os
import time
from unittest.mock import patch

import requests
from main import ThrottledHTTPAdapter, get_postable_fields
from sync.runtime_config import _read_env_float, load_nb_api_delay_seconds


# ---------------------------------------------------------------------------
#  load_nb_api_delay_seconds (env parsing)
# ---------------------------------------------------------------------------

class TestLoadNbApiDelaySeconds:
    def test_defaults_zero_when_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            assert load_nb_api_delay_seconds() == 0.0

    def test_parses_float(self):
        with patch.dict(os.environ, {"NB_API_DELAY_SECONDS": "0.2"}, clear=True):
            assert load_nb_api_delay_seconds() == 0.2

    def test_parses_one(self):
        with patch.dict(os.environ, {"NB_API_DELAY_SECONDS": "1"}, clear=True):
            assert load_nb_api_delay_seconds() == 1.0

    def test_invalid_falls_back_to_default(self):
        with patch.dict(os.environ, {"NB_API_DELAY_SECONDS": "abc"}, clear=True):
            assert load_nb_api_delay_seconds() == 0.0

    def test_negative_rejected(self):
        with patch.dict(os.environ, {"NB_API_DELAY_SECONDS": "-0.5"}, clear=True):
            assert load_nb_api_delay_seconds() == 0.0


class TestReadEnvFloat:
    def test_default_returned_when_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            assert _read_env_float("SOME_FLOAT", default=1.5) == 1.5

    def test_minimum_enforced(self):
        with patch.dict(os.environ, {"SOME_FLOAT": "-1"}, clear=True):
            assert _read_env_float("SOME_FLOAT", default=2.0, minimum=0.0) == 2.0


# ---------------------------------------------------------------------------
#  ThrottledHTTPAdapter
# ---------------------------------------------------------------------------

class TestThrottledHTTPAdapter:
    def test_zero_delay_is_noop(self):
        adapter = ThrottledHTTPAdapter(delay=0.0)
        assert adapter._delay == 0.0

    def test_delay_stored(self):
        adapter = ThrottledHTTPAdapter(delay=0.5)
        assert adapter._delay == 0.5

    def test_negative_clamped_to_zero(self):
        adapter = ThrottledHTTPAdapter(delay=-1.0)
        assert adapter._delay == 0.0

    def test_send_sleeps_when_delay_set(self):
        # send() must call time.sleep with the configured delay before
        # delegating to the parent adapter.
        adapter = ThrottledHTTPAdapter(delay=0.3)
        with patch("main.time.sleep") as mock_sleep, patch(
            "requests.adapters.HTTPAdapter.send"
        ) as mock_send:
            adapter.send(requests.Request("GET", "http://x").prepare())
            mock_sleep.assert_called_once_with(0.3)
            mock_send.assert_called_once()

    def test_send_does_not_sleep_when_delay_zero(self):
        adapter = ThrottledHTTPAdapter(delay=0.0)
        with patch("main.time.sleep") as mock_sleep, patch(
            "requests.adapters.HTTPAdapter.send"
        ) as mock_send:
            adapter.send(requests.Request("GET", "http://x").prepare())
            mock_sleep.assert_not_called()
            mock_send.assert_called_once()

    def test_real_delay_observed(self):
        # End-to-end: a mounted adapter actually delays a request.
        adapter = ThrottledHTTPAdapter(delay=0.15)
        session = requests.Session()
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        started = time.monotonic()
        try:
            session.get("http://127.0.0.1:9", timeout=0.05)
        except requests.exceptions.ConnectionError:
            pass
        except requests.exceptions.ReadTimeout:
            pass
        elapsed = time.monotonic() - started
        assert elapsed >= 0.15


# ---------------------------------------------------------------------------
#  get_postable_fields uses the provided session
# ---------------------------------------------------------------------------

class TestGetPostableFieldsUsesSession:
    def test_uses_session_options_when_provided(self):
        fake_resp = type(
            "R",
            (),
            {
                "raise_for_status": lambda self: None,
                "json": lambda self: {"actions": {"POST": {"name": 1}}},
            },
        )()
        session = requests.Session()
        session.options = lambda *a, **k: fake_resp
        # Must not raise and must return the POST fields.
        with patch("main.requests.options") as mock_bare:
            fields = get_postable_fields(
                "http://nb/", "tok", "dcim/devices", session=session
            )
            mock_bare.assert_not_called()
            assert "name" in fields
