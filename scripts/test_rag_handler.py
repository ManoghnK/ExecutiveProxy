"""
Test script for the RAG Handler Lambda.

Usage:
  # Invoke deployed Lambda:
  python scripts/test_rag_handler.py

  # Test local handler (no Lambda invoke):
  python scripts/test_rag_handler.py --local

Pre-requisites:
  - ExecProxyLambda stack deployed (rag_handler Lambda)
  - Pinecone index seeded with policy docs
  - AWS credentials configured
"""

import argparse
import json
import os
import sys

import boto3

REGION = "us-east-1"


def find_lambda(pattern: str) -> str | None:
    """Find a Lambda function name containing the given pattern."""
    client = boto3.client("lambda", region_name=REGION)
    paginator = client.get_paginator("list_functions")
    for page in paginator.paginate():
        for func in page["Functions"]:
            if pattern.lower() in func["FunctionName"].lower():
                return func["FunctionName"]
    return None


def test_deployed():
    """Invoke the deployed rag_handler Lambda."""
    print("=" * 60)
    print("RAG Handler — Deployed Lambda Test")
    print("=" * 60)

    func_name = find_lambda("raghandler")
    if not func_name:
        print("❌ rag_handler Lambda not found!")
        print("   Deploy first: cd cdk && cdk deploy ExecProxyLambdas")
        return False

    print(f"  Function: {func_name}\n")

    client = boto3.client("lambda", region_name=REGION)

    # Test payload — matches handler's expected event schema:
    #   { "meeting_id": str, "query_text": str }
    payload = {
        "meeting_id": "test-rag-001",
        "query_text": (
            "We need to assess the cybersecurity risks of deploying AI "
            "in production. What are the compliance requirements?"
        ),
    }

    print(f"📤 Invoking with payload:\n{json.dumps(payload, indent=2)}\n")

    response = client.invoke(
        FunctionName=func_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload),
    )

    result = json.loads(response["Payload"].read())
    print(f"📥 Response:\n{json.dumps(result, indent=2)}\n")

    # ── Validation ────────────────────────────────────────────────────────
    print("--- Validation ---")
    status_code = result.get("statusCode", 0)
    body_raw = result.get("body", "{}")
    try:
        body = json.loads(body_raw) if isinstance(body_raw, str) else body_raw
    except json.JSONDecodeError:
        body = {}

    checks = {
        "statusCode == 200": status_code == 200,
        "risk_level present": "risk_level" in body,
        "recommendation present": "recommendation" in body,
        "no error field": "error" not in body,
    }

    all_pass = True
    for check, passed in checks.items():
        icon = "✅" if passed else "❌"
        print(f"  {icon} {check}")
        if not passed:
            all_pass = False

    if all_pass:
        print(f"\n✅ RAG Handler PASSED")
        print(f"   Risk level: {body.get('risk_level')}")
        print(f"   Recommendation: {str(body.get('recommendation', ''))[:120]}...")
    else:
        print(f"\n❌ RAG Handler FAILED")

    return all_pass


def test_local():
    """Run the handler locally (imports handler.py directly)."""
    print("=" * 60)
    print("RAG Handler — Local Test")
    print("=" * 60)

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas", "rag_handler"))

    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

    from handler import handler  # type: ignore

    event = {
        "meeting_id": "test-rag-local",
        "query_text": "I want to hire a contractor without an NDA immediately.",
    }

    print(f"📤 Event:\n{json.dumps(event, indent=2)}\n")

    result = handler(event, None)
    print(f"📥 Result:\n{json.dumps(result, indent=2)}\n")

    status_code = result.get("statusCode", 0)
    body = json.loads(result.get("body", "{}"))

    checks = {
        "statusCode == 200": status_code == 200,
        "risk_level present": "risk_level" in body,
        "no error field": "error" not in body,
    }

    all_pass = True
    for check, passed in checks.items():
        icon = "✅" if passed else "❌"
        print(f"  {icon} {check}")
        if not passed:
            all_pass = False

    return all_pass


def main():
    parser = argparse.ArgumentParser(description="Test RAG Handler Lambda")
    parser.add_argument("--local", action="store_true", help="Run handler locally")
    args = parser.parse_args()

    if args.local:
        success = test_local()
    else:
        success = test_deployed()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
