"""Seed the Supabase `minimum_wage` table (run once).

Create the table first (SQL, run in the Supabase SQL editor):

    create table if not exists minimum_wage (
        country  text primary key,
        currency text,
        amount   numeric,
        unit     text,
        period   text
    );

Then run:
    python scripts/seed_minwage.py

Values below are seed figures for the supported jurisdictions (verify/update to
the latest 2026 figures as needed). The MinimumWageTool reads this table by the
country label used in config.JURISDICTIONS.
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


def main():
    if not (SUPABASE_URL and SUPABASE_KEY):
        print("SUPABASE_URL / SUPABASE_KEY not set. Fill .env first.")
        sys.exit(1)
    from supabase import create_client
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    res = client.table("minimum_wage").upsert(SEED).execute()
    print(f"Upserted {len(res.data or SEED)} rows into minimum_wage.")


if __name__ == "__main__":
    main()
