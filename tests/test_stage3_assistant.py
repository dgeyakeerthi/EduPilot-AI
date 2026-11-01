import pytest
from backend.ai.orchestrator import ToolRegistry, MAX_TOOL_CALLS
from backend.ai.assistant_api import _json_object, ALLOWED

def test_registry_rejects_unregistered_tool():
    r=ToolRegistry(); r.register('ok','safe',lambda: {'ok':True})
    with pytest.raises(PermissionError): r.call('exec_code',{}, {'calls':0})

def test_registry_enforces_five_calls_per_task():
    r=ToolRegistry(); r.register('ok','safe',lambda: {'ok':True})
    state={'calls':0}
    for _ in range(MAX_TOOL_CALLS): assert r.call('ok',{},state)=={'ok':True}
    with pytest.raises(RuntimeError): r.call('ok',{},state)

def test_only_six_sdd_tools_are_allowed():
    assert set(ALLOWED)=={'scholarship_search','profile_lookup','document_lookup','eligibility_evaluation','application_preparation','tracking_retrieval'}

def test_planner_json_parser_handles_fenced_json():
    assert _json_object('```json\n{"tool_calls": [], "answer": "hello"}\n```')['answer']=='hello'

def test_planner_json_parser_rejects_invalid_text():
    assert _json_object('not json') is None
