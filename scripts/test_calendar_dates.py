"""
Test Script: Validate Calendar Date Fix in Executor Lambda
==========================================================
Run this BEFORE the end-to-end test to confirm Nova Pro is resolving
dates correctly with the new datetime anchor in the system prompt.

Usage:
    cd executive-proxy
    python scripts/test_calendar_dates.py

Prerequisites:
    - AWS credentials configured (SSO refresh if needed)
    - .env file with all required variables
    - The fix applied to lambdas/executor/handler.py
"""

import json
import sys
import os
from datetime import datetime, timezone, timedelta

# Add project root to path so we can import the executor handler
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ─── CONFIG ───────────────────────────────────────────────────────
# If your executor is deployed as a Lambda, set this to True and provide the function name.
# If you want to test the handler locally (calling Bedrock directly), set to False.
TEST_REMOTE_LAMBDA = False
LAMBDA_FUNCTION_NAME = "ExecProxyLambda-executor"  # adjust if your CDK names it differently

# ─── TEST CASES ───────────────────────────────────────────────────
today = datetime.now(timezone.utc)

test_cases = [
    {
        "name": "Relative weekday — Thursday at 2pm",
        "payload": {
            "meeting_id": "test-cal-001",
            "intent": "CALENDAR_EVENT",
            "extracted_action": "Schedule a team sync for Thursday at 2pm",
            "confidence": 0.95
        },
        "validate": lambda dt: dt.year == today.year and dt.replace(tzinfo=timezone.utc) > today,
    },
    {
        "name": "Tomorrow morning",
        "payload": {
            "meeting_id": "test-cal-002",
            "intent": "CALENDAR_EVENT",
            "extracted_action": "Block 30 minutes tomorrow at 9am for a standup",
            "confidence": 0.92
        },
        "validate": lambda dt: dt.date() == (today + timedelta(days=1)).date(),
    },
    {
        "name": "Next Friday",
        "payload": {
            "meeting_id": "test-cal-003",
            "intent": "CALENDAR_EVENT",
            "extracted_action": "Set up a retrospective next Friday at 4pm",
            "confidence": 0.90
        },
        "validate": lambda dt: dt.year == today.year and dt.replace(tzinfo=timezone.utc) > today and dt.weekday() == 4,
    },
    {
        "name": "Relative hours — in 2 hours",
        "payload": {
            "meeting_id": "test-cal-004",
            "intent": "CALENDAR_EVENT",
            "extracted_action": "Schedule a quick 1:1 in 2 hours",
            "confidence": 0.88
        },
        "validate": lambda dt: dt.year == today.year and dt.replace(tzinfo=timezone.utc) > today,
    },
    {
        "name": "Specific date mentioned — March 20",
        "payload": {
            "meeting_id": "test-cal-005",
            "intent": "CALENDAR_EVENT",
            "extracted_action": "Book a review meeting on March 20 at 10am",
            "confidence": 0.96
        },
        "validate": lambda dt: dt.year >= today.year and dt.month == 3 and dt.day == 20,
    },
]


def extract_datetime_from_result(result):
    """
    Parse the executor's tool-use output to find start_datetime.
    Adjust this parsing logic based on your executor's actual response format.
    """
    # If the result is a string, try to parse it as JSON
    if isinstance(result, str):
        result = json.loads(result)

    # The executor typically returns the tool call parameters or the action payload.
    # Look for start_datetime in common locations:
    search_keys = ['start_datetime', 'start_time', 'startDateTime']

    def find_key(obj, keys):
        if isinstance(obj, dict):
            for k in keys:
                if k in obj:
                    return obj[k]
            for v in obj.values():
                found = find_key(v, keys)
                if found:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = find_key(item, keys)
                if found:
                    return found
        return None

    dt_str = find_key(result, search_keys)
    if not dt_str:
        return None

    # Try common ISO8601 formats
    for fmt in [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M",
    ]:
        try:
            # Handle invalid 24 HR instances explicitly 
            adjusted_dt_str = dt_str
            if "T24:" in adjusted_dt_str:
                # Need to push day forward if Bedrock returned 24:XX:XX
                adjusted_dt_str = adjusted_dt_str.replace("T24:", "T00:")
                parsed = datetime.strptime(adjusted_dt_str.replace("Z", "+00:00").rstrip("+00:00") if "Z" in adjusted_dt_str else adjusted_dt_str, fmt)
                return parsed + timedelta(days=1)
                
            return datetime.strptime(adjusted_dt_str.replace("Z", "+00:00").rstrip("+00:00") if "Z" in adjusted_dt_str else adjusted_dt_str, fmt)
        except ValueError:
            continue

    # Fallback: try dateutil if available
    try:
        from dateutil import parser as dateutil_parser
        return dateutil_parser.parse(dt_str)
    except ImportError:
        pass

    return None


def test_via_local_handler(payload):
    """Invoke the executor handler locally (calls Bedrock directly)."""
    from lambdas.executor.handler import handler

    # Use the payload directly as the event since that's what the executor handler expects
    response = handler(payload, None)

    if isinstance(response, dict) and 'body' in response:
        return json.loads(response['body'])
    return response


def test_via_remote_lambda(payload):
    """Invoke the deployed Lambda function directly."""
    import boto3

    client = boto3.client('lambda', region_name='us-east-1')
    response = client.invoke(
        FunctionName=LAMBDA_FUNCTION_NAME,
        InvocationType='RequestResponse',
        Payload=json.dumps(payload),
    )
    result = json.loads(response['Payload'].read().decode('utf-8'))

    if isinstance(result, dict) and 'body' in result:
        return json.loads(result['body'])
    return result


def run_tests():
    print("=" * 60)
    print("  EXECUTOR CALENDAR DATE FIX — UNIT TESTS")
    print(f"  Current UTC time: {today.strftime('%A, %B %d, %Y at %H:%M UTC')}")
    print("=" * 60)
    print()

    passed = 0
    failed = 0

    for i, tc in enumerate(test_cases, 1):
        print(f"Test {i}/{len(test_cases)}: {tc['name']}")
        print(f"  Input: \"{tc['payload']['extracted_action']}\"")

        try:
            if TEST_REMOTE_LAMBDA:
                result = test_via_remote_lambda(tc['payload'])
            else:
                result = test_via_local_handler(tc['payload'])

            print(f"  Raw result: {json.dumps(result, indent=2, default=str)[:300]}")

            dt = extract_datetime_from_result(result)

            if dt is None:
                print(f"  ❌ FAIL — Could not extract start_datetime from response")
                print(f"     Check the executor's response format and update extract_datetime_from_result()")
                failed += 1
            elif tc['validate'](dt):
                print(f"  ✅ PASS — Resolved to: {dt.isoformat()}")
                passed += 1
            else:
                print(f"  ❌ FAIL — Resolved to: {dt.isoformat()}")
                print(f"     Year={dt.year} (expected {today.year}), In future: {dt > today}")
                failed += 1

        except Exception as e:
            print(f"  ❌ ERROR — {type(e).__name__}: {e}")
            failed += 1

        print()

    print("=" * 60)
    print(f"  RESULTS: {passed} passed, {failed} failed out of {len(test_cases)}")
    print("=" * 60)

    if failed > 0:
        print("\n⚠️  Some tests failed. Check if:")
        print("   1. The datetime injection is in the right place in the system prompt")
        print("   2. The .env / AWS credentials are configured")
        print("   3. The executor response format matches what extract_datetime_from_result() expects")
        sys.exit(1)
    else:
        print("\n✅ All dates resolve correctly. Proceed to end-to-end testing.")
        sys.exit(0)


if __name__ == "__main__":
    run_tests()
