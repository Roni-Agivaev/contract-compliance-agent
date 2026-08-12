"""Supervisor — orchestrates the whole slide-6 flow.

Draft Contract -> Supervisor -> (Company Law || Employee Law) -> Supervisor
-> Editor <-> Reflection -> Compliant Contract + change log.

The two jurisdictions come from the input prompt (provided explicitly by the
user); the Supervisor reads them as given, or infers them from the contract. If
Company Law + Employee Law find no breaches, the Supervisor autonomously returns
the original contract with a "No breaches found" message and never invokes
Editor/Reflection.
"""
import re
from concurrent.futures import ThreadPoolExecutor

from langchain_core.prompts import ChatPromptTemplate

from config import get_llm, normalize_country, JURISDICTIONS, MAX_REFLECTION_ITERS
from agent.prompts import supervisor_system
from agent.law_agent import run_law_agent
from agent.editor import run_editor
from agent.reflection import run_reflection
from agent.trace import make_step, parse_json


# ── input parsing ──────────────────────────────────────────────────────────────
def parse_input(prompt: str):
    """Extract (company_country, employee_country, contract_text) from the prompt.

    Expected fields (case-insensitive):
        Company country: ...
        Employee country: ...
        Contract / Offer text: ...
    Falls back to treating the whole prompt as the contract if fields are absent.
    """
    def grab(label_pattern):
        m = re.search(label_pattern + r"\s*[:\-]\s*(.+)", prompt, re.IGNORECASE)
        return m.group(1).strip().splitlines()[0].strip() if m else None

    company = grab(r"company\s*country")
    employee = grab(r"employee\s*country")

    m = re.search(r"(?:contract|offer)(?:\s*/\s*offer)?\s*(?:text)?\s*[:\-]\s*(.+)",
                  prompt, re.IGNORECASE | re.DOTALL)
    contract = m.group(1).strip() if m else prompt.strip()
    return company, employee, contract


# ── pipeline ────────────────────────────────────────────────────────────────────
def supported_countries_list() -> str:
    """Canonical names of the jurisdictions whose law is indexed."""
    return ", ".join(cfg["label"] for cfg in JURISDICTIONS.values())


def _supervisor_plan(contract: str, company_raw, employee_raw, supported: str,
                     steps: list) -> dict:
    """One Supervisor LLM call: scope guard, jurisdictions, pay, search queries."""
    system = supervisor_system(supported)
    sup_user = (
        f"Company country: {company_raw or '(not given)'}\n"
        f"Employee country: {employee_raw or '(not given)'}\n"
        f"Contract text:\n{contract}"
    )
    chain = ChatPromptTemplate.from_messages(
        [("system", "{system}"), ("human", "{user}")]) | get_llm()
    raw = chain.invoke({"system": system, "user": sup_user}).content
    try:
        plan = parse_json(raw)
    except ValueError:
        plan = {"in_scope": True, "reason": None,
                "company_country": company_raw, "employee_country": employee_raw,
                "search_queries": []}
    steps.append(make_step("Supervisor", system, sup_user, plan))
    return plan


def _run_law_agents(contract: str, plan: dict, company_raw, employee_raw,
                    company_code, employee_code, steps: list):
    """Company Law || Employee Law, then the Supervisor validation gate.

    Returns (accepted_issues, company_result, employee_result).
    """
    queries = plan.get("search_queries") or [
        "minimum wage", "working hours and overtime", "paid annual leave",
        "notice period and termination", "mandatory employment terms",
    ]

    same_jurisdiction = (
        company_code is not None and company_code == employee_code
    ) or (
        company_code is None and employee_code is None
        and (company_raw or "").strip().lower() == (employee_raw or "").strip().lower()
        and bool((company_raw or "").strip())
    )

    company_steps, employee_steps = [], []

    # where the work is actually performed — drives the applicability gate and
    # decides which jurisdiction's minimum wage is territorially relevant
    work_country = plan.get("work_country") or employee_raw
    work_code = normalize_country(work_country) or employee_code

    def _company():
        return run_law_agent("Company Law", "company's jurisdiction",
                             company_code, contract, queries,
                             company_steps, country_label=company_raw,
                             work_country=work_country,
                             stated_pay=plan.get("stated_pay"),
                             governs_workplace=(company_code == work_code))

    def _employee():
        return run_law_agent("Employee Law", "employee's jurisdiction",
                             employee_code, contract, queries,
                             employee_steps, country_label=employee_raw,
                             work_country=work_country,
                             stated_pay=plan.get("stated_pay"),
                             governs_workplace=(employee_code == work_code))

    if same_jurisdiction:
        # Both countries identical: run one law agent (efficiency), reuse result.
        company_result = _company()
        employee_result = {"jurisdiction": company_result["jurisdiction"], "breaches": []}
        steps.extend(company_steps)
    else:
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_company = ex.submit(_company)
            f_employee = ex.submit(_employee)
            company_result = f_company.result()
            employee_result = f_employee.result()
        steps.extend(company_steps)
        steps.extend(employee_steps)

    # Supervisor validation gate: keep only genuine, citable violations.
    # Deterministic — no extra LLM call. Logged so the trace shows what each
    # law agent reported versus what the Supervisor accepted.
    raw_issues = _tag(company_result) + _tag(employee_result)
    issues, rejected = validate_breaches(raw_issues)
    steps.append(make_step(
        module="Supervisor",
        system_prompt="[Validation gate] Deterministic review of the findings returned by "
                      "Company Law and Employee Law. An entry is kept only if it self-declares "
                      "as a violation, cites a real statute, and does not read as a compliance note.",
        user_prompt=f"Received {len(raw_issues)} finding(s) from the law agents.",
        response={"accepted": len(issues), "rejected": len(rejected),
                  "rejected_details": rejected},
    ))
    return issues, company_result, employee_result


