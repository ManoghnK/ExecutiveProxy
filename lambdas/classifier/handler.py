"""
Combined permissions for this handler:
- bedrock:InvokeModel on amazon.nova-2-lite-v1:0
- dynamodb:PutItem on MeetingState table
- lambda:InvokeFunction on executor Lambda ARN (if intent found)
"""

import os
import json
import boto3
import datetime
import decimal

# ── Config ────────────────────────────────────────────────────────────────────
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
DYNAMODB_MEETING_TABLE = os.environ.get("DYNAMODB_MEETING_TABLE", "MeetingState")
EXECUTOR_LAMBDA_NAME = os.environ.get("EXECUTOR_LAMBDA_NAME")

# Model ID
# Use Cross-Region Inference Profile for on-demand
CLASSIFIER_MODEL_ID = "us.amazon.nova-2-lite-v1:0"

# Clients
bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
lambda_client = boto3.client("lambda", region_name=AWS_REGION)


def classify_transcript(transcript_chunk: str) -> dict:
    """
    Uses Nova 2 Lite to classify the transcript chunk.
    Returns: {
        "intent": "JIRA_TICKET|CALENDAR_EVENT|POLICY_RISK|NO_ACTION",
        "confidence": 0.0-1.0,
        "extracted_action": str|None,
        "entities": dict
    }
    """
    system_prompt = (
        "You are a meeting action item detector. Analyze the transcript "
        "chunk and classify it into exactly ONE of these intents:\n"
        "- JIRA_TICKET: Someone is requesting a bug fix, task, or ticket creation "
        "(e.g. \"let's ticket that\", \"create a story for\", \"log that bug\")\n"
        "- CALENDAR_EVENT: Someone is scheduling a meeting or event "
        "(e.g. \"let's set up a call\", \"schedule a meeting\", \"block time for\")\n"
        "- POLICY_RISK: A decision or proposal is being made that may violate "
        "company policy, or someone is explicitly asking about policy, compliance, "
        "rules, or risks (e.g. \"let's offshore\", \"ship without review\", "
        "\"track employee\", \"skip the security check\", \"what are the compliance risks\").\n"
        "- NO_ACTION: General conversation with no actionable intent\n\n"
        "Respond with ONLY a JSON object:\n"
        "{\n"
        "  \"intent\": \"JIRA_TICKET|CALENDAR_EVENT|POLICY_RISK|NO_ACTION\",\n"
        "  \"confidence\": 0.0-1.0,\n"
        "  \"extracted_action\": \"one sentence describing the action, or null if NO_ACTION\",\n"
        "  \"entities\": {\"key\": \"value\"} // relevant entities extracted e.g. assignee, date, component\n"
        "}"
    )

    messages = [
        {
            "role": "user",
            "content": [{"text": transcript_chunk}]
        }
    ]

    try:
        response = bedrock.converse(
            modelId=CLASSIFIER_MODEL_ID,
            messages=messages,
            system=[{"text": system_prompt}],
            inferenceConfig={"temperature": 0.0}
        )
        output_text = response["output"]["message"]["content"][0]["text"]

        # Clean up code blocks if present
        if "```json" in output_text:
            output_text = output_text.split("```json")[1].split("```")[0].strip()
        elif "```" in output_text:
            output_text = output_text.split("```")[1].split("```")[0].strip()

        return json.loads(output_text)

    except Exception as e:
        print(f"Error invoking Nova 2 Lite: {e}")
        # Default fallback
        return {
            "intent": "NO_ACTION",
            "confidence": 0.0,
            "extracted_action": None,
            "entities": {}
        }


def invoke_executor(payload: dict):
    """Invoke the executor Lambda asynchronously."""
    if not EXECUTOR_LAMBDA_NAME:
        print("WARNING: EXECUTOR_LAMBDA_NAME not set. Skipping invocation.")
        return

    try:
        lambda_client.invoke(
            FunctionName=EXECUTOR_LAMBDA_NAME,
            InvocationType="Event",  # Asynchronous
            Payload=json.dumps(payload)
        )
        print(f"Invoked executor: {EXECUTOR_LAMBDA_NAME}")
    except Exception as e:
        print(f"Failed to invoke executor: {e}")


def handler(event, context):
    """
    Lambda Entrypoint.
    Event: {
        "meeting_id": "string",
        "speaker": "string",
        "transcript_chunk": "string",
        "timestamp": "ISO8601 string"
    }
    """
    meeting_id = event.get("meeting_id", "unknown-meeting")
    speaker = event.get("speaker", "Unknown")
    transcript_chunk = event.get("transcript_chunk", "")
    # Default timestamp if missing
    timestamp = event.get("timestamp", datetime.datetime.now().isoformat())

    print(f"Processing chunk for meeting {meeting_id}: {transcript_chunk[:50]}...")

    # 1. Classify
    classification = classify_transcript(transcript_chunk)
    intent = classification.get("intent", "NO_ACTION")
    confidence = classification.get("confidence", 0.0)
    
    # 2. Save to DynamoDB
    try:
        table = dynamodb.Table(DYNAMODB_MEETING_TABLE)
        item = {
            "meeting_id": meeting_id,
            "timestamp": timestamp,
            "speaker": speaker,
            "transcript_chunk": transcript_chunk,
            "intent_label": intent,
            "action_triggered": (intent != "NO_ACTION"),
            "confidence": str(confidence), # Store as string to avoid Decimal issues
            "classification_details": json.dumps(classification)
        }
        table.put_item(Item=item)
        print("Saved to DynamoDB.")
    except Exception as e:
        print(f"Error saving to DynamoDB: {e}")

    # 3. Escalate if actionable
    if intent != "NO_ACTION" and confidence >= 0.75:
        print(f"Action detected ({intent}, conf={confidence}). Escalating.")
        executor_payload = {
            "meeting_id": meeting_id,
            "speaker": speaker,
            "transcript_chunk": transcript_chunk,
            "intent": intent,
            "extracted_action": classification.get("extracted_action"),
            "entities": classification.get("entities", {})
        }
        invoke_executor(executor_payload)
    else:
        print(f"No action or low confidence ({intent}, conf={confidence}). Skipping escalation.")

    return {
        "statusCode": 200,
        "body": json.dumps(classification)
    }


if __name__ == "__main__":
    # Local Test Block
    print("Running local classification test...")
    
    # Mock environment if not set
    if not os.environ.get("DYNAMODB_MEETING_TABLE"):
        print("NOTE: DYNAMODB_MEETING_TABLE not set, DB writes will fail (expected in local dev without mock).")

    test_cases = [
        "Let's ticket that login bug and assign it to Sarah",
        "Can we schedule a sync for Thursday at 2pm?",
        "I think we should offshore the data processing to cut costs",
        "Yeah I agree that makes sense going forward"
    ]

    for text in test_cases:
        print("\n--- Test Case ---")
        print(f"Input: \"{text}\"")
        result = classify_transcript(text)
        print(f"Output: {json.dumps(result, indent=2)}")
