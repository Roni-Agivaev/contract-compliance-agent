"""Company Law / Employee Law sub-agent.

One implementation, invoked twice (once per jurisdiction). The `module` name it
logs under is "Company Law" or "Employee Law" so the trace matches the diagram.

Each invocation:
  1. retrieves statutes for its jurisdiction (ComplianceRetriever) -> logged step
  2. looks up the country's minimum wage (MinimumWageTool)        -> logged step
  3. one LLM call to identify breaches + proposed fixes            -> logged step
"""
import json

from langchain_core.prompts import ChatPromptTemplate

from config import get_llm, JURISDICTIONS
from agent.prompts import LAW_AGENT_SYSTEM
from agent.retriever import retrieve, format_context
from agent.tools import lookup_minimum_wage
from agent.trace import make_step, parse_json


def run_law_agent(module: str, role_jurisdiction: str, country_code: str,
                  contract_text: str, search_queries, steps: list,
                  country_label: str = None) -> dict:
    """Run one law sub-agent. `module` = 'Company Law' or 'Employee Law'.

    Returns {"jurisdiction": <label>, "breaches": [...]}.
    Appends retrieval, minimum-wage, and LLM steps to `steps`.
    `country_code` may be None for a jurisdiction outside the indexed subset;
    the agent then runs on the ILO baseline only, using `country_label` for text.
    """
    label = (JURISDICTIONS.get(country_code, {}).get("label")
             or country_label or country_code or "the specified country")

    # 1) retrieval (no LLM) --------------------------------------------------
    passages = retrieve(search_queries, country_code)
    context = format_context(passages)
    steps.append(make_step(
        module=module,
        system_prompt="[ComplianceRetriever] Embed queries and query the "
                      f"{label} statute namespace + ILO baseline in Pinecone.",
        user_prompt="Queries: " + " | ".join(search_queries or []),
        response={"retrieved": [
            {"source": p["source"], "section": p["section"], "score": round(p["score"], 3)}
            for p in passages
        ]},
    ))

    # 2) minimum-wage tool (no LLM) -----------------------------------------
    wage = lookup_minimum_wage(country_code)
    steps.append(make_step(
        module=module,
        system_prompt="[MinimumWageTool] Deterministic Supabase lookup of the "
                      "2026 statutory minimum wage for the jurisdiction.",
        user_prompt=f"country={label}",
        response=wage,
    ))

    # 3) breach analysis (LLM) ----------------------------------------------
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

    steps.append(make_step(
        module=module, system_prompt=system, user_prompt=user, response=parsed,
    ))

    return {"jurisdiction": label, "breaches": breaches}
