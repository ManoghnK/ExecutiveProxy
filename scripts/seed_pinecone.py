"""
seed_pinecone.py — Embed policy docs and upsert into Pinecone.

Uses Amazon Nova multimodal embeddings (amazon.nova-2-multimodal-embeddings-v1:0)
to generate vectors, then upserts into the Pinecone serverless index.

Required IAM permissions for the executing identity:
  - bedrock:InvokeModel on amazon.nova-2-multimodal-embeddings-v1:0

Usage:
    pip install pinecone boto3 python-dotenv
    python seed_pinecone.py
"""

import os
import json
import uuid
import re
import boto3
from pathlib import Path
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

load_dotenv(Path(__file__).parent.parent / ".env")

# ── Config ────────────────────────────────────────────────────────────────────
AWS_REGION        = os.environ["AWS_REGION"]
PINECONE_API_KEY  = os.environ["PINECONE_API_KEY"]
INDEX_NAME        = os.environ["PINECONE_INDEX_NAME"]
EMBEDDING_MODEL   = "amazon.titan-embed-text-v2:0"
EMBEDDING_DIM     = 1024  # Enforcing 1024 for Titan v2
CHUNK_SIZE        = 400   # tokens approx — sweet spot for RAG precision
CHUNK_OVERLAP     = 50

POLICY_DOCS_DIR   = Path(__file__).parent / "policy_docs"

bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)


# ── Chunking ──────────────────────────────────────────────────────────────────
def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Split text into overlapping chunks by word count.
    Overlap ensures context isn't lost at chunk boundaries.
    """
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def extract_section_header(chunk: str) -> str:
    """Pull the nearest markdown header for metadata context."""
    match = re.search(r"#{1,3} (.+)", chunk)
    return match.group(1).strip() if match else "General"


# ── Embedding ─────────────────────────────────────────────────────────────────
def get_embedding(text: str) -> list[float]:
    """
    Call Titan Embeddings v2 via Bedrock.
    Returns a 1024-dim float vector.
    """
    body = json.dumps({
        "inputText": text,
        "dimensions": EMBEDDING_DIM,
        "normalize": True
    })
    response = bedrock.invoke_model(
        modelId=EMBEDDING_MODEL,
        body=body,
        contentType="application/json",
        accept="application/json",
    )
    result = json.loads(response["body"].read())
    return result["embedding"]


# ── Pinecone ──────────────────────────────────────────────────────────────────
def get_or_create_index(pc: Pinecone) -> object:
    """Create the index if it doesn't exist, return the Index object."""
    existing = [idx.name for idx in pc.list_indexes()]
    if INDEX_NAME not in existing:
        print(f"Creating Pinecone index: {INDEX_NAME}")
        pc.create_index(
            name=INDEX_NAME,
            dimension=EMBEDDING_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        print("Index created.")
    else:
        print(f"Index '{INDEX_NAME}' already exists — upserting into it.")
    return pc.Index(INDEX_NAME)


# ── Main ──────────────────────────────────────────────────────────────────────
def seed():
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = get_or_create_index(pc)

    doc_files = list(POLICY_DOCS_DIR.glob("*.md"))
    if not doc_files:
        raise FileNotFoundError(f"No .md files found in {POLICY_DOCS_DIR}")

    all_vectors = []

    for doc_path in doc_files:
        doc_name = doc_path.stem  # e.g. "hr_policy"
        print(f"\nProcessing: {doc_path.name}")
        text = doc_path.read_text(encoding="utf-8")
        chunks = chunk_text(text)
        print(f"  → {len(chunks)} chunks")

        for i, chunk in enumerate(chunks):
            print(f"  Embedding chunk {i+1}/{len(chunks)}...", end="\r")
            vector = get_embedding(chunk)
            section = extract_section_header(chunk)

            all_vectors.append({
                "id": f"{doc_name}_{i}_{uuid.uuid4().hex[:8]}",
                "values": vector,
                "metadata": {
                    "source": doc_name,
                    "section": section,
                    "chunk_index": i,
                    "text": chunk[:1000],  # store first 1000 chars for retrieval
                },
            })

    # Upsert in batches of 100 (Pinecone limit)
    batch_size = 100
    total = len(all_vectors)
    print(f"\nUpserting {total} vectors to Pinecone in batches of {batch_size}...")

    for start in range(0, total, batch_size):
        batch = all_vectors[start : start + batch_size]
        index.upsert(vectors=batch)
        print(f"  Upserted {min(start + batch_size, total)}/{total}")

    print(f"\n✅ Seeding complete. {total} vectors across {len(doc_files)} documents.")
    print(f"   Index: {INDEX_NAME}")

    # Quick sanity check
    stats = index.describe_index_stats()
    print(f"   Index stats: {stats}")


if __name__ == "__main__":
    seed()
