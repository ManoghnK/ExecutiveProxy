"""
DynamoDB Stream → AppSync Mutation Resolver.

This Lambda is triggered by DynamoDB Streams on both MeetingState and ActionLog
tables. It transforms stream records into AppSync GraphQL mutations, enabling
real-time subscriptions for the Electron frontend.

Flow: DynamoDB Stream → Lambda → AppSync Mutation → Subscription push

Environment variables:
  APPSYNC_API_URL  — AppSync GraphQL endpoint
  APPSYNC_API_KEY  — AppSync API key for auth
"""

import json
import os
import urllib.request
import urllib.error


APPSYNC_API_URL = os.environ.get("APPSYNC_API_URL", "")
APPSYNC_API_KEY = os.environ.get("APPSYNC_API_KEY", "")


def handler(event, context):
    """
    Process DynamoDB Stream records and invoke AppSync mutations.
    Handles batches of records from both MeetingState and ActionLog tables.
    """
    if not APPSYNC_API_URL or not APPSYNC_API_KEY:
        print("ERROR: APPSYNC_API_URL or APPSYNC_API_KEY not set")
        return {"statusCode": 500, "error": "AppSync config missing"}

    records = event.get("Records", [])
    print(f"Processing {len(records)} stream records")

    success_count = 0
    error_count = 0

    for record in records:
        event_name = record.get("eventName", "")

        # Only process INSERT and MODIFY events
        if event_name not in ("INSERT", "MODIFY"):
            print(f"Skipping {event_name} event")
            continue

        try:
            new_image = record.get("dynamodb", {}).get("NewImage", {})
            if not new_image:
                print("No NewImage in record, skipping")
                continue

            # Determine which table this stream event is from
            # by checking which keys are present
            parsed = _parse_dynamo_image(new_image)

            if "action_id" in parsed:
                # ActionLog record
                _invoke_action_mutation(parsed)
            elif "transcript_chunk" in parsed or "timestamp" in parsed:
                # MeetingState record
                _invoke_transcript_mutation(parsed)
            else:
                print(f"Unknown record shape: {list(parsed.keys())}")
                continue

            success_count += 1

        except Exception as e:
            print(f"Error processing record: {e}")
            error_count += 1

    print(f"Done: {success_count} success, {error_count} errors")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "processed": success_count,
            "errors": error_count,
        }),
    }


def _parse_dynamo_image(image: dict) -> dict:
    """
    Convert DynamoDB stream NewImage format to plain dict.
    DynamoDB format: {"field": {"S": "value"}, "num": {"N": "123"}}
    Output: {"field": "value", "num": "123"}
    """
    result = {}
    for key, type_value in image.items():
        if "S" in type_value:
            result[key] = type_value["S"]
        elif "N" in type_value:
            result[key] = type_value["N"]
        elif "BOOL" in type_value:
            result[key] = type_value["BOOL"]
        elif "NULL" in type_value:
            result[key] = None
        elif "L" in type_value:
            result[key] = json.dumps(type_value["L"])
        elif "M" in type_value:
            result[key] = json.dumps(type_value["M"])
        else:
            result[key] = str(type_value)
    return result


def _invoke_transcript_mutation(data: dict):
    """Call onTranscriptUpdate mutation via AppSync."""
    mutation = """
    mutation OnTranscriptUpdate(
        $meeting_id: ID!,
        $timestamp: String!,
        $speaker: String,
        $transcript_chunk: String,
        $intent_label: String,
        $action_triggered: Boolean
    ) {
        onTranscriptUpdate(
            meeting_id: $meeting_id,
            timestamp: $timestamp,
            speaker: $speaker,
            transcript_chunk: $transcript_chunk,
            intent_label: $intent_label,
            action_triggered: $action_triggered
        ) {
            meeting_id
            timestamp
            transcript_chunk
        }
    }
    """

    variables = {
        "meeting_id": data.get("meeting_id", ""),
        "timestamp": data.get("timestamp", ""),
        "speaker": data.get("speaker", ""),
        "transcript_chunk": data.get("transcript_chunk", ""),
        "intent_label": data.get("intent_label", ""),
        "action_triggered": bool(data.get("action_triggered", False)),
    }

    print(f"Transcript mutation: meeting={variables['meeting_id']}, "
          f"ts={variables['timestamp']}")

    _execute_graphql(mutation, variables)


def _invoke_action_mutation(data: dict):
    """Call onActionComplete mutation via AppSync."""
    mutation = """
    mutation OnActionComplete(
        $meeting_id: ID!,
        $action_id: ID!,
        $action_type: String!,
        $status: String!,
        $payload: String,
        $result: String,
        $created_at: String!
    ) {
        onActionComplete(
            meeting_id: $meeting_id,
            action_id: $action_id,
            action_type: $action_type,
            status: $status,
            payload: $payload,
            result: $result,
            created_at: $created_at
        ) {
            meeting_id
            action_id
            status
        }
    }
    """

    variables = {
        "meeting_id": data.get("meeting_id", ""),
        "action_id": data.get("action_id", ""),
        "action_type": data.get("action_type", "UNKNOWN"),
        "status": data.get("status", "UNKNOWN"),
        "payload": data.get("payload", ""),
        "result": data.get("result", ""),
        "created_at": data.get("created_at", ""),
    }

    print(f"Action mutation: meeting={variables['meeting_id']}, "
          f"action={variables['action_id']}, type={variables['action_type']}")

    _execute_graphql(mutation, variables)


def _execute_graphql(query: str, variables: dict):
    """
    Execute a GraphQL mutation against AppSync using API key auth.
    Uses urllib (no extra dependencies) for Lambda compatibility.
    """
    payload = json.dumps({
        "query": query,
        "variables": variables,
    }).encode("utf-8")

    req = urllib.request.Request(
        APPSYNC_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": APPSYNC_API_KEY,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if "errors" in body:
                print(f"GraphQL errors: {body['errors']}")
            else:
                print(f"GraphQL success: {json.dumps(body.get('data', {}))}")
            return body
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else "no body"
        print(f"HTTP {e.code} error calling AppSync: {error_body}")
        raise
    except urllib.error.URLError as e:
        print(f"URL error calling AppSync: {e.reason}")
        raise
