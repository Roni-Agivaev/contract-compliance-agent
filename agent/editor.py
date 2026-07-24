"""Editor module — rewrites flagged clauses into compliant language (one LLM call)."""
import json

from langchain_core.prompts import ChatPromptTemplate

from config import get_llm
from agent.prompts import EDITOR_SYSTEM
from agent.trace import make_step, parse_json


def run_editor(contract_text: str, issues: list, steps: list, iteration: int) -> dict:
    """Return {"revised_contract": str, "changes": [...]}. Appends an Editor step."""
    user = (
        f"CONTRACT:\n{contract_text}\n\n"
        f"ISSUES TO FIX (JSON):\n{json.dumps(issues, ensure_ascii=False, indent=2)}\n\n"
        "Rewrite the contract fixing every issue. Return JSON."
    )
    chain = ChatPromptTemplate.from_messages(
        [("system", "{system}"), ("human", "{user}")]) | get_llm()
    raw = chain.invoke({"system": EDITOR_SYSTEM, "user": user}).content

    try:
        parsed = parse_json(raw)
        revised = parsed.get("revised_contract", contract_text)
        changes = parsed.get("changes", [])
    except ValueError:
        parsed = {"revised_contract": raw, "changes": []}
        revised, changes = raw, []

    steps.append(make_step(
        module=f"Editor (iteration {iteration})",
        system_prompt=EDITOR_SYSTEM, user_prompt=user, response=parsed,
    ))
    return {"revised_contract": revised, "changes": changes}


# keep the diagram module name exact when reading the trace: the base name is
# "Editor"; the iteration suffix disambiguates loop passes.
