"""SUP-10: portability of the CRIBA bridge (no hardcoded root, validated timeout).

The bridge must degrade to an explicit "unavailable" dict instead of raising
or running a subprocess with a nonexistent cwd, and must keep its return
contract (dict with error/raw_output keys) intact.
"""

from __future__ import annotations

from supra_agentic.integrations import criba_bridge


def _env_without_roots(monkeypatch):
    monkeypatch.delenv("SUPRA_CRIBA_ROOT", raising=False)
    monkeypatch.delenv("CRIBA_ROOT", raising=False)
    monkeypatch.delenv("SUPRA_CRIBA_TIMEOUT", raising=False)


def test_root_not_found_returns_explicit_error_without_exception(monkeypatch):
    """No env root and no valid checkout -> unavailable, never an exception."""
    _env_without_roots(monkeypatch)
    # Force the historical fallback to be invalid as well.
    monkeypatch.setattr(criba_bridge, "_CRIBA_ROOT_FALLBACK", "C:/does/not/exist/CRIBA")

    result = criba_bridge.call_criba("consulta de prueba")
    assert result["error"]
    assert result["status"] == "unavailable"
    assert isinstance(result, dict)

    result = criba_bridge.call_blackforge("consulta de prueba")
    assert result["error"]
    assert result["status"] == "unavailable"
    assert isinstance(result, dict)


def test_invalid_timeout_returns_explicit_error(monkeypatch):
    """SUPRA_CRIBA_TIMEOUT invalid (non-integer or <= 0) -> explicit error."""
    monkeypatch.delenv("SUPRA_CRIBA_ROOT", raising=False)
    monkeypatch.delenv("CRIBA_ROOT", raising=False)
    monkeypatch.setattr(criba_bridge, "_resolve_criba_root", lambda: ".")
    monkeypatch.setenv("SUPRA_CRIBA_TIMEOUT", "not-a-number")

    result = criba_bridge.call_criba("consulta")
    assert result["error"]
    assert "timeout" in result["error"].lower()


def test_valid_timeout_env_is_used(monkeypatch):
    """A positive SUPRA_CRIBA_TIMEOUT is honored by _criba_timeout()."""
    monkeypatch.setenv("SUPRA_CRIBA_TIMEOUT", "17")
    assert criba_bridge._criba_timeout() == 17


def test_missing_timeout_env_uses_default():
    """No timeout env -> default 60s."""
    import os

    old = os.environ.pop("SUPRA_CRIBA_TIMEOUT", None)
    try:
        assert criba_bridge._criba_timeout() == 60
    finally:
        if old is not None:
            os.environ["SUPRA_CRIBA_TIMEOUT"] = old


def test_contract_keys_preserved(monkeypatch):
    """Even on failure the dict keeps the callers' expected keys."""
    _env_without_roots(monkeypatch)
    monkeypatch.setattr(criba_bridge, "_CRIBA_ROOT_FALLBACK", "C:/does/not/exist/CRIBA")

    for fn in (criba_bridge.call_criba, criba_bridge.call_blackforge):
        result = fn("test")
        assert isinstance(result, dict)
        # runner.py consumes "error"/"raw_output" keys; a failure carries "error".
        assert "error" in result
