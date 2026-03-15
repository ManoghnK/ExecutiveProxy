"""
Test script for the Classifier Lambda.

Usage:
  # Invoke deployed Lambda:
  python scripts/test_classifier.py

  # Test local handler (no Lambda invoke):
  python scripts/test_classifier.py --local

Pre-requisites:
  - ExecProxyLambda stack deployed (classifier Lambda)
  - AWS credentials configured
"""

import argparse
import json
import os
import sys
import time

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


# ── Test cases ────────────────────────────────────────────────────────────────
# Uses the ACTUAL intent labels from classifier/handler.py:
#   JIRA_TICKET, CALENDAR_EVENT, POLICY_RISK, NO_ACTION
TEST_CASES = [
    {
        "transcript_chunk": "Let's create a Jira ticket for the API bug we discussed",
        "expected": "JIRA_TICKET",
    },
    {
        "transcript_chunk": "Schedule a meeting with the engineering team next Tuesday at 2pm",
        "expected": "CALENDAR_EVENT",
    },
    {
        "transcript_chunk": "What are the compliance risks of storing customer data in the cloud?",
        "expected": "POLICY_RISK",
    },
    {
        "transcript_chunk": "Just discussing the weather today, nothing important",
        "expected": "NO_ACTION",
    },
]


def test_deployed():
    """Invoke the deployed classifier Lambda with test cases."""
    print("=" * 60)
    print("Classifier — Deployed Lambda Test")
    print("=" * 60)

    func_name = find_lambda("classifier")
    if not func_name:
        print("❌ Classifier Lambda not found!")
        print("   Deploy first: cd cdk && cdk deploy ExecProxyLambda")
        return False

    print(f"  Function: {func_name}\n")
    client = boto3.client("lambda", region_name=REGION)

    passed = 0
    failed = 0

    for i, tc in enumerate(TEST_CASES, 1):
        print(f"Test {i}: {tc['transcript_chunk'][:50]}...")

        # Matches classifier handler's expected event schema:
        #   { meeting_id, speaker, transcript_chunk, timestamp }
        payload = {
            "meeting_id": f"test-cls-{i}",
            "speaker": "test-user",
            "transcript_chunk": tc["transcript_chunk"],
            "timestamp": "2026-03-15T10:00:00Z",
        }

        t0 = time.time()
        response = client.invoke(
            FunctionName=func_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )
        elapsed = time.time() - t0

        result = json.loads(response["Payload"].read())

        if result.get("statusCode") == 200:
            body = json.loads(result["body"]) if isinstance(result["body"], str) else result["body"]
            intent = body.get("intent")
            confidence = body.get("confidence", "?")

            if intent == tc["expected"]:
                print(f"  ✅ PASS — Intent: {intent}  Confidence: {confidence}  ({elapsed:.1f}s)\n")
                passed += 1
            else:
                print(f"  ❌ FAIL — Expected: {tc['expected']}, Got: {intent}  ({elapsed:.1f}s)\n")
                failed += 1
        else:
            print(f"  ❌ ERROR: {json.dumps(result, indent=2)} ({elapsed:.1f}s)\n")
            failed += 1

    print("=" * 50)
    print(f"Results: {passed}/{len(TEST_CASES)} passed")
    if failed == 0:
        print("✅ Classifier PASSED all tests")
    else:
        print(f"❌ Classifier FAILED {failed} test(s)")

    return failed == 0


def test_local():
    """Run the classifier handler locally."""
    print("=" * 60)
    print("Classifier — Local Test")
    print("=" * 60)

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas", "classifier"))

    from handler import classify_transcript

    passed = 0
    failed = 0

    for i, tc in enumerate(TEST_CASES, 1):
        print(f"Test {i}: {tc['transcript_chunk'][:50]}...")

        t0 = time.time()
        result = classify_transcript(tc["transcript_chunk"])
        elapsed = time.time() - t0

        intent = result.get("intent", "?")
        confidence = result.get("confidence", "?")

        if intent == tc["expected"]:
            print(f"  ✅ PASS — Intent: {intent}  Confidence: {confidence}  ({elapsed:.1f}s)\n")
            passed += 1
        else:
            print(f"  ❌ FAIL — Expected: {tc['expected']}, Got: {intent}  ({elapsed:.1f}s)\n")
            failed += 1

    print("=" * 50)
    print(f"Results: {passed}/{len(TEST_CASES)} passed")
    return failed == 0


def main():
    parser = argparse.ArgumentParser(description="Test Classifier Lambda")
    parser.add_argument("--local", action="store_true", help="Run handler locally")
    args = parser.parse_args()

    if args.local:
        success = test_local()
    else:
        success = test_deployed()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
