"""Seed the Supabase reference tables (run once, or to refresh rates).

Create BOTH tables first — paste this into the Supabase SQL editor and Run:

    create table if not exists minimum_wage (
        country  text primary key,
        currency text,
        amount   numeric,
        unit     text,
        period   text
    );

    create table if not exists currency_rates (
        currency   text primary key,
        to_usd     numeric not null,
        updated_on date
    );

Then run:
    python scripts/seed_minwage.py

`to_usd` = how many US dollars one unit of that currency is worth.
NOTE: these are STATIC reference rates, not a live FX feed. Refresh them by
editing RATES below and re-running this script.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config import SUPABASE_URL, SUPABASE_KEY

# country label -> record. Labels match config.JURISDICTIONS[...]["label"].
SEED = [
    {"country": "United States", "currency": "USD", "amount": 7.25, "unit": "hour", "period": "hour"},
    {"country": "United Kingdom", "currency": "GBP", "amount": 11.44, "unit": "hour", "period": "hour"},
    {"country": "Germany", "currency": "EUR", "amount": 12.82, "unit": "hour", "period": "hour"},
    {"country": "Israel", "currency": "ILS", "amount": 6247.67, "unit": "month", "period": "month"},
    # extra examples from the data source table
    {"country": "Venezuela", "currency": "VEF", "amount": 13000000, "unit": "month", "period": "month"},
    {"country": "Laos", "currency": "LAK", "amount": 2500000, "unit": "month", "period": "month"},
    {"country": "Uzbekistan", "currency": "UZS", "amount": 1271000, "unit": "month", "period": "month"},
]

# Currencies of the four supported jurisdictions. Static reference rates.
RATES = [
    {"currency": "USD", "to_usd": 1.00, "updated_on": "2026-08-08"},
    {"currency": "EUR", "to_usd": 1.09, "updated_on": "2026-08-08"},
    {"currency": "GBP", "to_usd": 1.27, "updated_on": "2026-08-08"},
    {"currency": "ILS", "to_usd": 0.27, "updated_on": "2026-08-08"},
]


def main():
    if not (SUPABASE_URL and SUPABASE_KEY):
        print("SUPABASE_URL / SUPABASE_KEY not set. Fill .env first.")
        sys.exit(1)
    from supabase import create_client
    client = create_client(SUPABASE_URL, SUPABASE_KEY)

    res = client.table("minimum_wage").upsert(SEED).execute()
    print(f"Upserted {len(res.data or SEED)} rows into minimum_wage.")

    try:
        res = client.table("currency_rates").upsert(RATES).execute()
        print(f"Upserted {len(res.data or RATES)} rows into currency_rates.")
    except Exception as e:
        print("currency_rates upsert FAILED -- did you create the table? "
              "See the SQL at the top of this file.")
        print(f"  {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
