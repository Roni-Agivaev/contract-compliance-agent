"""ComplianceRetriever — Pinecone retrieval for a jurisdiction (no chat LLM).

Given search queries + a jurisdiction code, embed the queries, query that
jurisdiction's namespace plus the ILO baseline namespace, dedup by source
section, and return compact legal passages for the law agents to reason over.
"""
from config import (
    get_embeddings,
    get_index,
    ILO_NAMESPACE,
    JURISDICTIONS,
    TOP_K,
)


def _query_namespace(index, vector, namespace, top_k):
    try:
        res = index.query(
            vector=vector,
            top_k=top_k,
            include_metadata=True,
            namespace=namespace,
        )
        return list(res.matches)
    except Exception:
        return []


def retrieve(queries, country_code: str, top_k: int = TOP_K) -> list:
    """Return a list of passage dicts: {source, section, text, score}.

    Queries the country namespace + the ILO baseline namespace. Dedups by
    (source, section), keeping the highest-scoring passage.
    """
    if isinstance(queries, str):
        queries = [queries]
    queries = [q for q in queries if q and q.strip()] or ["employment contract compliance"]

    emb = get_embeddings()
    index = get_index()

    namespaces = []
    ns = JURISDICTIONS.get(country_code, {}).get("namespace")
    if ns:
        namespaces.append(ns)
    namespaces.append(ILO_NAMESPACE)

    best = {}  # (source, section) -> match-like dict
    for q in queries:
        vec = emb.embed_query(q)
        for namespace in namespaces:
            for m in _query_namespace(index, vec, namespace, top_k):
                md = m.metadata or {}
                key = (md.get("source", "?"), md.get("section", ""))
                if key not in best or m.score > best[key]["score"]:
                    best[key] = {
                        "source": md.get("source", "?"),
                        "section": md.get("section", ""),
                        "text": md.get("text", md.get("chunk", "")),
                        "score": float(m.score),
                    }

    passages = sorted(best.values(), key=lambda p: p["score"], reverse=True)
    return passages[:top_k]


def format_context(passages) -> str:
    """Render retrieved passages into a compact, citable context block."""
    parts = []
    for p in passages:
        head = p["source"]
        if p.get("section"):
            head += f" — {p['section']}"
        parts.append(f"[{head}]\n{p['text']}")
    return "\n\n".join(parts) if parts else "(no legal passages retrieved)"