def _editor_reflection(contract: str, issues: list, original: str, steps: list):
    """Editor <-> Reflection inner loop. Returns (revised_contract, changes)."""
    draft = contract
    changes = []
    remaining = issues
    for i in range(1, MAX_REFLECTION_ITERS + 1):
        edited = run_editor(draft, remaining, steps, i)
        draft = edited["revised_contract"]
        changes.extend(edited["changes"])
        # pass the ORIGINAL contract so Reflection can catch regressions
        verdict = run_reflection(draft, remaining, steps, i, original_contract=original)
        if verdict["pass"]:
            break
        remaining = verdict["remaining_issues"]
    return draft, changes


def run_pipeline(prompt: str) -> dict:
    """Execute the full agent: Supervisor -> (Company Law || Employee Law) ->
    validation gate -> Editor <-> Reflection.

    Returns {"response": str, "steps": [...]} normally, or
    {"error": str, "steps": [...]} when the request cannot be served
    (e.g. an unsupported jurisdiction).
    """
    steps = []
    company_raw, employee_raw, contract_text = parse_input(prompt)
    supported = supported_countries_list()

    # 1) Supervisor: scope guard, jurisdictions, stated pay, query planning ---
    plan = _supervisor_plan(contract_text, company_raw, employee_raw, supported, steps)

    if not plan.get("in_scope", True):
        reason = (plan.get("reason")
                  or "This request is outside the scope of contract compliance review.")
        return {
            "response": f"**Out of scope.** {reason}\n\nThis agent reviews employment "
                        f"contracts/offer letters against local labor law. Please provide a "
                        f"contract plus the company and employee countries.",
            "steps": steps,
        }

    company_raw = plan.get("company_country") or company_raw
    employee_raw = plan.get("employee_country") or employee_raw
    company_code = normalize_country(company_raw)
    employee_code = normalize_country(employee_raw)

    # 2) Jurisdiction gate: both countries must be in the indexed RAG set ----
    unsupported = []
    if company_code is None:
        unsupported.append(f"company country: {_describe(company_raw)}")
    if employee_code is None:
        unsupported.append(f"employee country: {_describe(employee_raw)}")
    if unsupported:
        return {
            "error": (
                "Unsupported jurisdiction — " + "; ".join(unsupported) + ". "
                f"This agent only supports contracts where BOTH countries are among: {supported}."
            ),
            "steps": steps,
        }

    # 3) Company Law || Employee Law, then the Supervisor validation gate ----
    issues, company_result, employee_result = _run_law_agents(
        contract_text, plan, company_raw, employee_raw, company_code, employee_code, steps)

    # 4) Autonomous no-breach branch ----------------------------------------
    if not issues:
        jurisdictions = _join_jurisdictions(company_result, employee_result)
        response = (
            f"## ✅ No breaches found\n\n"
            f"The Company Law and Employee Law reviews found no labor-law breaches for "
            f"{jurisdictions}. The contract is returned unchanged.\n\n"
            f"---\n\n{contract_text}"
        )
        return {"response": response, "steps": steps}

    # 5) Editor <-> Reflection, then finalize -------------------------------
    draft, changes = _editor_reflection(contract_text, issues, contract_text, steps)
    response = _final_report(company_result, employee_result, issues, changes, draft)
    return {"response": response, "steps": steps}


