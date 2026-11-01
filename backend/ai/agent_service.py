"""Conservative assistant entry point: retrieval-grounded responses and strict tool-call budget."""
from backend.ai.orchestrator import build_registry
from backend.ai import router

class ScholarshipAssistant:
    def __init__(self, handlers):
        self.tools = build_registry(**handlers)
    def run(self, question: str, context: str = ""):
        # The model is explicitly told not to invent a tool result or eligibility decision.
        prompt = ("You are EduPilot AI, a scholarship information assistant. Use only the supplied verified context. "
                  "Never claim eligibility, selection, authenticity, payment or submission is guaranteed. "
                  "If information is missing, say so and ask for it. Do not request or expose passwords, OTPs, "
                  "CAPTCHAs, bank credentials or full identity numbers. Final eligibility is determined by backend rules.\n\n"
                  f"CONTEXT:\n{context[:12000]}\n\nQUESTION:\n{question[:3000]}")
        result = router.complete(prompt, light=False, task="assistant")
        return {"answer": result.get("text") or "The AI providers are unavailable. Please use scholarship search or try again later.",
                "provider": result.get("provider", "none"), "tool_calls_used": 0,
                "tool_call_limit": 5, "source_references": []}
