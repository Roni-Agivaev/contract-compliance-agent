"""Regenerate agent_examples.json from REAL runs of the live agent.

The examples served by GET /api/agent_info are captured from actual
POST /api/execute calls — they are never hand-written — so the documented
behaviour always matches what the agent really does.

Usage (with the API running locally or in production):
    python scripts/build_agent_examples.py --base http://127.0.0.1:8000

Each example records the prompt, the full response, and the complete ordered
list of steps. Only the bulk "RETRIEVED ... LAW PASSAGES" block inside a user
prompt is abbreviated (it is many KB of verbatim statute text); the truncation
is marked inline so nothing is silently hidden.
"""
import argparse
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "agent_examples.json")

PASSAGE_KEEP = 700  # chars of retrieved statute text to keep per prompt


def execute(base, prompt):
    req = urllib.request.Request(
        base.rstrip("/") + "/api/execute", method="POST",
        data=json.dumps({"prompt": prompt}).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def abbreviate_passages(user_prompt: str) -> str:
    """Shorten the retrieved-statute block; leave everything else intact."""
    m = re.search(r"(RETRIEVED .*? LAW PASSAGES:\n)(.*?)(\n\nWAGE CHECK)",
                  user_prompt, re.DOTALL)
    if not m:
        return user_prompt
    body = m.group(2)
    if len(body) <= PASSAGE_KEEP:
        return user_prompt
    short = (body[:PASSAGE_KEEP].rstrip() +
             f"\n\n...[{len(body) - PASSAGE_KEEP} further characters of retrieved "
             f"statute text omitted from this example]...")
    return user_prompt[:m.start(2)] + short + user_prompt[m.end(2):]


def clean_steps(steps):
    out = []
    for s in steps or []:
        out.append({
            "module": s["module"],
            "prompt": {
                "System_prompt": s["prompt"]["System_prompt"],
                "User_prompt": abbreviate_passages(s["prompt"]["User_prompt"]),
            },
            "response": s["response"],
        })
    return out


def corrected_contract(response: str):
    m = re.search(r"### ✅ Corrected contract\s*\n+(.*)", response or "", re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"\n---\n+(.*)", response or "", re.DOTALL)
    return m.group(1).strip() if m else None


def build_example(result, prompt, title=None, note=None):
    """One prompt_examples entry.

    Exactly the three keys the assignment specifies — prompt, full_response,
    steps. `title`/`note` are accepted for callers' readability but deliberately
    NOT emitted, so the payload matches the documented response format.
    """
    return {
        "prompt": prompt,
        "full_response": result.get("response") or result.get("error"),
        "steps": clean_steps(result.get("steps")),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--contract", required=True,
                    help="path to the non-compliant contract text used for example 1")
    args = ap.parse_args()

    contract = open(args.contract, encoding="utf-8").read().strip()

    p1 = (f"Company country: United Kingdom\nEmployee country: Germany\n"
          f"Contract / Offer text: {contract}")
    r1 = execute(args.base, p1)
    print(f"example 1: status={r1.get('status')} steps={len(r1.get('steps') or [])}")

    fixed = corrected_contract(r1.get("response"))
    p2 = (f"Company country: United Kingdom\nEmployee country: Germany\n"
          f"Contract / Offer text: {fixed}")
    r2 = execute(args.base, p2)
    print(f"example 2: status={r2.get('status')} steps={len(r2.get('steps') or [])}")

    p3 = ("Company country: France\nEmployee country: Spain\n"
          "Contract / Offer text: EMPLOYMENT AGREEMENT between Lumiere SARL, registered in "
          "Paris, France, and Ms. Carmen Delgado, residing in Valencia, Spain, who performs "
          "all work from Valencia. 1. Position: Data Analyst, full-time, 40 hours per week. "
          "2. Compensation: EUR 1,500 gross per month. 3. Termination: the Company may "
          "terminate immediately without notice. 4. Governing law: the laws of France govern "
          "this agreement.")
    r3 = execute(args.base, p3)
    print(f"example 3: status={r3.get('status')} steps={len(r3.get('steps') or [])}")

    examples = [
        build_example(r1, p1, "Non-compliant cross-border contract (UK company, employee in Germany)",
                      "A deliberately abusive contract. Company Law and Employee Law run in "
                      "parallel, the Supervisor validation gate filters the findings, and the "
                      "Editor/Reflection loop rewrites the offending clauses."),
        build_example(r2, p2, "Re-audit of the corrected contract",
                      "The contract returned by example 1 is fed straight back in, showing how "
                      "the agent behaves on a second pass over its own output."),
        build_example(r3, p3, "Unsupported jurisdictions (error response)",
                      "Neither France nor Spain is in the indexed legal corpus, so the Supervisor "
                      "stops after one LLM call and returns a structured error."),
    ]

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"prompt_examples": examples}, f, ensure_ascii=False, indent=2)
    print(f"wrote {OUT} ({os.path.getsize(OUT):,} bytes)")


if __name__ == "__main__":
    main()
