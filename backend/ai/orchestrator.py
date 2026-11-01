"""Guarded scholarship assistant orchestration. Only six registered tools are callable; max five calls per task."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Any

MAX_TOOL_CALLS = 5

@dataclass
class Tool:
    name: str
    description: str
    handler: Callable[..., Any]

class ToolRegistry:
    def __init__(self): self._tools: dict[str, Tool] = {}
    def register(self, name: str, description: str, handler: Callable[..., Any]):
        if name in self._tools: raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = Tool(name, description, handler)
    def call(self, name: str, arguments: dict, state: dict):
        if name not in self._tools: raise PermissionError(f"Unregistered tool: {name}")
        if state.setdefault("calls", 0) >= MAX_TOOL_CALLS: raise RuntimeError("Maximum of five AI tool calls per task reached")
        state["calls"] += 1
        return self._tools[name].handler(**arguments)
    def manifest(self): return [{"name": t.name, "description": t.description} for t in self._tools.values()]


def build_registry(*, scholarship_search, profile_lookup, document_lookup, eligibility_evaluate, application_prepare, tracking_retrieve):
    r = ToolRegistry()
    r.register("scholarship_search", "Search published scholarship records", scholarship_search)
    r.register("profile_lookup", "Read the authenticated student's own profile", profile_lookup)
    r.register("document_lookup", "Read the authenticated student's own document metadata", document_lookup)
    r.register("eligibility_evaluation", "Run deterministic backend eligibility evaluation", eligibility_evaluate)
    r.register("application_preparation", "Prepare an application draft; never submit it", application_prepare)
    r.register("tracking_retrieval", "Retrieve application timeline and recorded status", tracking_retrieve)
    return r
