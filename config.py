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
TOP_K = 6                 # chunks retrieved per law agent, before dedup
MAX_REFLECTION_ITERS = 3  # Editor <-> Reflection loop cap (slide 6: "<= N iterations")

# Outer re-audit loop: after the Editor returns a corrected contract the whole
# agent runs again over it, until no breaches remain or this many passes have run.
MAX_AGENT_PASSES = 3
# Never start another pass this late into the request — Vercel hard-kills at 300s
# and would return nothing at all, so we stop and return the best contract we have.
PASS_TIME_BUDGET_SECONDS = 210

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
    return ChatOpenAI(
        model=CHAT_MODEL,
        openai_api_key=LLMOD_API_KEY,
        openai_api_base=LLMOD_BASE_URL,
        temperature=temperature,
    )


def get_index():
    """Lazy Pinecone index handle (import inside so the module loads without the dep)."""
    from pinecone import Pinecone

    pc = Pinecone(api_key=PINECONE_API_KEY)
    return pc.Index(PINECONE_INDEX_NAME)
