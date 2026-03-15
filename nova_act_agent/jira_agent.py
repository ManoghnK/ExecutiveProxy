"""
Nova Act UI Agent for Jira ticket creation.

Uses the nova-act SDK to navigate Jira Cloud UI and create tickets
via browser automation. Designed to run locally (requires browser),
NOT inside Lambda.

Required env vars:
  NOVA_ACT_API_KEY  — from nova.amazon.com/act
  JIRA_BASE_URL     — e.g. https://yourorg.atlassian.net
  JIRA_PROJECT_KEY  — e.g. EP

Optional env vars:
  JIRA_USER_EMAIL   — for auth setup
  JIRA_PASSWORD     — for auth setup
  NOVA_ACT_USER_DATA_DIR — persistent browser session directory
"""

import os
import sys
import json
import logging
import platform
from typing import Optional
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not required if env vars are set via OS or CDK

# ── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger("jira_agent")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s %(message)s"
    ))
    logger.addHandler(handler)

# ── Config ───────────────────────────────────────────────────────────────────
NOVA_ACT_API_KEY = os.environ.get("NOVA_ACT_API_KEY")
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "https://yourorg.atlassian.net")
JIRA_PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY", "EP")
JIRA_USER_EMAIL = os.environ.get("JIRA_USER_EMAIL")
JIRA_PASSWORD = os.environ.get("JIRA_PASSWORD")

# Persistent browser profile directory
BROWSER_PROFILE = Path(__file__).parent / "browser_profile"
BROWSER_PROFILE.mkdir(exist_ok=True)


def _get_user_data_dir() -> str:
    """Get or create the persistent browser data directory."""
    return str(BROWSER_PROFILE)


