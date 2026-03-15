"""
Test script for AppSync + DynamoDB Streams integration.

Usage:
  # Write test data to DynamoDB and verify AppSync query:
  python scripts/test_appsync.py

  # Query only (no write):
  python scripts/test_appsync.py --query-only

  # Verify stream resolver locally:
  python scripts/test_appsync.py --local

Pre-requisites:
  - ExecProxyAppSync stack deployed: cd cdk && cdk deploy ExecProxyAppSync
  - AWS CLI configured with credentials
"""

import argparse
import json
import os
import sys
import time
import uuid
import urllib.request
import urllib.error
from datetime import datetime, timezone


def get_appsync_config():
    """Get AppSync URL and API key from CloudFormation outputs."""
    import boto3
    cfn = boto3.client("cloudformation", region_name="us-east-1")
    try:
        resp = cfn.describe_stacks(StackName="ExecProxyAppSync")
        outputs = {
            o["OutputKey"]: o["OutputValue"]
            for o in resp["Stacks"][0].get("Outputs", [])
        }
        return {
            "url": outputs.get("AppSyncApiUrl", ""),
            "key": outputs.get("AppSyncApiKey", ""),
            "id": outputs.get("AppSyncApiId", ""),
        }
    except Exception as e:
        print(f"Could not read stack outputs: {e}")
        return {
            "url": os.environ.get("APPSYNC_API_URL", ""),
            "key": os.environ.get("APPSYNC_API_KEY", ""),
            "id": "",
        }


