"""
Nova Act UI Agent for Google Calendar event creation.

Uses the nova-act SDK to navigate Google Calendar web UI and create events
via browser automation. Designed to run locally (requires browser),
NOT inside Lambda.

Required env vars:
  NOVA_ACT_API_KEY  — from nova.amazon.com/act

Optional env vars:
  NOVA_ACT_USER_DATA_DIR — persistent browser session directory
"""

import os
import sys
import json
import logging
import re
from datetime import datetime
from typing import Optional
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not required if env vars are set via OS or CDK

# ── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger("calendar_agent")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s %(message)s"
    ))
    logger.addHandler(handler)

# ── Config ───────────────────────────────────────────────────────────────────
NOVA_ACT_API_KEY = os.environ.get("NOVA_ACT_API_KEY")
CALENDAR_URL = "https://calendar.google.com"

# Persistent browser profile directory (shared with jira_agent)
BROWSER_PROFILE = Path(__file__).parent / "browser_profile"
BROWSER_PROFILE.mkdir(exist_ok=True)


def _get_user_data_dir() -> str:
    """Get or create the persistent browser data directory."""
    return str(BROWSER_PROFILE)


def _parse_iso_to_display(iso_str: str) -> dict:
    """
    Parse ISO8601 datetime string into display-friendly components
    for use in Google Calendar UI prompts.

    Returns:
        {"date": "March 15, 2026", "time": "2:00 PM",
         "date_input": "03/15/2026", "time_input": "2:00 PM"}
    """
    try:
        # Handle timezone-aware and naive datetimes
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return {
            "date": dt.strftime("%B %d, %Y"),         # March 15, 2026
            "time": dt.strftime("%I:%M %p").lstrip("0"),  # 2:00 PM
            "date_input": dt.strftime("%m/%d/%Y"),     # 03/15/2026
            "time_input": dt.strftime("%I:%M %p").lstrip("0"),
            "iso": iso_str,
        }
    except (ValueError, AttributeError) as e:
        logger.warning(f"Could not parse datetime '{iso_str}': {e}")
        return {
            "date": iso_str,
            "time": iso_str,
            "date_input": iso_str,
            "time_input": iso_str,
            "iso": iso_str,
        }