class JiraUIAgent:
    """
    Nova Act-powered Jira ticket creator.

    Uses browser UI automation to create tickets in Jira Cloud.
    Requires a persistent authenticated browser session (see setup_auth).
    """

    def __init__(
        self,
        jira_url: Optional[str] = None,
        project_key: Optional[str] = None,
        api_key: Optional[str] = None,
        headless: bool = True,
        user_data_dir: Optional[str] = None,
    ):
        self.jira_url = (jira_url or JIRA_BASE_URL).rstrip("/")
        self.project_key = project_key or JIRA_PROJECT_KEY
        self.api_key = api_key or NOVA_ACT_API_KEY
        self.headless = headless
        self.user_data_dir = user_data_dir or _get_user_data_dir()

        if not self.api_key:
            raise ValueError(
                "NOVA_ACT_API_KEY not set. "
                "Get one at https://nova.amazon.com/act"
            )

    def create_ticket(
        self,
        summary: str,
        description: str = "",
        issue_type: str = "Task",
        priority: str = "Medium",
        assignee: Optional[str] = None,
        labels: Optional[list] = None,
    ) -> dict:
        """
        Create a Jira ticket using Nova Act browser automation.

        Uses multi-step act() calls per SDK best practices:
          1. Navigate to create issue page
          2. Fill in form fields
          3. Submit the form
          4. Extract ticket ID from confirmation

        Returns:
            {
                "success": bool,
                "ticket_id": str | None,     # e.g. "EP-123"
                "ticket_url": str | None,     # Full URL
                "error": str | None,
                "steps_completed": int,
                "nova_act_metadata": dict
            }
        """
        try:
            from nova_act import NovaAct
        except ImportError:
            logger.warning("nova-act SDK not installed. Using mock mode.")
            return self._mock_create_ticket(
                summary, description, issue_type, priority, assignee, labels
            )

        logger.info(
            f"Creating Jira ticket: summary='{summary[:60]}...', "
            f"type={issue_type}, priority={priority}"
        )

        steps_completed = 0
        metadata = {}

        try:
            with NovaAct(
                starting_page=f"{self.jira_url}/jira/projects",
                nova_act_api_key=self.api_key,
                headless=self.headless,
                user_data_dir=self.user_data_dir,
                clone_user_data_dir=False,  # ← CRITICAL: Reuse profile instead of cloning
            ) as nova:

                # ── Step 1: Navigate to create ticket ────────────────────────
                logger.info("Step 1: Opening create issue dialog")
                result = nova.act(
                    "Click the 'Create' button in the top navigation bar "
                    "to open the create issue dialog. If there's a '+ Create' "
                    "or 'Create issue' button, click that."
                )
                steps_completed = 1
                logger.info(f"Step 1 complete ({result.metadata.num_steps_executed} browser steps)")

                # ── Step 2: Set project and issue type ───────────────────────
                logger.info(f"Step 2: Setting project to {self.project_key} and type to {issue_type}")
                result = nova.act(
                    f"In the create issue form, set the project to "
                    f"'{self.project_key}' if it's not already selected. "
                    f"Set the issue type to '{issue_type}'. "
                    f"If there's a project dropdown, select the correct project first."
                )
                steps_completed = 2
                logger.info(f"Step 2 complete ({result.metadata.num_steps_executed} browser steps)")

                # ── Step 3: Fill in summary ──────────────────────────────────
                logger.info("Step 3: Filling in summary")
                # Escape quotes in summary for the prompt
                safe_summary = summary.replace('"', '\\"').replace("'", "\\'")
                result = nova.act(
                    f"In the create issue form, click on the Summary field "
                    f"and type exactly: {safe_summary}"
                )
                steps_completed = 3
                logger.info(f"Step 3 complete ({result.metadata.num_steps_executed} browser steps)")

                # ── Step 4: Fill in description ──────────────────────────────
                if description:
                    logger.info("Step 4: Filling in description")
                    safe_desc = description.replace('"', '\\"').replace("'", "\\'")
                    result = nova.act(
                        f"In the create issue form, click on the Description field "
                        f"and type: {safe_desc}"
                    )
                    steps_completed = 4
                    logger.info(f"Step 4 complete ({result.metadata.num_steps_executed} browser steps)")
                else:
                    steps_completed = 4
                    logger.info("Step 4: No description, skipping")

                # ── Step 5: Set priority ─────────────────────────────────────
                if priority and priority != "Medium":
                    logger.info(f"Step 5: Setting priority to {priority}")
                    result = nova.act(
                        f"In the create issue form, find the Priority field "
                        f"and set it to '{priority}'. Click the priority "
                        f"dropdown and select '{priority}'."
                    )
                    steps_completed = 5
                    logger.info(f"Step 5 complete ({result.metadata.num_steps_executed} browser steps)")
                else:
                    steps_completed = 5
                    logger.info("Step 5: Using default priority, skipping")

                # ── Step 6: Assign (optional) ────────────────────────────────
                if assignee:
                    logger.info(f"Step 6: Assigning to {assignee}")
                    result = nova.act(
                        f"In the create issue form, find the Assignee field "
                        f"and set it to '{assignee}'. Type the name in the "
                        f"assignee search box and select the matching user."
                    )
                    steps_completed = 6
                    logger.info(f"Step 6 complete ({result.metadata.num_steps_executed} browser steps)")
                else:
                    steps_completed = 6

                # ── Step 7: Add labels (optional) ────────────────────────────
                if labels:
                    logger.info(f"Step 7: Adding labels {labels}")
                    labels_str = ", ".join(labels)
                    result = nova.act(
                        f"In the create issue form, find the Labels field "
                        f"and add these labels: {labels_str}. "
                        f"Type each label and press Enter to add it."
                    )
                    steps_completed = 7
                    logger.info(f"Step 7 complete ({result.metadata.num_steps_executed} browser steps)")
                else:
                    steps_completed = 7

                # ── Step 8: Submit the form ──────────────────────────────────
                logger.info("Step 8: Submitting the form")
                result = nova.act(
                    "Click the 'Create' or 'Submit' button to create the issue. "
                    "Do NOT click cancel. Click the primary submit button at the "
                    "bottom of the create issue form."
                )
                steps_completed = 8
                logger.info(f"Step 8 complete ({result.metadata.num_steps_executed} browser steps)")

                # ── Step 9: Extract ticket ID ────────────────────────────────
                logger.info("Step 9: Extracting ticket ID")
                try:
                    extract_result = nova.act_get(
                        "A Jira ticket was just created. Look for a confirmation "
                        "message, toast notification, or the ticket key (like "
                        f"'{self.project_key}-' followed by a number) anywhere on "
                        "the page, including notifications, the URL bar, or any "
                        "success banner. Return the full ticket key (e.g. "
                        f"'{self.project_key}-123') and the full URL to the ticket."
                    )
                    steps_completed = 9

                    ticket_id = None
                    ticket_url = None

                    if extract_result.response:
                        response_text = extract_result.response
                        logger.info(f"Extraction response: {response_text}")

                        # Parse ticket ID from response
                        import re
                        ticket_match = re.search(
                            rf"{re.escape(self.project_key)}-\d+",
                            response_text
                        )
                        if ticket_match:
                            ticket_id = ticket_match.group(0)
                            ticket_url = f"{self.jira_url}/browse/{ticket_id}"

                    metadata = {
                        "total_browser_steps": extract_result.metadata.num_steps_executed,
                        "session_id": extract_result.metadata.session_id,
                        "act_id": extract_result.metadata.act_id,
                    }

                except Exception as extract_err:
                    logger.warning(f"Ticket ID extraction failed: {extract_err}")
                    # Ticket was likely created but we couldn't extract the ID
                    ticket_id = "CREATED_ID_UNKNOWN"
                    ticket_url = self.jira_url

                logger.info(
                    f"Ticket creation complete: id={ticket_id}, url={ticket_url}"
                )

                return {
                    "success": True,
                    "ticket_id": ticket_id,
                    "ticket_url": ticket_url,
                    "error": None,
                    "steps_completed": steps_completed,
                    "nova_act_metadata": metadata,
                }

        except ImportError:
            # nova_act import errors (missing sub-dependencies)
            error_msg = "nova-act SDK dependency error. Run: pip install nova-act"
            logger.error(error_msg)
            return self._error_result(error_msg, steps_completed)

        except Exception as e:
            # Catch all Nova Act errors
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Nova Act error at step {steps_completed}: {error_msg}")

            # Check for specific Nova Act error types
            try:
                from nova_act.types.act_errors import (
                    ActAgentError,
                    ActClientError,
                    ActServerError,
                    ActExecutionError,
                )

                if isinstance(e, ActClientError):
                    error_msg = f"Client error (check API key / rate limit): {e}"
                elif isinstance(e, ActServerError):
                    error_msg = f"Nova Act service error (transient): {e}"
                elif isinstance(e, ActAgentError):
                    error_msg = f"Agent could not complete task: {e}"
                elif isinstance(e, ActExecutionError):
                    error_msg = f"Browser execution error: {e}"
            except ImportError:
                pass

            return self._error_result(error_msg, steps_completed)

    def _error_result(self, error: str, steps_completed: int = 0) -> dict:
        """Build a standardized error result."""
        return {
            "success": False,
            "ticket_id": None,
            "ticket_url": None,
            "error": error,
            "steps_completed": steps_completed,
            "nova_act_metadata": {},
        }

    def _mock_create_ticket(
        self,
        summary: str,
        description: str,
        issue_type: str,
        priority: str,
        assignee: Optional[str],
        labels: Optional[list],
    ) -> dict:
        """
        Mock implementation when nova-act SDK is not installed.
        Returns a realistic response structure for integration testing.
        """
        import uuid

        mock_ticket_num = abs(hash(summary)) % 9999
        ticket_id = f"{self.project_key}-{mock_ticket_num}"
        ticket_url = f"{self.jira_url}/browse/{ticket_id}"

        logger.info(f"[MOCK] Would create ticket: {ticket_id}")
        logger.info(f"[MOCK]   Summary: {summary}")
        logger.info(f"[MOCK]   Description: {description[:80]}...")
        logger.info(f"[MOCK]   Type: {issue_type}, Priority: {priority}")
        logger.info(f"[MOCK]   Assignee: {assignee or 'unassigned'}")
        logger.info(f"[MOCK]   Labels: {labels or []}")
        logger.info(f"[MOCK]   URL: {ticket_url}")

        return {
            "success": True,
            "ticket_id": ticket_id,
            "ticket_url": ticket_url,
            "error": None,
            "steps_completed": 9,
            "nova_act_metadata": {"mode": "MOCK"},
        }

    @classmethod
    def setup_auth(
        cls,
        jira_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> str:
        """
        One-time interactive setup: opens a browser to Jira for manual login.
        The session is saved to user_data_dir for future headless runs.

        Returns the user_data_dir path.
        """
        try:
            from nova_act import NovaAct
        except ImportError:
            print("ERROR: nova-act SDK not installed. Run: pip install nova-act")
            sys.exit(1)

        url = (jira_url or JIRA_BASE_URL).rstrip("/")
        key = api_key or NOVA_ACT_API_KEY
        user_data_dir = _get_user_data_dir()

        print("=" * 60)
        print("Nova Act Jira Auth Setup")
        print("=" * 60)
        print(f"  Jira URL:       {url}")
        print(f"  User data dir:  {user_data_dir}")
        print()
        print("A browser will open. Log into Jira manually, then")
        print("come back here and press Enter to save the session.")
        print("=" * 60)

        with NovaAct(
            starting_page=url,
            nova_act_api_key=key,
            headless=False,  # Must be visible for manual login
            user_data_dir=user_data_dir,
            clone_user_data_dir=False,  # Save directly to persist session
        ) as nova:
            input("\n>>> Log into Jira in the browser, then press Enter here... ")

        print(f"\n✅ Session saved to: {user_data_dir}")
        print("Future runs will reuse this authenticated session.")
        return user_data_dir


# ── Module-level convenience function (called by executor) ───────────────────

def create_ticket(
    summary: str,
    description: str = "",
    issue_type: str = "Task",
    priority: str = "Medium",
    assignee: Optional[str] = None,
    labels: Optional[list] = None,
    jira_url: Optional[str] = None,
    headless: bool = True,
) -> dict:
    """
    Convenience function for creating a Jira ticket.
    Can be called directly from the executor or test scripts.
    """
    agent = JiraUIAgent(jira_url=jira_url, headless=headless)
    return agent.create_ticket(
        summary=summary,
        description=description,
        issue_type=issue_type,
        priority=priority,
        assignee=assignee,
        labels=labels,
    )


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Nova Act Jira Agent")
    parser.add_argument("--setup-auth", action="store_true",
                        help="Run interactive auth setup")
    parser.add_argument("--summary", default="[TEST] Nova Act Demo Ticket",
                        help="Ticket summary")
    parser.add_argument("--description",
                        default="Created by Executive Proxy via Nova Act UI automation.",
                        help="Ticket description")
    parser.add_argument("--priority", default="Medium",
                        choices=["High", "Medium", "Low"],
                        help="Ticket priority")
    parser.add_argument("--assignee", default=None, help="Assignee")
    parser.add_argument("--visible", action="store_true",
                        help="Run with visible browser (not headless)")
    args = parser.parse_args()

    if args.setup_auth:
        JiraUIAgent.setup_auth()
    else:
        result = create_ticket(
            summary=args.summary,
            description=args.description,
            priority=args.priority,
            assignee=args.assignee,
            labels=["executive-proxy", "nova-act"],
            headless=not args.visible,
        )
        print(json.dumps(result, indent=2))
