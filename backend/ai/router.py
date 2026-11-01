"""Provider router: capped Gemini -> local Ollama Qwen3 -> safe deterministic fallback.
Cloud calls are bounded; document-context prompts can force local-only processing.
"""
from __future__ import annotations
import json, os, urllib.request

_calls = {"gemini": 0}
usage, usage_hook = {}, None


def _log(result, prompt, light, task):
    usage[result["provider"]] = usage.get(result["provider"], 0) + 1
    if usage_hook:
        try:
            usage_hook({"provider": result["provider"], "task": task, "light": light,
                        "prompt_chars": len(prompt), "response_chars": len(result.get("text") or "")})
        except Exception:
            pass
    return result


def _post(url, body, timeout, headers=None):
    req = urllib.request.Request(url, json.dumps(body).encode(),
                                 {"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def configuration():
    return {
        "primary_model": os.getenv("GEMINI_PRIMARY_MODEL", "gemini-3.8-flash"),
        "light_model": os.getenv("GEMINI_LIGHT_MODEL", "gemini-3.1-flash-lite"),
        "local_model": os.getenv("LOCAL_LLM_MODEL", "qwen3:4b"),
        "embedding_model": os.getenv("EMBED_MODEL", "nomic-embed-text-v2-moe"),
        "gemini_configured": bool(os.getenv("AI_API_KEY")),
        "ollama_configured": bool(os.getenv("OLLAMA_URL", "http://localhost:11434")),
        "gemini_calls_this_process": _calls["gemini"],
        "gemini_request_limit": int(os.getenv("GEMINI_REQUEST_LIMIT", "50")),
    }


def complete(prompt, light=False, task="general", local_only=False):
    key = os.getenv("AI_API_KEY")
    limit = max(0, int(os.getenv("GEMINI_REQUEST_LIMIT", "50")))
    model = os.getenv("GEMINI_LIGHT_MODEL" if light else "GEMINI_PRIMARY_MODEL") or (
        "gemini-3.1-flash-lite" if light else "gemini-3.8-flash")
    if not local_only and key and _calls["gemini"] < limit:
        try:
            _calls["gemini"] += 1
            data = _post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                {"contents": [{"parts": [{"text": prompt}]}],
                 "generationConfig": {"temperature": 0.2}}, 30,
                {"x-goog-api-key": key})
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return _log({"provider": "gemini", "model": model, "text": text}, prompt, light, task)
        except Exception:
            pass
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    try:
        data = _post(ollama_url + "/api/generate",
                     {"model": os.getenv("LOCAL_LLM_MODEL", "qwen3:4b"),
                      "prompt": prompt, "stream": False,
                      "options": {"temperature": 0.2}}, 90)
        return _log({"provider": "ollama", "model": os.getenv("LOCAL_LLM_MODEL", "qwen3:4b"),
                     "text": data.get("response")}, prompt, light, task)
    except Exception:
        return _log({"provider": "none", "model": None, "text": None}, prompt, light, task)
