"""
tests.conftest
~~~~~~~~~~~~~~~
Shared fixtures for the test suite.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_settings_singleton():
    """Reset the settings singleton between tests to avoid leaking state."""
    import app.core.config as config_mod
    import app.core.llm_client as llm_mod

    config_mod._settings = None
    llm_mod._worker = None
    yield
    config_mod._settings = None
    llm_mod._worker = None


@pytest.fixture(autouse=True)
def _set_test_env_vars(monkeypatch):
    """Set required env vars for all tests (avoids pydantic-settings crashes)."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("FEATHERLESS_API_KEY", "test-key-1")
