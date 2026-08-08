"""MinimumWageTool — deterministic (no LLM) wage + currency lookups from Supabase.

Two Supabase tables back this module (both seeded by scripts/seed_minwage.py):

  minimum_wage   country (pk), currency, amount, unit, period
  currency_rates currency (pk), to_usd, updated_on

The tool returns the statutory minimum already normalised to per-hour AND
per-month in the local currency, plus the FX rates needed to convert a
contract's pay into that currency. All arithmetic happens here, not in the LLM.

If Supabase is unavailable the tool degrades gracefully: the law agent is told
to skip the wage check rather than invent a finding.
"""
from config import SUPABASE_URL, SUPABASE_KEY, JURISDICTIONS

# Full-time month: 40 h/week * 52 weeks / 12 months
HOURS_PER_MONTH = 173.33

_client = None
_rates_cache = None


def _get_client():
    global _client
    if _client is None:
        if not (SUPABASE_URL and SUPABASE_KEY):
            return None
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def get_currency_rates() -> dict:
    """{"USD": 1.0, "EUR": 1.09, ...} — how many USD one unit of each is worth.

    Cached for the process; returns {} if the table is unreachable.
    """
    global _rates_cache
    if _rates_cache is not None:
        return _rates_cache
    client = _get_client()
    if client is None:
        _rates_cache = {}
        return _rates_cache
    try:
        res = client.table("currency_rates").select("currency,to_usd").execute()
        _rates_cache = {r["currency"]: float(r["to_usd"]) for r in (res.data or [])}
    except Exception:
        _rates_cache = {}
    return _rates_cache


def convert(amount: float, from_currency: str, to_currency: str, rates: dict = None):
    """Convert an amount between two currencies. Returns None if not possible."""
    if amount is None or not from_currency or not to_currency:
        return None
    if from_currency == to_currency:
        return round(float(amount), 2)
    rates = get_currency_rates() if rates is None else rates
    if from_currency not in rates or to_currency not in rates:
        return None
    usd = float(amount) * rates[from_currency]
    return round(usd / rates[to_currency], 2)


def evaluate_wage(stated_pay: dict, wage: dict) -> dict:
    """Deterministically compare the contract's pay to the statutory floor.

    The LLM must NOT do this arithmetic — currency conversion and hour/month
    normalisation are done here and handed to the agent as a finished verdict.
    """
    if not (wage or {}).get("found"):
        return {"checked": False, "reason": "no statutory minimum available"}
    if not stated_pay:
        return {"checked": False, "reason": "contract pay not identified"}
    try:
        amount = float(stated_pay.get("amount"))
    except (TypeError, ValueError):
        return {"checked": False, "reason": "pay amount not numeric"}

    cur = (stated_pay.get("currency") or "").upper()
    period = (stated_pay.get("period") or "").lower()
    local = wage["statutory_minimum"]["currency"]

    converted = convert(amount, cur, local)
    if converted is None:
        return {"checked": False, "reason": f"no FX rate to convert {cur} to {local}"}

    norm = wage["normalized"]
    if period.startswith("hour"):
        floor, basis, pay = norm.get(f"per_hour_{local}"), "per hour", converted
    elif period.startswith(("year", "annum", "annual")):
        floor, basis, pay = norm.get(f"per_month_{local}"), "per month", round(converted / 12, 2)
    else:  # treat anything else as monthly
        floor, basis, pay = norm.get(f"per_month_{local}"), "per month", converted

    if floor is None:
        return {"checked": False, "reason": "could not normalise the statutory minimum"}

    compliant = pay >= floor
    return {
        "checked": True,
        "contract_pay": f"{amount} {cur} {stated_pay.get('period')}",
        "converted_pay": f"{pay} {local} {basis}",
        "statutory_floor": f"{floor} {local} {basis}",
        "compliant": compliant,
        "verdict": (
            f"PAY MEETS THE MINIMUM ({pay} >= {floor} {local} {basis}) — do NOT report a wage breach."
            if compliant else
            f"PAY IS BELOW THE MINIMUM ({pay} < {floor} {local} {basis}) — report a wage breach."
        ),
    }


def lookup_minimum_wage(country_code: str) -> dict:
    """Statutory minimum wage for a jurisdiction, normalised and FX-annotated."""
    label = JURISDICTIONS.get(country_code, {}).get("label", country_code)
    client = _get_client()
    if client is None:
        return {"found": False, "country": label,
                "note": "minimum_wage DB not configured; skip the wage check."}
    try:
        res = (
            client.table("minimum_wage").select("*")
            .eq("country", label).limit(1).execute()
        )
        rows = res.data or []
        if not rows:
            return {"found": False, "country": label,
                    "note": f"No minimum-wage row for {label}; skip the wage check."}

        r = rows[0]
        amount = float(r["amount"])
        currency = r.get("currency")
        unit = (r.get("unit") or r.get("period") or "").lower()

        # normalise to per-hour and per-month in the local currency
        if unit.startswith("hour"):
            per_hour, per_month = amount, round(amount * HOURS_PER_MONTH, 2)
        elif unit.startswith("month"):
            per_hour, per_month = round(amount / HOURS_PER_MONTH, 2), amount
        else:
            per_hour, per_month = None, None

        # FX rates expressed against the minimum wage's own currency, so the
        # agent can convert the CONTRACT's pay into it with one multiplication
        rates = get_currency_rates()
        fx = {}
        if currency in rates:
            for cur in rates:
                if cur != currency:
                    fx[cur] = round(rates[cur] / rates[currency], 4)

        return {
            "found": True,
            "country": label,
            "statutory_minimum": {"amount": amount, "currency": currency, "unit": unit},
            "normalized": {f"per_hour_{currency}": per_hour,
                           f"per_month_{currency}": per_month},
            "fx_to_local": fx,
            "note": (f"Full-time month = {HOURS_PER_MONTH} hours. To compare, multiply the "
                     f"contract's pay by fx_to_local[<contract currency>] to get {currency}."),
        }
    except Exception as e:  # pragma: no cover - network/DB errors
        return {"found": False, "country": label,
                "note": f"minimum_wage lookup error ({e}); skip the wage check."}
