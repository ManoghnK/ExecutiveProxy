"""
Combined permissions:
- bedrock:InvokeModel on amazon.nova-pro-v1:0 (Cross-Region Inference Profile: us.amazon.nova-pro-v1:0)
- dynamodb:PutItem on ActionLog table
- lambda:InvokeFunction on rag_handler Lambda ARN
"""

import os
import json
import uuid
import datetime
import base64
import requests
import boto3

# ── Config ────────────────────────────────────────────────────────────────────
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
DYNAMODB_ACTION_TABLE = os.environ.get("DYNAMODB_ACTION_TABLE", "ActionLog")
RAG_LAMBDA_NAME = os.environ.get("RAG_LAMBDA_NAME")

# Jira Config
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL")
JIRA_USER_EMAIL = os.environ.get("JIRA_USER_EMAIL")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")
JIRA_PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY", "EP")

# Model ID (Using Inference Profile for stability)
EXECUTOR_MODEL_ID = "us.amazon.nova-pro-v1:0"

# Clients
bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
lambda_client = boto3.client("lambda", region_name=AWS_REGION)

# ── Tools ─────────────────────────────────────────────────────────────────────
TOOLS = [
    {
        "toolSpec": {
            "name": "create_jira_ticket",
            "description": "Creates a Jira ticket with the extracted details",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string", "description": "ticket title"},
                        "description": {"type": "string", "description": "detailed description"},
                        "issue_type": {"type": "string", "enum": ["Bug", "Task", "Story"]},
                        "priority": {"type": "string", "enum": ["Low", "Medium", "High", "Critical"]},
                        "assignee": {"type": "string", "nullable": True},
                        "labels": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["summary", "issue_type"]
                }
            }
        }
    },
    {
        "toolSpec": {
            "name": "create_calendar_event",
            "description": "Creates a Google Calendar event",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string", "nullable": True},
                        "start_datetime": {"type": "string", "description": "ISO8601 string"},
                        "end_datetime": {"type": "string", "description": "ISO8601 string"},
                        "attendees": {"type": "array", "items": {"type": "string"}},
                        "duration_minutes": {"type": "integer", "default": 30}
                    },
                    "required": ["title", "start_datetime"]
                }
            }
        }
    }
]

# ── Logic ─────────────────────────────────────────────────────────────────────

def log_action(meeting_id: str, action_type: str, status: str, payload: dict, result: dict):
    """Writes the action to DynamoDB."""
    try:
        table = dynamodb.Table(DYNAMODB_ACTION_TABLE)
        item = {
            "meeting_id": meeting_id,
            "action_id": str(uuid.uuid4()),
            "action_type": action_type,
            "status": status,
            "payload": json.dumps(payload),
            "result": json.dumps(result),
            "created_at": datetime.datetime.now().isoformat()
        }
        table.put_item(Item=item)
        print(f"Logged action ({status}): {action_type}")
    except Exception as e:
        print(f"Failed to log action: {e}")

def invoke_tool_use(intent: str, extracted_action: str, entities: dict) -> dict:
    """Invokes Nova Pro with tool definitions to extract structured parameters."""
    
    system_prompt = [{"text": f"You are an executive assistant. Your goal is to extract parameters for the '{intent}' action from the user request."}]
    
    user_message = f"""
    Action: {extracted_action}
    Entities: {json.dumps(entities)}
    
    Extract the necessary parameters and call the appropriate tool.
    If information is missing, infer reasonable defaults based on context.
    """
    
    messages = [{"role": "user", "content": [{"text": user_message}]}]
    
    try:
        # Nova Pro via Converse API
        response = bedrock.converse(
            modelId=EXECUTOR_MODEL_ID,
            messages=messages,
            system=system_prompt,
            toolConfig={"tools": TOOLS},
            inferenceConfig={"temperature": 0.0}
        )
        
        output_message = response["output"]["message"]
        content_blocks = output_message["content"]
        
        # Check for tool use
        for block in content_blocks:
            if "toolUse" in block:
                return block["toolUse"]
        
        # If no tool use, return text response or error
        return {"error": "No tool use generated by model", "raw_response": str(content_blocks)}
        
    except Exception as e:
        print(f"Error invoking Nova Pro: {e}")
        return {"error": str(e)}

def execute_jira(tool_input: dict) -> dict:
    """Calls Jira API."""
    if not (JIRA_BASE_URL and JIRA_USER_EMAIL and JIRA_API_TOKEN):
        return {"status": "SKIPPED", "reason": "Jira credentials not set"}
    
    try:
        url = f"{JIRA_BASE_URL}/rest/api/3/issue"
        auth_str = f"{JIRA_USER_EMAIL}:{JIRA_API_TOKEN}"
        encoded_auth = base64.b64encode(auth_str.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {encoded_auth}",
            "Content-Type": "application/json"
        }
        
        # JIRA Format
        payload = {
            "fields": {
                "project": {"key": JIRA_PROJECT_KEY},
                "summary": tool_input.get("summary"),
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [{
                        "type": "paragraph",
                        "content": [{"type": "text", "text": tool_input.get("description", "") or "No description"}]
                    }]
                },
                "issuetype": {"name": tool_input.get("issue_type", "Task")}
            }
        }
        
        print(f"Calling Jira: {url}")
        resp = requests.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()
        
    except Exception as e:
        # If response exists, return its text
        return {"error": str(e)}