# ── helpers ─────────────────────────────────────────────────────────────────────
# Phrases that reveal an entry is NOT a violation — either the model hedging
# ("no breach can be established") or affirming compliance ("within the limits
# of BGB 622(3)"). Backstop for when the model sets is_violation wrongly.
_NON_BREACH_MARKERS = (
    # hedging / nothing established
    "no concrete breach", "cannot be established", "could not be established",
    "could not be verified", "could not be retrieved", "not supported by",
    "do not include any", "do not contain any", "does not contain any",
    "no breach can be", "unable to verify", "record is unavailable",
    "cannot be confirmed", "no breach is established",
    # affirming the clause is fine
    "within the limits", "is consistent with", "complies with", "is compliant",
    "are within the", "is permitted", "is allowed", "no breach", "not a breach",
    "meets the requirement", "satisfies the requirement", "is lawful",
    "does not violate", "no violation",
)

_BAD_CITATIONS = {"", "n/a", "none", "null", "minimum-wage record",
                  "minimum_wage record", "wage check", "not applicable"}


def validate_breaches(issues: list) -> tuple:
    """Supervisor's central quality gate over the law agents' findings.

    Deterministic (no LLM). An entry survives only if it self-declares as a
    violation, carries a real statute citation, and does not read as a
    compliance note. Returns (accepted, rejected).
    """
    accepted, rejected = [], []
    for b in issues:
        if not isinstance(b, dict):
            rejected.append({"reason": "malformed entry", "entry": str(b)[:120]})
            continue

        # 1) self-declaration: the agent must assert this is a violation
        if b.get("is_violation") is False:
            rejected.append({"reason": "is_violation=false", "clause": b.get("clause", "")[:80]})
            continue

        # 2) must cite a real statute
        cite = (b.get("law_citation") or "").strip().lower()
        if cite in _BAD_CITATIONS:
            rejected.append({"reason": "no usable law_citation", "clause": b.get("clause", "")[:80]})
            continue

        # 3) backstop: text that reads as a compliance note is not a breach
        blob = f"{b.get('issue', '')} {b.get('violated_requirement', '')} {b.get('clause', '')}".lower()
        marker = next((m for m in _NON_BREACH_MARKERS if m in blob), None)
        if marker:
            rejected.append({"reason": f"reads as compliant ('{marker}')",
                             "clause": b.get("clause", "")[:80]})
            continue

        accepted.append(b)
    return accepted, rejected


def _describe(raw) -> str:
    """Readable label for a country that failed the supported-jurisdiction check."""
    s = (raw or "").strip()
    if not s or s.lower() in {"null", "none", "(not given)", "unknown"}:
        return "could not be determined from the input or the contract"
    return f"'{s}' is not supported"


def _tag(result: dict) -> list:
    out = []
    for b in result.get("breaches", []):
        b = dict(b)
        b.setdefault("jurisdiction", result.get("jurisdiction"))
        out.append(b)
    return out


def _join_jurisdictions(company_result, employee_result) -> str:
    labels = []
    for r in (company_result, employee_result):
        j = r.get("jurisdiction")
        if j and j not in labels:
            labels.append(j)
    return " and ".join(labels) if labels else "the specified jurisdictions"


def _final_report(company_result, employee_result, issues, changes, final_contract) -> str:
    lines = ["## ⚖️ Compliance Review — Contract Corrected", ""]
    lines.append(f"**Jurisdictions reviewed:** {_join_jurisdictions(company_result, employee_result)}")
    lines.append(f"**Breaches found:** {len(issues)}  ·  **Edits applied:** {len(changes)}")
    lines.append("")
    lines.append("### Breaches found")
    for b in issues:
        sev = (b.get("severity") or "").upper()
        lines.append(
            f"- **[{sev}] {b.get('jurisdiction','')}** — {b.get('issue','')} "
            f"_(cite: {b.get('law_citation','n/a')})_"
        )
    lines.append("")
    lines.append("### Changes made (plain English)")
    if changes:
        for c in changes:
            lines.append(f"- **{c.get('clause','')}**: {c.get('change','')} — _{c.get('why','')}_")
    else:
        lines.append("- (no change log returned)")
    lines.append("")
    lines.append("### ✅ Corrected contract")
    lines.append("")
    lines.append(final_contract)
    return "\n".join(lines)
