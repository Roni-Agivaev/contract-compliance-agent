"""Payload for GET /api/agent_info.

description / purpose / prompt_template are defined here; prompt_examples are
loaded from agent_examples.json, which is generated from REAL runs of the agent
by scripts/build_agent_examples.py (never hand-written), so the documented
behaviour always matches what POST /api/execute actually returns.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES_PATH = os.path.join(ROOT, "agent_examples.json")

DESCRIPTION = (
    "A multi-agent Contract Compliance Agent for international hiring. You give it an "
    "employment contract or offer letter as TEXT together with the company's country and the "
    "employee's country; it audits the contract against BOTH jurisdictions' labor law using "
    "retrieval-augmented generation over official statutes, then rewrites every non-compliant "
    "clause and returns the corrected contract with a plain-English log of what changed and why."
    "\n\n"
    "How it works (the module names below match the architecture diagram returned by "
    "GET /api/model_architecture and the `module` field of every step in the trace):\n"
    "1. Supervisor — reads the two jurisdictions from the prompt (or infers them from the "
    "contract when they are not stated), checks the request is in scope, confirms both countries "
    "are in the indexed legal corpus, extracts the stated pay, and plans the legal search queries.\n"
    "2. Company Law and Employee Law — two sub-agents running in parallel, one per jurisdiction. "
    "Each retrieves the statutes for its country from its own Pinecone namespace, applies an "
    "applicability gate (a country's labor law generally governs only where the work is performed), "
    "receives a deterministically computed minimum-wage verdict, and returns breaches with citations "
    "and proposed fixes.\n"
    "3. Supervisor validation gate — a deterministic pass over both findings lists that keeps only "
    "entries which self-declare as a violation and cite a real statute, so compliance notes never "
    "reach the Editor or inflate the report.\n"
    "4. Editor and Reflection — the Editor rewrites the flagged clauses (it may only raise a term to "
    "meet the law, never reduce a benefit), and Reflection verifies each issue was resolved without "
    "introducing a regression, looping back to the Editor for at most three iterations.\n"
    "If no breaches survive the validation gate, the Supervisor autonomously returns the original "
    "contract unchanged with a 'No breaches found' message and never invokes the Editor.\n\n"
    "What it CAN do: audit and rewrite employment contracts for the United States, United Kingdom, "
    "Germany and Israel; cite the specific statute behind each finding; compare pay across "
    "currencies and hourly/monthly/annual units against the statutory minimum wage; and return a "
    "full step-by-step execution trace.\n\n"
    "What it CANNOT do: it is not legal advice and does not replace a qualified employment lawyer; "
    "it does not send, sign, file or store contracts; it reasons only from the indexed statutes and "
    "not from the open internet; and it refuses contracts where either jurisdiction is outside the "
    "supported list, returning a structured error instead of guessing."
)

PURPOSE = (
    "Cut the time and legal risk of international onboarding by automatically finding and fixing "
    "labor-law violations in cross-border employment contracts before they are sent to a candidate."
)

PROMPT_TEMPLATE = {
    "template": (
        "Company country: <where the hiring company is based, e.g. United Kingdom>\n"
        "Employee country: <where the employee lives and performs the work, e.g. Germany>\n"
        "Contract / Offer text: <paste the full contract or offer letter as plain text>"
    ),
    "example": (
        "Company country: United Kingdom\n"
        "Employee country: Germany\n"
        "Contract / Offer text: EMPLOYMENT AGREEMENT between Brightpath Analytics Ltd, London "
        "('the Company'), and Mr. Lukas Berger, Munich, Germany ('the Employee').\n"
        "3. Probationary Period: The first twelve (12) months constitute a probationary period, "
        "during which the Company may terminate the employment immediately and without notice.\n"
        "6. Remuneration: The Employee shall receive a gross salary of EUR 2,000 per month.\n"
        "8. Annual Leave: The Employee is entitled to fifteen (15) days of paid annual leave.\n"
        "10. Termination: After the probationary period, either party may terminate by giving "
        "one (1) week's written notice..."
    ),
}


def _load_examples():
    try:
        with open(EXAMPLES_PATH, encoding="utf-8") as f:
            return json.load(f).get("prompt_examples", [])
    except (OSError, ValueError):
        return []


# Exactly the four keys the assignment's response format specifies.
AGENT_INFO = {
    "description": DESCRIPTION,
    "purpose": PURPOSE,
    "prompt_template": PROMPT_TEMPLATE,
    "prompt_examples": _load_examples(),
}