def execute_calendar(tool_input: dict) -> dict:
    """Mock Google Calendar execution."""
    # TODO: Replace with Google Calendar API call
    print(f"MOCK CALENDAR: Creating event '{tool_input.get('title')}' at {tool_input.get('start_datetime')}")
    return {"status": "MOCKED", "data": tool_input}

def handler(event, context):
    """
    Main Executor Lambda
    Preconditions: event contains classified intent
    """
    meeting_id = event.get("meeting_id", "unknown")
    intent = event.get("intent", "NO_ACTION")
    extracted_action = event.get("extracted_action", "")
    entities = event.get("entities", {})
    
    print(f"Executor received: {intent} for {meeting_id}")
    
    result = {}
    status = "FAILED"
    
    try:
        if intent == "POLICY_RISK":
            # Handoff to RAG Handler
            if RAG_LAMBDA_NAME:
                print(f"Invoking RAG Handler: {RAG_LAMBDA_NAME}")
                payload = {"meeting_id": meeting_id, "query_text": extracted_action}
                lambda_client.invoke(
                    FunctionName=RAG_LAMBDA_NAME,
                    InvocationType="Event",
                    Payload=json.dumps(payload)
                )
                result = {"handoff": RAG_LAMBDA_NAME}
                status = "HANDOFF"
            else:
                result = {"error": "RAG_LAMBDA_NAME not set"}
                
        elif intent in ["JIRA_TICKET", "CALENDAR_EVENT"]:
            # 1. Extract Params using Nova Pro Tool Use
            tool_use = invoke_tool_use(intent, extracted_action, entities)
            
            if "error" in tool_use:
                result = tool_use
            else:
                tool_name = tool_use["name"]
                tool_input = tool_use["input"]
                
                print(f"Tool selected: {tool_name}")
                
                # 2. Execute Action
                if tool_name == "create_jira_ticket":
                    result = execute_jira(tool_input)
                    status = "COMPLETED" if "error" not in result else "FAILED"
                    
                elif tool_name == "create_calendar_event":
                    result = execute_calendar(tool_input)
                    status = "COMPLETED"
                else:
                    result = {"error": f"Unknown tool: {tool_name}"}
    
        else:
            result = {"info": "Intent not actionable or recognized"}
            status = "SKIPPED"

    except Exception as e:
        print(f"Executor Handler Error: {e}")
        status = "CRASHED"
        result = {"error": str(e)}

    # Log Outcome
    log_action(meeting_id, intent, status, {"action": extracted_action, "entities": entities}, result)

    return {
        "statusCode": 200,
        "body": json.dumps(result)
    }

if __name__ == "__main__":
    # Local Test Block
    print("Running local executor test...")
    # Mock DynamoDB
    class MockTable:
        def put_item(self, Item):
            print(f"[DynamoDB] PutItem: {Item['action_type']} - {Item['status']}")
            
    dynamodb.Table = lambda x: MockTable()
    
    # Mock Lambda Client (for RAG invocation)
    class MockLambda:
        def invoke(self, FunctionName, InvocationType, Payload):
            print(f"[Lambda] Invoking {FunctionName} (Async) with payload: {Payload}")
            return {}
            
    lambda_client = MockLambda()
    # Set RAG lambda name so mock invokes it
    RAG_LAMBDA_NAME = "mock-rag-lambda" 

    test_cases = [
        {
            "intent": "JIRA_TICKET",
            "extracted_action": "Fix the login bug where users get 401 on OAuth callback",
            "entities": {"assignee": "sarah", "component": "auth-service"}
        },
        {
            "intent": "CALENDAR_EVENT",
            "extracted_action": "Schedule a sync for Thursday at 2pm",
            "entities": {"day": "Thursday", "time": "2pm", "duration": "30 minutes"}
        },
        {
            "intent": "POLICY_RISK",
            "extracted_action": "Offshore data processing to reduce costs",
            "entities": {"department": "engineering", "risk_area": "data privacy"}
        }
    ]
    
    for case in test_cases:
        print(f"\n--- Test Case: {case['intent']} ---")
        case["meeting_id"] = "test-meeting-123"
        
        try:
            res = handler(case, None)
            print("Response:", json.dumps(res, indent=2))
        except Exception as e:
            print(f"Test failed: {e}")
