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
    PER_QUERY_K,
    MAX_PASSAGES,
    RETRIEVAL_MODE,
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

    Retrieval budget is allocated PER QUERY, not as one global top-K pool. Each
    query is guaranteed PER_QUERY_K passages of its own, so a high-scoring topic
    can no longer take every slot and leave other topics with no statutory basis.
    That matters because a law agent may only cite provisions that were actually
    retrieved — an un-retrieved topic is silently unauditable for that run.

    Queries the country namespace + the ILO baseline namespace, dedupes by
    (source, section), and caps the total at MAX_PASSAGES.
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

    if RETRIEVAL_MODE == "global":
        # Pool every query's hits and keep the MAX_PASSAGES highest scoring.
        best = {}
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
        ranked = sorted(best.values(), key=lambda p: p["score"], reverse=True)
        return ranked[:MAX_PASSAGES]

    selected = {}  # (source, section) -> passage dict
    for q in queries:
        if len(selected) >= MAX_PASSAGES:
            break
        vec = emb.embed_query(q)

        # this query's own candidate pool, across every namespace
        pool = []
        for namespace in namespaces:
            pool.extend(_query_namespace(index, vec, namespace, top_k))
        pool.sort(key=lambda m: m.score, reverse=True)

        added = 0
        for m in pool:
            if added >= PER_QUERY_K or len(selected) >= MAX_PASSAGES:
                break
            md = m.metadata or {}
            key = (md.get("source", "?"), md.get("section", ""))
            if key in selected:
                # already retrieved by an earlier query — keep the better score,
                # but do not spend this query's quota on a passage we already have
                if m.score > selected[key]["score"]:
                    selected[key]["score"] = float(m.score)
                continue
            selected[key] = {
                "source": md.get("source", "?"),
                "section": md.get("section", ""),
                "text": md.get("text", md.get("chunk", "")),
                "score": float(m.score),
            }
            added += 1

    return sorted(selected.values(), key=lambda p: p["score"], reverse=True)


def format_context(passages) -> str:
    """Render retrieved passages into a compact, citable context block."""
    parts = []
    for p in passages:
        head = p["source"]
        if p.get("section"):
            head += f" — {p['section']}"
        parts.append(f"[{head}]\n{p['text']}")
    return "\n\n".join(parts) if parts else "(no legal passages retrieved)"
