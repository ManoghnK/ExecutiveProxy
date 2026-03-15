import os
import json
import uuid
import re
import boto3
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# ── Config ────────────────────────────────────────────────────────────────────
AWS_REGION        = os.environ.get("AWS_REGION", "us-east-1")
PINECONE_API_KEY  = os.environ["PINECONE_API_KEY"]
INDEX_NAME        = os.environ["PINECONE_INDEX_NAME"]
EMBEDDING_MODEL   = "amazon.titan-embed-text-v2:0"
EMBEDDING_DIM     = 1024  # Enforcing 1024 for Titan v2
CHUNK_SIZE        = 400   # tokens approx — sweet spot for RAG precision
CHUNK_OVERLAP     = 50

POLICY_DOCS_DIR   = Path(__file__).parent / "policy_docs"

bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)

headers = {
    "Api-Key": PINECONE_API_KEY,
    "Content-Type": "application/json"
}


# ── Chunking ──────────────────────────────────────────────────────────────────
def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
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
    match = re.search(r"#{1,3} (.+)", chunk)
    return match.group(1).strip() if match else "General"


# ── Embedding ─────────────────────────────────────────────────────────────────
def get_embedding(text: str) -> list[float]:
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


# ── Pinecone REST Helpers ─────────────────────────────────────────────────────
def get_index_host() -> str:
    response = requests.get(
        f"https://api.pinecone.io/indexes/{INDEX_NAME}",
        headers=headers,
        timeout=10
    )
    if response.status_code == 200:
        return response.json().get('host')
    else:
        raise Exception(f"Failed to get index {INDEX_NAME}: {response.text}")

def upsert_vectors(host, vectors):
    # Upsert in batches of 100
    batch_size = 100
    total = len(vectors)
    print(f"\nUpserting {total} vectors to Pinecone (host: {host}) in batches of {batch_size}...")

    for start in range(0, total, batch_size):
        batch = vectors[start : start + batch_size]
        payload = {
            "vectors": batch
        }
        res = requests.post(
            f"https://{host}/vectors/upsert",
            headers=headers,
            json=payload,
            timeout=30
        )
        if res.status_code == 200:
            print(f"  Upserted {min(start + batch_size, total)}/{total}")
        else:
            print(f"  ❌ Failed to upsert batch: {res.status_code} - {res.text}")


# ── Main ──────────────────────────────────────────────────────────────────────
def seed():
    try:
        host = get_index_host()
    except Exception as e:
        print(e)
        return

    doc_files = list(POLICY_DOCS_DIR.glob("*.md"))
    if not doc_files:
        print(f"No .md files found in {POLICY_DOCS_DIR}")
        return

    all_vectors = []

    for doc_path in doc_files:
        doc_name = doc_path.stem
        print(f"\nProcessing: {doc_path.name}")
        text = doc_path.read_text(encoding="utf-8")
        chunks = chunk_text(text)
        print(f"  → {len(chunks)} chunks")

        for i, chunk in enumerate(chunks):
            print(f"  Embedding chunk {i+1}/{len(chunks)}...", end="\r")
            try:
                vector = get_embedding(chunk)
            except Exception as e:
                print(f"\n  ❌ Failed to embed chunk: {e}")
                continue
            section = extract_section_header(chunk)

            all_vectors.append({
                "id": f"{doc_name}_{i}_{uuid.uuid4().hex[:8]}",
                "values": vector,
                "metadata": {
                    "source": doc_name,
                    "section": section,
                    "chunk_index": i,
                    "text": chunk[:1000],
                },
            })

    if all_vectors:
        upsert_vectors(host, all_vectors)
        print(f"\n✅ Seeding complete. {len(all_vectors)} vectors across {len(doc_files)} documents.")
    else:
        print("\n⚠️ No vectors generated.")

if __name__ == "__main__":
    seed()
