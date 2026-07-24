"""Static payload for GET /api/agent_info.

Includes a fully worked example (slide-7 scenario: US company hiring a
Germany-based developer with a zero-notice termination clause that violates
German BGB 622) with its full step trace.
"""

_PROMPT_TEMPLATE = (
    "Company country: <where the hiring company is based, e.g. United States>\n"
    "Employee country: <where the worker is based, e.g. Germany>\n"
    "Contract / Offer text: <paste the full contract or offer letter as text>"
)

_EXAMPLE_PROMPT = (
    "Company country: United States\n"
    "Employee country: Germany\n"
    "Contract / Offer text: This Employment Agreement is between Acme Inc. (US) and "
    "the Employee (Germany). Compensation is EUR 1,200 per month. Either party may "
    "terminate this agreement effective immediately, with no prior notice."
)

_EXAMPLE_RESPONSE = (
    "## ⚖️ Compliance Review — Contract Corrected\n\n"
    "**Jurisdictions reviewed:** United States and Germany\n"
    "**Breaches found:** 2  ·  **Edits applied:** 2\n\n"
    "### Breaches found\n"
    "- **[HIGH] Germany** — A zero-notice termination clause is void; German law sets "
    "statutory minimum notice periods that scale with tenure. _(cite: BGB 622)_\n"
    "- **[HIGH] Germany** — Monthly pay of EUR 1,200 falls below the German statutory "
    "minimum wage for full-time work. _(cite: German minimum wage 2026)_\n\n"
    "### Changes made (plain English)\n"
    "- **Termination clause**: Replaced instant termination with the statutory notice "
    "period under German law — _resolves BGB 622 violation_\n"
    "- **Compensation clause**: Raised monthly pay to meet the German statutory minimum "
    "wage — _resolves minimum-wage breach_\n\n"
    "### ✅ Corrected contract\n\n"
    "This Employment Agreement is between Acme Inc. (US) and the Employee (Germany). "
    "Compensation is set at no less than the German statutory minimum wage for full-time "
    "work. Either party may terminate with the statutory notice period required under "
    "German law (BGB 622), scaling with the employee's tenure."
)

_EXAMPLE_STEPS = [
    {
        "module": "Supervisor",
        "prompt": {
            "System_prompt": "You are the Supervisor ... decide in_scope and plan legal search queries. JSON only.",
            "User_prompt": "Company country: United States\nEmployee country: Germany\nContract text: ... no prior notice.",
        },
        "response": {
            "in_scope": True, "reason": None,
            "company_country": "United States", "employee_country": "Germany",
            "search_queries": ["minimum wage Germany", "notice period termination BGB",
                                "working hours overtime", "paid annual leave"],
        },
    },
    {
        "module": "Company Law",
        "prompt": {"System_prompt": "You are the Company Law sub-agent ... United States ... JSON only.",
                    "User_prompt": "CONTRACT ... RETRIEVED US LAW PASSAGES ... MINIMUM WAGE RECORD ..."},
        "response": {
            "retrieved_sources": [{"source": "US Fair Labor Standards Act (FLSA)", "section": "§206", "score": 0.41}],
            "minimum_wage": {"found": True, "country": "United States", "amount": 7.25, "currency": "USD", "unit": "hour"},
            "analysis": {"jurisdiction": "United States", "breaches": []},
        },
    },
    {
        "module": "Employee Law",
        "prompt": {"System_prompt": "You are the Employee Law sub-agent ... Germany ... JSON only.",
                    "User_prompt": "CONTRACT ... RETRIEVED GERMANY LAW PASSAGES ... MINIMUM WAGE RECORD ..."},
        "response": {
            "retrieved_sources": [{"source": "German Civil Code (BGB)", "section": "§622", "score": 0.63}],
            "minimum_wage": {"found": True, "country": "Germany", "amount": 12.82, "currency": "EUR", "unit": "hour"},
            "analysis": {"jurisdiction": "Germany", "breaches": [
                {"clause": "Either party may terminate ... with no prior notice.",
                 "issue": "Zero-notice termination is void under German statutory notice rules.",
                 "severity": "high", "law_citation": "BGB 622",
                 "proposed_fix": "Apply the statutory notice period under BGB 622, scaling with tenure."},
                {"clause": "EUR 1,200 per month",
                 "issue": "Below the German statutory minimum wage for full-time work.",
                 "severity": "high", "law_citation": "German minimum wage 2026",
                 "proposed_fix": "Raise pay to at least the statutory minimum wage."},
            ]},
        },
    },
    {
        "module": "Editor (iteration 1)",
        "prompt": {"System_prompt": "You are the Editor ... rewrite fixing every issue. JSON only.",
                    "User_prompt": "CONTRACT ... ISSUES TO FIX (JSON) ..."},
        "response": {"revised_contract": "... statutory notice period required under German law (BGB 622) ...",
                      "changes": [
                          {"clause": "Termination clause", "change": "Replaced instant termination with statutory notice.", "why": "BGB 622"},
                          {"clause": "Compensation clause", "change": "Raised pay to the German minimum wage.", "why": "minimum wage 2026"},
                      ]},
    },
    {
        "module": "Reflection (iteration 1)",
        "prompt": {"System_prompt": "You are the Reflection reviewer ... verify each issue resolved. JSON only.",
                    "User_prompt": "REVISED CONTRACT ... ISSUES THAT HAD TO BE FIXED (JSON) ..."},
        "response": {"pass": True, "remaining_issues": []},
    },
]

AGENT_INFO = {
    "description": (
        "A multi-agent Contract Compliance Agent for international hiring. It takes an "
        "employment contract or offer letter as TEXT, plus the company's country and the "
        "employee's country, and reviews the contract against BOTH jurisdictions' labor "
        "law using retrieval-augmented generation (RAG) over official statutes, plus a "
        "2026 minimum-wage check.\n\n"
        "Architecture (slide 6): a Supervisor orchestrates the flow; Company Law and "
        "Employee Law sub-agents run in parallel, each scanning its jurisdiction's statutes "
        "and flagging breaches with citations and fixes; an Editor rewrites the flagged "
        "clauses and a Reflection reviewer verifies the fixes in a short loop. If no "
        "breaches are found, the Supervisor autonomously returns the original contract with "
        "a 'No breaches found' message.\n\n"
        "What it CAN do: audit and rewrite contracts for US, UK, Germany, and Israel "
        "jurisdictions (plus a universal ILO baseline and a global minimum-wage table); cite "
        "the specific statute behind each finding; return a full step-by-step trace.\n"
        "What it CANNOT do: it is not legal advice; it does not send, sign, or file "
        "anything; and it only reasons from the indexed statutes, not the open internet."
    ),
    "purpose": (
        "Cut the time and legal risk of international onboarding by automatically catching "
        "and fixing labor-law violations in cross-border employment contracts before they "
        "are sent."
    ),
    "prompt_template": {"template": _PROMPT_TEMPLATE},
    "prompt_examples": [
        {
            "prompt": _EXAMPLE_PROMPT,
            "full_response": _EXAMPLE_RESPONSE,
            "steps": _EXAMPLE_STEPS,
        }
    ],
}