def execute_graphql(url, api_key, query, variables=None):
    """Execute a GraphQL query against AppSync."""
    payload = json.dumps({
        "query": query,
        "variables": variables or {},
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_write_and_query():
    """Write to DynamoDB and verify AppSync returns the data."""
    print("=" * 60)
    print("AppSync + DynamoDB Integration Test")
    print("=" * 60)

    config = get_appsync_config()
    if not config["url"] or not config["key"]:
        print("ERROR: AppSync not deployed or config missing.")
        print("Deploy first: cd cdk && cdk deploy ExecProxyAppSync")
        return False

    print(f"  AppSync URL: {config['url']}")
    print(f"  API Key: {config['key'][:12]}...")
    print()

    # Generate test data
    meeting_id = f"test-{uuid.uuid4()}"
    timestamp = datetime.now(timezone.utc).isoformat()

    # ── Step 1: Write to MeetingState table ──────────────────────────────
    print("[1/4] Writing transcript chunk to MeetingState...")
    import boto3
    dynamo = boto3.resource("dynamodb", region_name="us-east-1")
    meeting_table = dynamo.Table("MeetingState")

    meeting_table.put_item(Item={
        "meeting_id": meeting_id,
        "timestamp": timestamp,
        "speaker": "Test Speaker",
        "transcript_chunk": "We need to create a Jira ticket for the login bug fix.",
        "intent_label": "JIRA_TICKET",
        "action_triggered": True,
    })
    print(f"  ✅ Written: meeting_id={meeting_id}")

    # ── Step 2: Write to ActionLog table ─────────────────────────────────
    print("[2/4] Writing action to ActionLog...")
    action_table = dynamo.Table("ActionLog")
    action_id = str(uuid.uuid4())

    action_table.put_item(Item={
        "meeting_id": meeting_id,
        "action_id": action_id,
        "action_type": "JIRA_TICKET",
        "status": "COMPLETED",
        "payload": json.dumps({"summary": "Fix login bug"}),
        "result": json.dumps({"ticket_id": "EP-42", "url": "https://jira.example.com/EP-42"}),
        "created_at": timestamp,
    })
    print(f"  ✅ Written: action_id={action_id}")

    # ── Step 3: Wait for stream processing ───────────────────────────────
    print("[3/4] Waiting 3s for DynamoDB Stream processing...")
    time.sleep(3)

    # ── Step 4: Query AppSync ────────────────────────────────────────────
    print("[4/4] Querying AppSync for written data...")

    # Query meeting
    meeting_query = """
    query GetMeeting($meeting_id: ID!) {
        getMeeting(meeting_id: $meeting_id) {
            items {
                meeting_id
                timestamp
                speaker
                transcript_chunk
                intent_label
            }
        }
    }
    """
    meeting_result = execute_graphql(
        config["url"], config["key"],
        meeting_query, {"meeting_id": meeting_id}
    )

    # Query actions
    action_query = """
    query GetActions($meeting_id: ID!) {
        getActions(meeting_id: $meeting_id) {
            items {
                meeting_id
                action_id
                action_type
                status
                result
            }
        }
    }
    """
    action_result = execute_graphql(
        config["url"], config["key"],
        action_query, {"meeting_id": meeting_id}
    )

    # ── Validation ───────────────────────────────────────────────────────
    print("\n--- Validation ---")
    all_pass = True

    # Check meeting query
    meeting_items = (meeting_result.get("data", {})
                     .get("getMeeting", {})
                     .get("items", []))
    checks = {
        "getMeeting returns items": len(meeting_items) > 0,
        "meeting_id matches": (meeting_items[0]["meeting_id"] == meeting_id
                               if meeting_items else False),
        "transcript_chunk present": bool(meeting_items[0].get("transcript_chunk"))
                                    if meeting_items else False,
    }

    # Check action query
    action_items = (action_result.get("data", {})
                    .get("getActions", {})
                    .get("items", []))
    checks.update({
        "getActions returns items": len(action_items) > 0,
        "action_type is JIRA_TICKET": (action_items[0]["action_type"] == "JIRA_TICKET"
                                       if action_items else False),
        "status is COMPLETED": (action_items[0]["status"] == "COMPLETED"
                                if action_items else False),
    })

    for check, passed in checks.items():
        icon = "✅" if passed else "❌"
        print(f"  {icon} {check}")
        if not passed:
            all_pass = False

    # Clean up test data
    try:
        meeting_table.delete_item(Key={"meeting_id": meeting_id, "timestamp": timestamp})
        action_table.delete_item(Key={"meeting_id": meeting_id, "action_id": action_id})
        print("\n  🧹 Test data cleaned up")
    except Exception:
        pass

    return all_pass


def test_stream_resolver_local():
    """Test the stream resolver Lambda handler locally with mock data."""
    print("=" * 60)
    print("Stream Resolver — Local Test")
    print("=" * 60)

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas", "stream_resolver"))
    from handler import _parse_dynamo_image, handler as stream_handler

    # Test DynamoDB image parsing
    test_image = {
        "meeting_id": {"S": "test-123"},
        "timestamp": {"S": "2026-03-14T10:00:00Z"},
        "speaker": {"S": "Alice"},
        "transcript_chunk": {"S": "Create a Jira ticket"},
        "intent_label": {"S": "JIRA_TICKET"},
        "action_triggered": {"BOOL": True},
    }

    parsed = _parse_dynamo_image(test_image)

    checks = {
        "meeting_id parsed": parsed["meeting_id"] == "test-123",
        "speaker parsed": parsed["speaker"] == "Alice",
        "action_triggered is bool": parsed["action_triggered"] is True,
    }

    all_pass = True
    for check, passed in checks.items():
        icon = "✅" if passed else "❌"
        print(f"  {icon} {check}")
        if not passed:
            all_pass = False

    # Test handler with mock event (will fail AppSync call but validates parsing)
    print("\n  Testing handler with mock stream event (AppSync call will fail)...")
    mock_event = {
        "Records": [
            {
                "eventName": "INSERT",
                "dynamodb": {
                    "NewImage": test_image,
                },
            },
            {
                "eventName": "REMOVE",  # Should be skipped
                "dynamodb": {"NewImage": {}},
            },
        ]
    }

    # Without AppSync config, the handler should handle gracefully
    os.environ.pop("APPSYNC_API_URL", None)
    os.environ.pop("APPSYNC_API_KEY", None)
    result = stream_handler(mock_event, None)
    checks2 = {
        "handler returns 500 without config": result.get("statusCode") == 500,
    }
    for check, passed in checks2.items():
        icon = "✅" if passed else "❌"
        print(f"  {icon} {check}")
        if not passed:
            all_pass = False

    return all_pass


def test_query_only():
    """Query AppSync without writing (useful for checking deployed state)."""
    print("=" * 60)
    print("AppSync Query-Only Test")
    print("=" * 60)

    config = get_appsync_config()
    if not config["url"]:
        print("ERROR: AppSync not deployed")
        return False

    # Query for any existing meeting
    result = execute_graphql(
        config["url"], config["key"],
        """query { getMeeting(meeting_id: "test-0") { items { meeting_id } } }"""
    )

    print(f"  Query response: {json.dumps(result, indent=2)}")
    print(f"  ✅ AppSync endpoint reachable")
    return "errors" not in result


def main():
    parser = argparse.ArgumentParser(description="Test AppSync Integration")
    parser.add_argument("--query-only", action="store_true",
                        help="Only test AppSync queries")
    parser.add_argument("--local", action="store_true",
                        help="Test stream resolver locally")
    args = parser.parse_args()

    results = []

    if args.local:
        results.append(("Stream Resolver Local", test_stream_resolver_local()))
    elif args.query_only:
        results.append(("Query-Only", test_query_only()))
    else:
        results.append(("Write + Query", test_write_and_query()))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    all_pass = True
    for name, passed in results:
        icon = "✅" if passed else "❌"
        print(f"  {icon} {name}")
        if not passed:
            all_pass = False

    print(f"\n{'ALL TESTS PASSED' if all_pass else 'SOME TESTS FAILED'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
