"""Company Law / Employee Law sub-agent.

One implementation, invoked twice (once per jurisdiction). The `module` name it
logs under is "Company Law" or "Employee Law" so the trace matches the diagram.

Each invocation does three things but logs a SINGLE step (one LLM call):
  1. retrieves statutes for its jurisdiction (ComplianceRetriever, no LLM)
  2. looks up the country's minimum wage (MinimumWageTool, no LLM)
  3. one LLM call to identify breaches + proposed fixes
The retrieval sources and wage result are surfaced inside that step's response.
"""
import json

from langchain_core.prompts import ChatPromptTemplate

from config import get_llm, JURISDICTIONS
from agent.prompts import LAW_AGENT_SYSTEM
from agent.retriever import retrieve, format_context
from agent.tools import lookup_minimum_wage
from agent.trace import make_step, parse_json


# Phrases that mark a "finding" as a non-breach (the model hedging rather than
# reporting an actual violation). Such items are dropped before they reach the
# Editor, so they cannot inflate the breach list or trigger pointless rewrites.
_NON_BREACH_MARKERS = (
    "no concrete breach", "cannot be established", "could not be established",
    "could not be verified", "could not be retrieved", "not supported by",
    "do not include any", "do not contain any", "does not contain any",
    "no breach can be", "unable to verify", "record is unavailable",
    "not available", "no statutory", "cannot be confirmed",
)


def _is_real_breach(b: dict) -> bool:
    """Drop hedged non-findings: they must have a citation and assert a violation."""
    if not isinstance(b, dict):
        return False
    cite = (b.get("law_citation") or "").strip().lower()
    if not cite or cite in {"n/a", "none", "null", "minimum-wage record", "minimum_wage record"}:
        return False
    blob = f"{b.get('issue', '')} {b.get('clause', '')}".lower()
    return not any(marker in blob for marker in _NON_BREACH_MARKERS)


def run_law_agent(module: str, role_jurisdiction: str, country_code: str,
                  contract_text: str, search_queries, steps: list,
                  country_label: str = None) -> dict:
    """Run one law sub-agent. `module` = 'Company Law' or 'Employee Law'.

    Returns {"jurisdiction": <label>, "breaches": [...]}.
    Appends ONE merged step to `steps` (the LLM breach-analysis call, with the
    retrieval sources + minimum-wage tool result surfaced in its response).
    `country_code` may be None for a jurisdiction outside the indexed subset;
    the agent then runs on the ILO baseline only, using `country_label` for text.
    """
    label = (JURISDICTIONS.get(country_code, {}).get("label")
             or country_label or country_code or "the specified country")

    # internal tools (no LLM): retrieval + minimum-wage lookup ----------------
    passages = retrieve(search_queries, country_code)
    context = format_context(passages)
    wage = lookup_minimum_wage(country_code)

    # single LLM call: breach analysis ---------------------------------------
    system = LAW_AGENT_SYSTEM.format(
        role=module, country=label, role_jurisdiction=role_jurisdiction,
    )
    user = (
        f"CONTRACT:\n{contract_text}\n\n"
        f"RETRIEVED {label.upper()} LAW PASSAGES:\n{context}\n\n"
        f"MINIMUM WAGE RECORD:\n{json.dumps(wage)}\n\n"
        f"Identify breaches for {label} only. Return JSON."
    )
    chain = ChatPromptTemplate.from_messages(
        [("system", "{system}"), ("human", "{user}")]) | get_llm()
    raw = chain.invoke({"system": system, "user": user}).content

    try:
        parsed = parse_json(raw)
        breaches = parsed.get("breaches", []) if isinstance(parsed, dict) else []
    except ValueError:
        parsed = {"jurisdiction": label, "breaches": [], "_raw": raw}
        breaches = []

    # keep only genuine, citable violations
    filtered = [b for b in breaches if _is_real_breach(b)]
    dropped = len(breaches) - len(filtered)
    breaches = filtered
    if isinstance(parsed, dict):
        parsed["breaches"] = breaches
        if dropped:
            parsed["_dropped_non_breaches"] = dropped

    # one merged step for this sub-agent: the LLM call, plus the tool results
    # (retrieved sources + minimum wage) surfaced for transparency.
    response = {
        "retrieved_sources": [
            {"source": p["source"], "section": p["section"], "score": round(p["score"], 3)}
            for p in passages
        ],
        "minimum_wage": wage,
        "analysis": parsed,
    }
    steps.append(make_step(
        module=module, system_prompt=system, user_prompt=user, response=response,
    ))

    return {"jurisdiction": label, "breaches": breaches}