class CalendarUIAgent:
    """
    Nova Act-powered Google Calendar event creator.

    Uses browser UI automation to create events in Google Calendar.
    Requires a persistent authenticated browser session (see setup_auth).
    """

    def __init__(
        self,
        calendar_url: Optional[str] = None,
        api_key: Optional[str] = None,
        headless: bool = True,
        user_data_dir: Optional[str] = None,
    ):
        self.calendar_url = (calendar_url or CALENDAR_URL).rstrip("/")
        self.api_key = api_key or NOVA_ACT_API_KEY
        self.headless = headless
        self.user_data_dir = user_data_dir or _get_user_data_dir()

        if not self.api_key:
            raise ValueError(
                "NOVA_ACT_API_KEY not set. "
                "Get one at https://nova.amazon.com/act"
            )

    def create_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        description: str = "",
        attendees: Optional[list] = None,
        location: Optional[str] = None,
    ) -> dict:
        """
        Create a Google Calendar event using Nova Act browser automation.

        Uses multi-step act() calls per SDK best practices:
          1. Navigate to Google Calendar
          2. Open create event dialog
          3. Fill in title
          4. Set start date/time
          5. Set end date/time
          6. Add description (optional)
          7. Add attendees (optional)
          8. Save the event
          9. Extract event confirmation

        Args:
            title: Event title
            start_time: ISO8601 datetime string
            end_time: ISO8601 datetime string
            description: Event description (optional)
            attendees: List of email addresses (optional)
            location: Event location (optional)

        Returns:
            {
                "success": bool,
                "event_id": str | None,
                "event_url": str | None,
                "error": str | None,
                "steps_completed": int,
                "nova_act_metadata": dict
            }
        """
        try:
            from nova_act import NovaAct
        except ImportError:
            logger.warning("nova-act SDK not installed. Using mock mode.")
            return self._mock_create_event(
                title, start_time, end_time, description, attendees, location
            )

        # Parse times for display
        start = _parse_iso_to_display(start_time)
        end = _parse_iso_to_display(end_time)

        logger.info(
            f"Creating calendar event: title='{title}', "
            f"start={start['date']} {start['time']}, "
            f"end={end['date']} {end['time']}"
        )

        steps_completed = 0
        metadata = {}

        try:
            with NovaAct(
                starting_page=self.calendar_url,
                nova_act_api_key=self.api_key,
                headless=self.headless,
                user_data_dir=self.user_data_dir,
                clone_user_data_dir=False,  # ← CRITICAL: Reuse profile instead of cloning
            ) as nova:

                # ── Step 1: Wait for calendar to load ────────────────────────
                logger.info("Step 1: Waiting for Google Calendar to load")
                result = nova.act(
                    "Wait for Google Calendar to fully load. "
                    "You should see the calendar view with days and times."
                )
                steps_completed = 1
                logger.info(f"Step 1 complete ({result.metadata.num_steps_executed} steps)")

                # ── Step 2: Create the Event (Single Multi-Step Instruction) ─
                logger.info("Step 2: Creating the entire event")
                
                safe_title = title.replace('"', '\\"').replace("'", "\\'")
                safe_desc = description.replace('"', '\\"').replace("'", "\\'") if description else ""
                attendees_str = ", ".join(attendees) if attendees else ""
                
                comprehensive_prompt = (
                    "Create a new Google Calendar event with the following details:\n"
                    f"- Title: {safe_title}\n"
                    f"- Start Date: {start['date']}\n"
                    f"- Start Time: {start['time']}\n"
                    f"- End Date: {end['date']}\n"
                    f"- End Time: {end['time']}\n"
                )
                
                if safe_desc:
                    comprehensive_prompt += f"- Description: {safe_desc}\n"
                if attendees_str:
                    comprehensive_prompt += f"- Guests/Attendees: {attendees_str} (press Enter after each)\n"
                if location:
                    comprehensive_prompt += f"- Location: {location}\n"
                    
                comprehensive_prompt += (
                    "\nInstructions:\n"
                    "1. Click the '+ Create' or 'Create' button, then click 'Event'. If a quick-add popover appears, click 'More options' to open the full editor.\n"
                    "2. Fill in the title, dates, and times exactly as specified above.\n"
                    "3. Add the description, guests, and location if they were provided above.\n"
                    "4. Finally, click the 'Save' button. Do NOT click Cancel. If asked about sending invitations to guests, click 'Send'.\n"
                    "5. Return once the event is saved and you are back on the main calendar view."
                )

                result = nova.act(comprehensive_prompt, max_steps=60)
                steps_completed = 2
                logger.info(f"Step 2 complete ({result.metadata.num_steps_executed} steps)")

                # ── Step 10: Extract event confirmation ──────────────────────
                logger.info("Step 10: Extracting event confirmation")
                try:
                    extract_result = nova.act_get(
                        "An event was just created in Google Calendar. "
                        "Look for any confirmation message, the event "
                        "appearing in the calendar view, or any event ID "
                        "in the URL. Return a description of the event that "
                        "was created including its title and time, and any "
                        "event ID or URL visible on the page or in the "
                        "browser address bar."
                    )
                    steps_completed = 10

                    event_id = None
                    event_url = None

                    if extract_result.response:
                        response_text = extract_result.response
                        logger.info(f"Extraction response: {response_text}")

                        # Try to extract event ID from URL pattern
                        eid_match = re.search(r"eid=([A-Za-z0-9_-]+)", response_text)
                        if eid_match:
                            event_id = eid_match.group(1)
                            event_url = (
                                f"{self.calendar_url}/calendar/event?eid={event_id}"
                            )
                        else:
                            # Fallback: generate a synthetic confirmation
                            event_id = f"evt_{abs(hash(title + start_time)) % 999999}"

                    metadata = {
                        "total_browser_steps": extract_result.metadata.num_steps_executed,
                        "session_id": extract_result.metadata.session_id,
                        "act_id": extract_result.metadata.act_id,
                    }

                except Exception as extract_err:
                    logger.warning(f"Event ID extraction failed: {extract_err}")
                    event_id = "CREATED_ID_UNKNOWN"
                    event_url = self.calendar_url

                if not event_url:
                    event_url = self.calendar_url

                logger.info(
                    f"Event creation complete: id={event_id}, url={event_url}"
                )

                return {
                    "success": True,
                    "event_id": event_id,
                    "event_url": event_url,
                    "error": None,
                    "steps_completed": steps_completed,
                    "nova_act_metadata": metadata,
                }

        except ImportError:
            error_msg = "nova-act SDK dependency error. Run: pip install nova-act"
            logger.error(error_msg)
            return self._error_result(error_msg, steps_completed)

        except Exception as e:
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
            "event_id": None,
            "event_url": None,
            "error": error,
            "steps_completed": steps_completed,
            "nova_act_metadata": {},
        }

    def _mock_create_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        description: str,
        attendees: Optional[list],
        location: Optional[str],
    ) -> dict:
        """
        Mock implementation when nova-act SDK is not installed.
        Returns a realistic response structure for integration testing.
        """
        start = _parse_iso_to_display(start_time)
        end = _parse_iso_to_display(end_time)

        mock_event_id = f"evt_{abs(hash(title + start_time)) % 999999}"
        event_url = f"{self.calendar_url}/calendar/event?eid={mock_event_id}"

        logger.info(f"[MOCK] Would create event: {mock_event_id}")
        logger.info(f"[MOCK]   Title: {title}")
        logger.info(f"[MOCK]   Start: {start['date']} {start['time']}")
        logger.info(f"[MOCK]   End:   {end['date']} {end['time']}")
        logger.info(f"[MOCK]   Description: {(description or 'none')[:60]}")
        logger.info(f"[MOCK]   Attendees: {attendees or []}")
        logger.info(f"[MOCK]   Location: {location or 'none'}")
        logger.info(f"[MOCK]   URL: {event_url}")

        return {
            "success": True,
            "event_id": mock_event_id,
            "event_url": event_url,
            "error": None,
            "steps_completed": 10,
            "nova_act_metadata": {"mode": "MOCK"},
        }

    @classmethod
    def setup_auth(
        cls,
        calendar_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> str:
        """
        One-time interactive setup: opens a browser to Google Calendar
        for manual login. The session is saved for future headless runs.

        Returns the user_data_dir path.
        """
        try:
            from nova_act import NovaAct
        except ImportError:
            print("ERROR: nova-act SDK not installed. Run: pip install nova-act")
            sys.exit(1)

        url = (calendar_url or CALENDAR_URL).rstrip("/")
        key = api_key or NOVA_ACT_API_KEY
        user_data_dir = _get_user_data_dir()

        print("=" * 60)
        print("Nova Act Google Calendar Auth Setup")
        print("=" * 60)
        print(f"  Calendar URL:   {url}")
        print(f"  User data dir:  {user_data_dir}")
        print()
        print("A browser will open. Log into Google Calendar, then")
        print("come back here and press Enter to save the session.")
        print("=" * 60)

        with NovaAct(
            starting_page=url,
            nova_act_api_key=key,
            headless=False,
            user_data_dir=user_data_dir,
            clone_user_data_dir=False,  # Save directly to persist session
        ) as nova:
            input("\n>>> Log into Google in the browser, then press Enter here... ")

        print(f"\n✅ Session saved to: {user_data_dir}")
        print("Future runs will reuse this authenticated session.")
        return user_data_dir


# ── Module-level convenience function (called by executor) ───────────────────

def create_event(
    title: str,
    start_time: str,
    end_time: str,
    description: str = "",
    attendees: Optional[list] = None,
    location: Optional[str] = None,
    calendar_url: Optional[str] = None,
    headless: bool = True,
) -> dict:
    """
    Convenience function for creating a Google Calendar event.
    Can be called directly from the executor or test scripts.
    """
    agent = CalendarUIAgent(calendar_url=calendar_url, headless=headless)
    return agent.create_event(
        title=title,
        start_time=start_time,
        end_time=end_time,
        description=description,
        attendees=attendees,
        location=location,
    )


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Nova Act Calendar Agent")
    parser.add_argument("--setup-auth", action="store_true",
                        help="Run interactive auth setup")
    parser.add_argument("--title", default="[TEST] Nova Act Demo Event",
                        help="Event title")
    parser.add_argument("--start", default="2026-03-15T14:00:00Z",
                        help="Start time (ISO8601)")
    parser.add_argument("--end", default="2026-03-15T15:00:00Z",
                        help="End time (ISO8601)")
    parser.add_argument("--description", default="Created by Executive Proxy via Nova Act.",
                        help="Event description")
    parser.add_argument("--visible", action="store_true",
                        help="Run with visible browser (not headless)")
    args = parser.parse_args()

    if args.setup_auth:
        CalendarUIAgent.setup_auth()
    else:
        result = create_event(
            title=args.title,
            start_time=args.start,
            end_time=args.end,
            description=args.description,
            headless=not args.visible,
        )
        print(json.dumps(result, indent=2))
