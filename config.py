"""Shared configuration and client helpers for the Contract Compliance Agent.

All secrets come from environment variables (see .env.example). Nothing here is
committed with real values.
"""
import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

load_dotenv()

# ── secrets (from env) ─────────────────────────────────────────────────────────
LLMOD_API_KEY = os.getenv("LLMOD_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ── LLM provider (LLMod.ai, OpenAI-compatible) ─────────────────────────────────
LLMOD_BASE_URL = "https://api.llmod.ai/v1"
CHAT_MODEL = "MB5R2CF-azure/gpt-5.4-mini"
EMBEDDING_MODEL = "MB5R2CF-azure/text-embedding-3-small"
EMBEDDING_DIMENSION = 1536

# ── retrieval / chunking ───────────────────────────────────────────────────────
CHUNK_SIZE = 512
CHUNK_OVERLAP = 100
TOP_K = 6                 # candidates fetched per query, per namespace
# Retrieval is allocated per query rather than as one global top-K pool: without
# a quota a single high-scoring topic can take every slot, leaving other topics
# with no statutory basis at all — and a law agent may only cite provisions that
# were actually retrieved, so an un-retrieved topic becomes silently unauditable.
PER_QUERY_K = 2           # passages guaranteed to each query/topic
MAX_PASSAGES = 24         # overall cap per law agent, bounds prompt size
# "per_query" = every query gets its own PER_QUERY_K slots (quota).
# "global"    = pool all queries and keep the MAX_PASSAGES highest scoring.
RETRIEVAL_MODE = "per_query"
# Use the fixed query list below instead of the Supervisor's per-run queries.
USE_FIXED_QUERIES = True

# Retrieval queries are FIXED rather than written by the Supervisor each run.
# LLM-generated queries were measured as the dominant source of run-to-run
# variance: different wording embeds differently, retrieves different statutes,
# and a law agent may only cite provisions it actually received. A fixed list
# embeds identically every time, so the evidence base stops moving.
# One entry per compliance dimension the law agents are expected to check.
FIXED_SEARCH_QUERIES = [
    "minimum wage and rates of pay",
    "maximum weekly working hours and working time limits",
    "overtime pay and compensation for additional hours",
    "paid annual leave and holiday entitlement",
    "notice period and termination of employment",
    "probationary period and dismissal during probation",
    "sick pay and continued remuneration during illness",
    "post-termination restraint, non-compete and compensation for it",
    "written statement of employment particulars and form requirements",
    "deductions from wages and equal treatment of employees",
    # cross-border dimensions: added after a coverage experiment showed the
    # generic particulars query never retrieved ERA 1996 s.1(4)(k)
    "choice of law clause and mandatory employment protections that cannot be excluded",
    "particulars for an employee working outside the country, period abroad and currency of pay",
]

# Best-effort determinism. gpt-5 models reject every temperature except 1 and
# Azure rejects top_p, so `seed` is the only sampling control available: the same
# seed biases the backend toward the same generation. Set to None to disable.
LLM_SEED = 42
MAX_REFLECTION_ITERS = 3  # Editor <-> Reflection loop cap (slide 6: "<= N iterations")

PINECONE_INDEX_NAME = "contract-compliance"
ILO_NAMESPACE = "ilo_baseline"   # universal floor, queried alongside every jurisdiction

# ── jurisdictions ──────────────────────────────────────────────────────────────
# Adjustable subset. Add a jurisdiction = drop a PDF in data/ and add an entry here.
# `aliases` are lower-cased spellings the user might type for the country.
JURISDICTIONS = {
    "US": {
        "label": "United States",
        "namespace": "us_flsa",
        "source_name": "US Fair Labor Standards Act (FLSA)",
        "pdf": "US_FairLaborStandAct.pdf",
        "aliases": ["us", "u.s.", "u.s.a.", "usa", "united states",
                    "united states of america", "america"],
    },
    "UK": {
        "label": "United Kingdom",
        "namespace": "uk_era",
        "source_name": "UK Employment Rights Act 1996",
        "pdf": "uk_Employment Rights.pdf",
        "aliases": ["uk", "u.k.", "united kingdom", "britain", "great britain",
                    "england", "scotland", "wales"],
    },
    "DE": {
        "label": "Germany",
        "namespace": "de_bgb",
        "source_name": "German Civil Code (BGB)",
        "pdf": "German Civil Code.pdf",
        "aliases": ["de", "germany", "deutschland", "german"],
    },
    "IL": {
        "label": "Israel",
        "namespace": "il_guide",
        "source_name": "Israel Ministry of Aliyah & Integration Employment Guide",
        "pdf": "employment_en_israel.pdf",
        "aliases": ["il", "israel", "israeli"],
    },
}

# ILO baseline is indexed into ILO_NAMESPACE from this file.
ILO_SOURCE = {
    "source_name": "ILO 1998 Declaration on Fundamental Principles and Rights at Work",
    "pdf": "ILO_1998_Declaration.pdf",  # user to add; optional universal baseline
}


def normalize_country(text: str):
    """Map a free-text country name to a jurisdiction code (US/UK/DE/IL) or None."""
    if not text:
        return None
    t = text.strip().lower()
    for code, cfg in JURISDICTIONS.items():
        if t == code.lower() or t in cfg["aliases"] or t == cfg["label"].lower():
            return code
    # loose contains match (e.g. "based in Germany")
    for code, cfg in JURISDICTIONS.items():
        if cfg["label"].lower() in t or any(a in t for a in cfg["aliases"] if len(a) > 3):
            return code
    return None


# ── client helpers ─────────────────────────────────────────────────────────────
def get_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        openai_api_key=LLMOD_API_KEY,
        openai_api_base=LLMOD_BASE_URL,
        chunk_size=256,
    )


def get_llm(temperature: float = 1) -> ChatOpenAI:
    extra = {} if LLM_SEED is None else {"seed": LLM_SEED}
    return ChatOpenAI(
        model=CHAT_MODEL,
        openai_api_key=LLMOD_API_KEY,
        openai_api_base=LLMOD_BASE_URL,
        temperature=temperature,
        **extra,
    )


def get_index():
    """Lazy Pinecone index handle (import inside so the module loads without the dep)."""
    from pinecone import Pinecone

    pc = Pinecone(api_key=PINECONE_API_KEY)
    return pc.Index(PINECONE_INDEX_NAME)
