"""Helpers for building the `steps` trace and parsing model JSON output.

Every module invocation (LLM call, retrieval, or tool lookup) is appended to a
shared list of step dicts that matches the required schema:

    { "module": "...", "prompt": {"System_prompt": "...", "User_prompt": "..."},
      "response": {...} }

Module strings MUST match the architecture diagram box names exactly:
Supervisor, Company Law, Employee Law, Editor, Reflection.
"""
import json
import re


def make_step(module: str, system_prompt: str, user_prompt: str, response) -> dict:
    """Build one entry for the `steps` array."""
    return {
        "module": module,
        "prompt": {
            "System_prompt": system_prompt or "",
            "User_prompt": user_prompt or "",
        },
        "response": response,
    }


def parse_json(text: str):
    """Best-effort extraction of a JSON object from an LLM response.

    Handles ```json fenced blocks and leading/trailing prose.
    Raises ValueError if nothing parseable is found.
    """
    if text is None:
        raise ValueError("empty model response")
    s = text.strip()

    # strip code fences
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()

    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    # fall back to the first {...} balanced-looking block
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = s[start:end + 1]
        return json.loads(candidate)

    raise ValueError(f"could not parse JSON from model output: {text[:200]!r}")
