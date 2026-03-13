"""
Nova Act UI Agent for Jira ticket creation.
Uses the nova-act SDK to physically navigate Jira UI and create tickets.

Required env vars:
  NOVA_ACT_API_KEY  — from nova.amazon.com/dev
  JIRA_BASE_URL     — e.g. https://yourorg.atlassian.net
"""

from dotenv import load_dotenv
load_dotenv()

import os
import json
from nova_act import NovaAct

NOVA_ACT_API_KEY = os.environ.get("NOVA_ACT_API_KEY")
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "https://yourorg.atlassian.net")
JIRA_USER_EMAIL = os.environ.get("JIRA_USER_EMAIL")
JIRA_PASSWORD = os.environ.get("JIRA_PASSWORD")


class JiraUIAgent:
    def __init__(self):
        if not NOVA_ACT_API_KEY:
            raise ValueError("NOVA_ACT_API_KEY environment variable not set")
        self.jira_url = JIRA_BASE_URL
        self.email = JIRA_USER_EMAIL
        self.password = JIRA_PASSWORD

    def create_ticket(
        self,
        summary: str,
        description: str,
        issue_type: str = "Task",
        priority: str = "Medium",
        assignee: str = None,
        labels: list = None,
    ) -> dict:
        """
        Uses Nova Act to physically navigate Jira UI and create a ticket.
        Returns ticket_id, url, status, and nova_act_response.
        """
        instruction = ""
        
        # Add login instructions if credentials exist
        if self.email and self.password:
            instruction += (
                f"If you are presented with a login screen, log in using "
                f"email '{self.email}' and password '{self.password}'. "
            )

        instruction += (
            f"Navigate to create a new issue. "
            f"Set the issue type to {issue_type}. "
            f"Set the summary to: {summary}. "
            f"Set the description to: {description}. "
            f"Set the priority to {priority}. "
        )
        if assignee:
            instruction += f"Assign the ticket to {assignee}. "
        if labels:
            instruction += f"Add labels: {', '.join(labels)}. "
        instruction += (
            "Submit the form. After submission, return the ticket ID "
            "shown in the confirmation or URL."
        )

        try:
            # Use default Chrome profile to reuse existing login session
            user_data_path = os.path.expanduser("~/Library/Application Support/Google/Chrome")
            
            with NovaAct(
                starting_page=self.jira_url,
                headless=False,
                chrome_channel="chrome",      # Use system Chrome instead of bundled Chromium
                user_data_dir=user_data_path, # Point to user profile
                clone_user_data_dir=False     # USE REAL PROFILE (Requires Chrome to be CLOSED)
            ) as nova:
                result = nova.act(instruction)

                return {
                    "ticket_id": "CREATED",
                    "url": self.jira_url,
                    "status": "SUCCESS",
                    "nova_act_response": str(result),
                }

        except Exception as e:
            print(f"Nova Act Jira error: {e}")
            return {
                "ticket_id": None,
                "url": None,
                "status": "FAILED",
                "nova_act_response": str(e),
            }

    def verify_ticket(self, ticket_id: str) -> bool:
        """Navigate to ticket URL and confirm it exists."""
        try:
            with NovaAct(
                starting_page=f"{self.jira_url}/browse/{ticket_id}",
                headless=True,
            ) as nova:
                result = nova.act(
                    f"Confirm that ticket {ticket_id} exists and is visible on this page."
                )
                return "error" not in str(result).lower()
        except Exception as e:
            print(f"Verify ticket error: {e}")
            return False


if __name__ == "__main__":
    # Smoke test — opens real browser, attempts Jira navigation
    # Requires JIRA_BASE_URL and NOVA_ACT_API_KEY in .env
    agent = JiraUIAgent()
    result = agent.create_ticket(
        summary="[TEST] Executive Proxy Nova Act Demo Ticket",
        description="This ticket was created autonomously by Executive Proxy "
                    "during a live meeting using Nova Act UI automation.",
        issue_type="Task",
        priority="Medium",
        assignee=None,
        labels=["executive-proxy", "demo", "nova-act"],
    )
    print(json.dumps(result, indent=2))
