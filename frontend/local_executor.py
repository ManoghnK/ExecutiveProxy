"""
Local Executor Bridge for Electron.

Spawned as a subprocess by main.js. Receives JSON payload on stdin,
prints JSON status lines on stdout for real-time frontend updates,
then runs the executor handler locally with NOVA_ACT_ENABLED=true.
"""

import sys
import os
import json

# Force UTF-8 encoding for stdout/stderr to prevent Windows cp1252 crashes with Nova emojis
if sys.platform == "win32":
    import codecs
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Set up paths so we can import from lambdas/executor and nova_act_agent
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT_DIR, "lambdas", "executor"))
sys.path.insert(0, os.path.join(ROOT_DIR, "nova_act_agent"))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT_DIR, ".env"))
except ImportError:
    pass

# Enable Nova Act
os.environ["NOVA_ACT_ENABLED"] = "true"


def emit(status, message="", data=None):
    """Print a JSON status line to stdout for Electron to read."""
    line = {"status": status, "message": message}
    if data:
        line["data"] = data
    print(json.dumps(line), flush=True)


def main():
    # Read JSON payload from stdin
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        emit("FAILED", f"Invalid JSON input: {e}")
        sys.exit(1)

    intent = payload.get("intent", "UNKNOWN")
    extracted_action = payload.get("extracted_action", "")
    entities = payload.get("entities", {})
    meeting_id = payload.get("meeting_id", "unknown")

    emit("IN_PROGRESS", f"Processing {intent}...")

    try:
        # Import the executor's tool-use and execution functions
        from handler import invoke_tool_use, execute_jira, execute_calendar

        # Step 1: Extract parameters via Bedrock Nova Pro
        emit("IN_PROGRESS", f"Extracting parameters for {intent}...")
        tool_use = invoke_tool_use(intent, extracted_action, entities)

        if "error" in tool_use:
            emit("FAILED", f"Parameter extraction failed: {tool_use['error']}")
            sys.exit(1)

        tool_name = tool_use["name"]
        tool_input = tool_use["input"]

        # Step 2: Execute the action
        if tool_name == "create_jira_ticket":
            emit("IN_PROGRESS", "Nova Act is creating your Jira ticket...")
            result = execute_jira(tool_input)
            if not result.get("error"):
                ticket_id = result.get("ticket_id") or result.get("key", "")
                emit("COMPLETED", f"Ticket {ticket_id} created!", result)
            else:
                emit("FAILED", f"Jira API error: {result.get('error')}", result)

        elif tool_name == "create_calendar_event":
            emit("IN_PROGRESS", "Nova Act is creating your calendar event...")
            result = execute_calendar(tool_input)
            emit("COMPLETED", "Calendar event created!", result)

        else:
            emit("FAILED", f"Unknown tool: {tool_name}")

    except Exception as e:
        emit("FAILED", f"Executor error: {type(e).__name__}: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
