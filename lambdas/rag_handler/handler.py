"""
Combined permissions for this handler:
- bedrock:InvokeModel on amazon.nova-pro-v1:0 and amazon.titan-embed-text-v2:0
- dynamodb:PutItem on ActionLog table
"""
import json
import boto3
import os
import uuid
import datetime
import urllib.request
import urllib.parse

# ── Config ────────────────────────────────────────────────────────────────────
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "executive-proxy-policies")
DYNAMODB_ACTION_TABLE = os.environ.get("DYNAMODB_ACTION_TABLE", "ActionLog")

# Model IDs
# NOTE: Switched to Titan Embeddings v2 due to Nova Multimodal input issues
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
REASONING_MODEL_ID = "amazon.nova-pro-v1:0"

# Clients
bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)

_INDEX_HOST_CACHE = None

def get_pinecone_host():
    global _INDEX_HOST_CACHE
    if _INDEX_HOST_CACHE:
        return _INDEX_HOST_CACHE

    req = urllib.request.Request(
        f"https://api.pinecone.io/indexes/{PINECONE_INDEX_NAME}",
        headers={"Api-Key": PINECONE_API_KEY}
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        data = json.loads(response.read().decode("utf-8"))
        _INDEX_HOST_CACHE = data.get("host")
        return _INDEX_HOST_CACHE

def get_embedding(text: str) -> list[float]:
    """Generate embedding using Titan v2 via Bedrock."""
    body = json.dumps({
        "inputText": text,
        "dimensions": 1024,
        "normalize": True
    })
    response = bedrock.invoke_model(
        modelId=EMBEDDING_MODEL_ID,
        body=body,
        contentType="application/json",
        accept="application/json",
    )
    result = json.loads(response["body"].read())
    return result["embedding"]

def query_pinecone(vector: list[float], top_k: int = 5) -> list[str]:
    """Retrieve relevant policy chunks from Pinecone using REST."""
    if not PINECONE_API_KEY:
        print("WARNING: PINECONE_API_KEY not set. Returning empty context.")
        return []
        
    try:
        host = get_pinecone_host()
    except Exception as e:
        print(f"Error fetching index host: {e}")
        return []

    payload = json.dumps({
        "vector": vector,
        "topK": top_k,
        "includeMetadata": True
    }).encode("utf-8")

    req = urllib.request.Request(
        f"https://{host}/query",
        data=payload,
        headers={
            "Api-Key": PINECONE_API_KEY,
            "Content-Type": "application/json"
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            results = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        print(f"Pinecone query failed: {e}")
        return []
    
    # Format context: "Source: [Title] \n Text: [Chunk]"
    context_chunks = []
    for match in results.get("matches", []):
        meta = match.get("metadata", {})
        text = meta.get("text", "")
        source = meta.get("source", "Unknown")
        score = match.get("score", 0.0)
        context_chunks.append(f"Source: {source} (Score: {score:.3f})\nContent: {text}")
        
    return context_chunks

def analyze_risk(query: str, context: list[str]) -> dict:
    """Ask Nova Pro to assess risk based on policy context."""
    context_str = "\n\n".join(context)
    
    system_prompt_text = (
        "You are a Corporate Risk Officer. Analyze the user's proposed action against the provided policy documents. "
        "Identify violations and assign a risk level. "
        "Return ONLY valid JSON with this structure: "
        "{ 'risk_level': 'LOW'|'MEDIUM'|'HIGH'|'CRITICAL', 'policy_violations': [str], 'affected_policies': [str], 'recommendation': str }"
    )
    
    user_message = f"""
    Context from Policy Documents:
    {context_str}
    
    User Query/Action:
    "{query}"
    
    Analyze the risk. JSON only.
    """
    
    # Nova Pro uses Converse API
    messages = [{"role": "user", "content": [{"text": user_message}]}]
    
    try:
        response = bedrock.converse(
            modelId=REASONING_MODEL_ID,
            messages=messages,
            system=[{"text": system_prompt_text}],
            inferenceConfig={"temperature": 0.0}
        )
        output_text = response["output"]["message"]["content"][0]["text"]
        
        # Strip markdown if present
        if "```json" in output_text:
            output_text = output_text.split("```json")[1].split("```")[0].strip()
        elif "```" in output_text:
            output_text = output_text.split("```")[1].split("```")[0].strip()
            
        print(f"Nova Pro Output: {output_text}")
        return json.loads(output_text)
        
    except Exception as e:
        print(f"Error invoking Nova Pro: {e}")
        return {
            "risk_level": "UNKNOWN",
            "policy_violations": ["Error analyzing risk"],
            "affected_policies": [],
            "recommendation": "Manual review required due to system error."
        }

def handler(event, context):
    """
    Lambda Entrypoint.
    Event: { "meeting_id": str, "query_text": str }
    """
    meeting_id = event.get("meeting_id", "unknown")
    query_text = event.get("query_text", "")
    
    print(f"Processing RAG for meeting {meeting_id}: {query_text}")
    
    try:
        # 1. Embed Query
        vector = get_embedding(query_text)
        
        # 2. Retrieve Context
        context_chunks = query_pinecone(vector)
        
        # 3. Analyze Risk
        risk_matrix = analyze_risk(query_text, context_chunks)
        
        # 4. Log Action
        action_item = {
            "meeting_id": meeting_id,
            "action_id": str(uuid.uuid4()),
            "action_type": "RISK_MATRIX",
            "status": "COMPLETED",
            "payload": json.dumps({"query": query_text}),
            "result": json.dumps(risk_matrix),
            "created_at": datetime.datetime.now().isoformat()
        }
        
        table = dynamodb.Table(DYNAMODB_ACTION_TABLE)
        table.put_item(Item=action_item)
        
        return {
            "statusCode": 200,
            "body": json.dumps(risk_matrix)
        }
    except Exception as e:
        print(f"Handler failed: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

if __name__ == "__main__":
    # Local Test
    # export PINECONE_API_KEY=...
    # export AWS_REGION=us-east-1
    test_event = {
        "meeting_id": "test-meeting-123",
        "query_text": "I want to hire a contractor without an NDA immediately."
    }
    print("Running local test...")
    # Mock context or ensure env vars set
    if not PINECONE_API_KEY:
        print("Set PINECONE_API_KEY to run test.")
    else:
        result = handler(test_event, None)
        print("Result:", json.dumps(result, indent=2))
