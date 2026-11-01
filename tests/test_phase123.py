import pytest
from backend.ai.orchestrator import ToolRegistry, MAX_TOOL_CALLS

def test_registry_rejects_unregistered_tool():
    r = ToolRegistry()
    with pytest.raises(PermissionError):
        r.call("arbitrary_python", {}, {"calls": 0})

def test_registry_enforces_five_call_limit():
    r = ToolRegistry()
    r.register("safe_lookup", "test lookup", lambda **kw: {"ok": True})
    state = {"calls": 0}
    for _ in range(MAX_TOOL_CALLS):
        assert r.call("safe_lookup", {}, state) == {"ok": True}
    with pytest.raises(RuntimeError):
        r.call("safe_lookup", {}, state)

def test_registry_rejects_duplicate_names():
    r = ToolRegistry()
    r.register("lookup", "first", lambda **kw: None)
    with pytest.raises(ValueError):
        r.register("lookup", "second", lambda **kw: None)
