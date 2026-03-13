import boto3
import json
import os
import sys

client = boto3.client("bedrock-runtime", region_name="us-east-1")
model_id = "amazon.titan-embed-text-v2:0"

print(f"Testing model: {model_id}")
# Titan V2 payload
payloads = [
    {"inputText": "test"}
]

for p in payloads:
    print(f"Testing InvokeModel payload: {json.dumps(p)}")
    try:
        response = client.invoke_model(
            modelId=model_id,
            body=json.dumps(p)
        )
        print("InvokeModel SUCCESS")
        print(response['body'].read())
        sys.exit(0)
    except Exception as e:
        print(f"FAILED: {e}")
