"""Reflection module — verifies the Editor's rewrite resolves every issue (one LLM call)."""
import json

from langchain_core.prompts import ChatPromptTemplate

from config import get_llm
from agent.prompts import REFLECTION_SYSTEM
from agent.trace import make_step, parse_json


def run_reflection(revised_contract: str, issues: list, steps: list, iteration: int,
                   original_contract: str = "") -> dict:
    """Return {"pass": bool, "remaining_issues": [...]}. Appends a Reflection step.

    `original_contract` is supplied so the reviewer can catch REGRESSIONS — an
    edit that resolves an issue by making a term worse than the original draft.
    """
    user = (
        f"ORIGINAL DRAFT:\n{original_contract or '(not provided)'}\n\n"
        f"REVISED CONTRACT:\n{revised_contract}\n\n"
        f"ISSUES THAT HAD TO BE FIXED (JSON):\n{json.dumps(issues, ensure_ascii=False, indent=2)}\n\n"
        "Verify each issue is resolved AND that no benefit was reduced versus the original draft. Return JSON."
    )
    chain = ChatPromptTemplate.from_messages(
        [("system", "{system}"), ("human", "{user}")]) | get_llm()
    raw = chain.invoke({"system": REFLECTION_SYSTEM, "user": user}).content

    try:
        parsed = parse_json(raw)
        remaining = parsed.get("remaining_issues", [])
        passed = bool(parsed.get("pass", not remaining)) and not remaining
    except ValueError:
        parsed = {"pass": True, "remaining_issues": []}
        remaining, passed = [], True

    parsed["pass"] = passed
    parsed["remaining_issues"] = remaining
    steps.append(make_step(
        module=f"Reflection (iteration {iteration})",
        system_prompt=REFLECTION_SYSTEM, user_prompt=user, response=parsed,
    ))
    return {"pass": passed, "remaining_issues": remaining}
