import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("PINECONE_API_KEY")
if not api_key:
    print("❌ PINECONE_API_KEY not found in .env")
    exit(1)

# Pinecone index details
# We first need to get the index host URL from the describe endpoint
headers = {
    "Api-Key": api_key,
    "Content-Type": "application/json"
}

print("Fetching index details...")
# Use us-east-1 region (typical default for this hackathon setup unless otherwise specified)
# Let's hit the describe endpoint to get the host
# Note: Pinecone V2 API endpoint for describing index: https://api.pinecone.io/indexes/executive-proxy-policies
try:
    response = requests.get(
        "https://api.pinecone.io/indexes/executive-proxy-policies",
        headers=headers,
        timeout=10
    )
    if response.status_code == 200:
        index_data = response.json()
        host = index_data.get('host')
        dimension = index_data.get('dimension')
        print(f"✅ Found Index Host: {host}")
        print(f"✅ Index dimension: {dimension}")
        
        # Now get stats from the index host
        stats_response = requests.get(
            f"https://{host}/describe_index_stats",
            headers=headers,
            timeout=10
        )
        if stats_response.status_code == 200:
            stats = stats_response.json()
            print(f"✅ Total vectors: {stats.get('totalVectorCount')}")
            print(f"✅ Namespaces: {stats.get('namespaces', {})}")
            
            # Test query
            print("\nTesting Query...")
            query_vector = [0.1] * dimension if dimension else [0.1] * 1024
            query_payload = {
                "vector": query_vector,
                "topK": 3,
                "includeMetadata": True
            }
            query_response = requests.post(
                f"https://{host}/query",
                headers=headers,
                json=query_payload,
                timeout=10
            )
            
            if query_response.status_code == 200:
                results = query_response.json()
                matches = results.get('matches', [])
                print(f"✅ Query test successful. Found {len(matches)} results")
                if matches:
                    metadata = matches[0].get('metadata', {})
                    text = metadata.get('text', 'N/A')
                    print(f"   Sample match: {text[:100]}...")
            else:
                print(f"❌ Query failed: {query_response.status_code} - {query_response.text}")
        else:
             print(f"❌ Failed to get stats: {stats_response.status_code} - {stats_response.text}")
             
    else:
        print(f"❌ Failed to describe index: {response.status_code} - {response.text}")

except Exception as e:
    print(f"❌ Error connecting to Pinecone: {e}")
