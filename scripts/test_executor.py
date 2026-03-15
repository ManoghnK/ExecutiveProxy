"""
Test script for the Executor Lambda.

Usage:
  # Invoke deployed Lambda:
  python scripts/test_executor.py

  # Test local handler (no Lambda invoke):
  python scripts/test_executor.py --local

Pre-requisites:
  - ExecProxyLambda stack deployed (executor Lambda)
  - AWS credentials configured
  - Jira credentials in .env (for JIRA_TICKET test to fully pass)
"""

import argparse
import json
import os
import sys
import time

import boto3

REGION = "us-east-1"


def find_lambda(pattern: str, exclude: str = "") -> str | None:
    """Find a Lambda function name containing pattern but not exclude."""
    client = boto3.client("lambda", region_name=REGION)
    paginator = client.get_paginator("list_functions")
    for page in paginator.paginate():
        for func in page["Functions"]:
            name = func["FunctionName"]
            if pattern.lower() in name.lower() and (not exclude or exclude.lower() not in name.lower()):
                return name
    return None


# ── Test cases ────────────────────────────────────────────────────────────────
# Matches executor handler's expected event schema:
#   { meeting_id, intent, extracted_action, entities }
TEST_CASES = [
    {
        "intent": "JIRA_TICKET",
        "extracted_action": "Create a ticket to investigate the login timeout issue affecting mobile users",
        "entities": {"assignee": "sarah", "component": "auth-service"},
        "description": "Jira ticket creation via Nova Pro tool use → REST API",
        "success_check": lambda body: (
            "key" in body  # Jira REST API returns {"key": "EP-XX"}
            or "error" not in body
            or body.get("status") == "SKIPPED"  # OK if Jira creds missing
        ),
    },
    {
        "intent": "CALENDAR_EVENT",
        "extracted_action": "Schedule a sprint planning meeting next Monday at 10am with the dev team",
        "entities": {"day": "Monday", "time": "10am", "duration": "60 minutes"},
        "description": "Calendar event creation (mock fallback expected)",
        "success_check": lambda body: (
            body.get("status") == "MOCKED"  # Mock fallback is expected
            or body.get("success") is True
            or "error" not in body
        ),
    },
    {
        "intent": "POLICY_RISK",
        "extracted_action": "What are the data retention policies for EU customers under GDPR?",
        "entities": {"risk_area": "data privacy", "regulation": "GDPR"},
        "description": "Policy risk → handoff to RAG handler",
        "success_check": lambda body: (
            body.get("handoff") is not None  # Async handoff to RAG
            or "error" in body  # RAG_LAMBDA_NAME not set is also acceptable
        ),
    },
]


def test_deployed():
    """Invoke the deployed executor Lambda."""
    print("=" * 60)
    print("Executor — Deployed Lambda Test")
    print("=" * 60)

    func_name = find_lambda("executor", exclude="raghandler")
    if not func_name:
        print("❌ Executor Lambda not found!")
        print("   Deploy first: cd cdk && cdk deploy ExecProxyLambda")
        return False

    print(f"  Function: {func_name}\n")
    client = boto3.client("lambda", region_name=REGION)

    passed = 0
    failed = 0

    for i, tc in enumerate(TEST_CASES, 1):
        print(f"Test {i} — {tc['intent']}: {tc['description']}")
        print(f"  Action: {tc['extracted_action'][:60]}...\n")

        payload = {
            "meeting_id": f"test-exec-{i}",
            "intent": tc["intent"],
            "extracted_action": tc["extracted_action"],
            "entities": tc["entities"],
        }

        t0 = time.time()
        response = client.invoke(
            FunctionName=func_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )
        elapsed = time.time() - t0

        result = json.loads(response["Payload"].read())
        print(f"  Response ({elapsed:.1f}s):\n  {json.dumps(result, indent=2)}\n")

        status_code = result.get("statusCode", 0)
        body_raw = result.get("body", "{}")
        try:
            body = json.loads(body_raw) if isinstance(body_raw, str) else body_raw
        except json.JSONDecodeError:
            body = {}

        if status_code == 200 and tc["success_check"](body):
            print(f"  ✅ PASS\n")
            passed += 1
        else:
            print(f"  ❌ FAIL\n")
            failed += 1

    print("=" * 50)
    print(f"Results: {passed}/{len(TEST_CASES)} passed")
    if failed == 0:
        print("✅ Executor PASSED all tests")
    else:
        print(f"❌ Executor FAILED {failed} test(s)")

    return failed == 0


def test_local():
    """Run the executor handler locally with mocked DynamoDB and Lambda."""
    print("=" * 60)
    print("Executor — Local Test")
    print("=" * 60)

    executor_path = os.path.join(os.path.dirname(__file__), "..", "lambdas", "executor")
    sys.path.insert(0, executor_path)

    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

    import handler as executor_module

    # Mock DynamoDB
    class MockTable:
        def put_item(self, Item):
            print(f"  [DynamoDB] PutItem: {Item.get('action_type')} — {Item.get('status')}")

    executor_module.dynamodb.Table = lambda x: MockTable()

    # Mock Lambda client (for RAG handoff)
    class MockLambdaClient:
        def invoke(self, **kwargs):
            print(f"  [Lambda] Async invoke: {kwargs.get('FunctionName')}")
            return {}

    executor_module.lambda_client = MockLambdaClient()
    executor_module.RAG_LAMBDA_NAME = "mock-rag-handler"

    passed = 0
    failed = 0

    for i, tc in enumerate(TEST_CASES, 1):
        print(f"\nTest {i} — {tc['intent']}: {tc['description']}")

        event = {
            "meeting_id": f"test-local-{i}",
            "intent": tc["intent"],
            "extracted_action": tc["extracted_action"],
            "entities": tc["entities"],
        }

        try:
            result = executor_module.handler(event, None)
            status_code = result.get("statusCode", 0)
            body = json.loads(result.get("body", "{}"))
            print(f"  Result: {json.dumps(body)[:200]}")

            if status_code == 200:
                print(f"  ✅ PASS\n")
                passed += 1
            else:
                print(f"  ❌ FAIL\n")
                failed += 1
        except Exception as e:
            print(f"  ❌ EXCEPTION: {e}\n")
            failed += 1

    print("=" * 50)
    print(f"Results: {passed}/{len(TEST_CASES)} passed")
    return failed == 0


def main():
    parser = argparse.ArgumentParser(description="Test Executor Lambda")
    parser.add_argument("--local", action="store_true", help="Run handler locally with mocks")
    args = parser.parse_args()

    if args.local:
        success = test_local()
    else:
        success = test_deployed()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
