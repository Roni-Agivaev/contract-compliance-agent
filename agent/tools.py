"""MinimumWageTool — deterministic (no LLM) minimum-wage lookup from Supabase.

Table `minimum_wage` is seeded once by scripts/seed_minwage.py from
worldpopulationreview's 2026 minimum-wage data. Rows:
    country (text), currency (text), amount (numeric), unit (text), period (text)

If Supabase is unavailable or the country is missing, returns a graceful
"unknown" result so the pipeline can continue.
"""
from config import SUPABASE_URL, SUPABASE_KEY, JURISDICTIONS

_client = None


def _get_client():
    global _client
    if _client is None:
        if not (SUPABASE_URL and SUPABASE_KEY):
            return None
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def lookup_minimum_wage(country_code: str) -> dict:
    """Return the minimum-wage record for a jurisdiction code (US/UK/DE/IL/...).

    Result shape:
        {"found": bool, "country": str, "amount": float|None,
         "currency": str|None, "unit": str|None, "note": str}
    """
    label = JURISDICTIONS.get(country_code, {}).get("label", country_code)
    client = _get_client()
    if client is None:
        return {"found": False, "country": label, "amount": None,
                "currency": None, "unit": None,
                "note": "minimum_wage DB not configured; wage check skipped."}
    try:
        res = (
            client.table("minimum_wage")
            .select("*")
            .eq("country", label)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            return {"found": False, "country": label, "amount": None,
                    "currency": None, "unit": None,
                    "note": f"No 2026 minimum-wage row for {label}."}
        r = rows[0]
        return {
            "found": True,
            "country": label,
            "amount": r.get("amount"),
            "currency": r.get("currency"),
            "unit": r.get("unit") or r.get("period"),
            "note": f"2026 statutory minimum wage for {label}.",
        }
    except Exception as e:  # pragma: no cover - network/DB errors
        return {"found": False, "country": label, "amount": None,
                "currency": None, "unit": None,
                "note": f"minimum_wage lookup error: {e}"}
