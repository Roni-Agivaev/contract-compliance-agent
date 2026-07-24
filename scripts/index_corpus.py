"""Index the legal corpus into Pinecone (run once).

For each jurisdiction PDF (+ the optional ILO baseline), extract text, chunk it
(512-token chunks, 100 overlap), embed with text-embedding-3-small, and upsert
into that jurisdiction's namespace with citable metadata.

Usage:
    python scripts/index_corpus.py --data-dir "path/to/Data RAG/Data RAG"

Creates the Pinecone index if it does not exist.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import (
    get_embeddings, PINECONE_API_KEY, PINECONE_INDEX_NAME, EMBEDDING_DIMENSION,
    CHUNK_SIZE, CHUNK_OVERLAP, JURISDICTIONS, ILO_NAMESPACE, ILO_SOURCE,
)


def ensure_index():
    from pinecone import Pinecone, ServerlessSpec
    pc = Pinecone(api_key=PINECONE_API_KEY)
    existing = [i["name"] for i in pc.list_indexes()]
    if PINECONE_INDEX_NAME not in existing:
        print(f"Creating index {PINECONE_INDEX_NAME} ...")
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=EMBEDDING_DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
    return pc.Index(PINECONE_INDEX_NAME)


def pdf_to_text(path: str) -> str:
    reader = PdfReader(path)
    out = []
    for page in reader.pages:
        try:
            out.append(page.extract_text() or "")
        except Exception:
            out.append("")
    return "\n".join(out)


def chunk(text: str):
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    return splitter.split_text(text)


def index_source(index, emb, path, namespace, source_name):
    if not os.path.exists(path):
        print(f"  SKIP (missing): {path}")
        return 0
    text = pdf_to_text(path)
    chunks = [c for c in chunk(text) if c.strip()]
    print(f"  {source_name}: {len(chunks)} chunks -> namespace '{namespace}'")
    batch, ids, metas = [], [], []
    for i, c in enumerate(chunks):
        batch.append(c)
        ids.append(f"{namespace}-{i}")
        metas.append({"source": source_name, "section": f"chunk {i}", "text": c})

    # embed + upsert in batches of 100
    total = 0
    for start in range(0, len(batch), 100):
        sub = batch[start:start + 100]
        vecs = emb.embed_documents(sub)
        payload = [
            {"id": ids[start + j], "values": vecs[j], "metadata": metas[start + j]}
            for j in range(len(sub))
        ]
        index.upsert(vectors=payload, namespace=namespace)
        total += len(sub)
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True, help="folder containing the source PDFs")
    args = ap.parse_args()

    index = ensure_index()
    emb = get_embeddings()

    grand = 0
    for code, cfg in JURISDICTIONS.items():
        print(f"[{code}] {cfg['label']}")
        grand += index_source(
            index, emb, os.path.join(args.data_dir, cfg["pdf"]),
            cfg["namespace"], cfg["source_name"],
        )

    # ILO baseline (optional; add the PDF to run it)
    print("[ILO] baseline")
    grand += index_source(
        index, emb, os.path.join(args.data_dir, ILO_SOURCE["pdf"]),
        ILO_NAMESPACE, ILO_SOURCE["source_name"],
    )

    print(f"\nDone. Upserted {grand} vectors total.")


if __name__ == "__main__":
    main()
