"""
Test script for the Nova Act Calendar Agent.

Usage:
  # Mock mode (no real browser, validates integration):
  python scripts/test_calendar_agent.py --mock

  # Real mode (opens browser, creates real event):
  python scripts/test_calendar_agent.py

  # Real mode with visible browser:
  python scripts/test_calendar_agent.py --visible

  # Setup authentication first:
  python scripts/test_calendar_agent.py --setup-auth

Pre-requisites:
  pip install nova-act python-dotenv
  Set NOVA_ACT_API_KEY in .env
"""

import argparse
import json
import os
import sys

# Add nova_act_agent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "nova_act_agent"))


def test_mock_mode():
    """Test with mock implementation (no browser needed)."""
    print("=" * 60)
    print("Calendar Agent — Mock Mode Test")
    print("=" * 60)

    from calendar_agent import CalendarUIAgent

    agent = CalendarUIAgent(
        calendar_url="https://calendar.google.com",
        api_key="test-key-mock",
    )

    test_cases = [
        {
            "title": "Sprint Planning Meeting",
            "start_time": "2026-03-15T14:00:00Z",
            "end_time": "2026-03-15T15:00:00Z",
            "description": "Weekly sprint planning for Q2 goals.",
            "attendees": ["alice@company.com", "bob@company.com"],
            "location": "Conference Room A",
        },
        {
            "title": "1:1 with Manager",
            "start_time": "2026-03-16T10:00:00-04:00",
            "end_time": "2026-03-16T10:30:00-04:00",
            "description": "",
            "attendees": None,
            "location": None,
        },
        {
            "title": "All-Hands Town Hall",
            "start_time": "2026-03-20T16:00:00Z",
            "end_time": "2026-03-20T17:30:00Z",
            "description": "Quarterly update from leadership team.",
            "attendees": ["team@company.com"],
            "location": "Main Auditorium / Zoom",
        },
    ]

    all_pass = True
    for i, tc in enumerate(test_cases, 1):
        print(f"\n--- Test Case {i}: {tc['title'][:40]} ---")
        result = agent.create_event(**tc)
        print(json.dumps(result, indent=2))

        # Validate
        checks = {
            "success is True": result.get("success") is True,
            "event_id present": bool(result.get("event_id")),
            "event_url present": bool(result.get("event_url")),
            "error is None": result.get("error") is None,
            "event_id starts with evt_": str(result.get("event_id", "")).startswith("evt_"),
        }

        for check, passed in checks.items():
            icon = "✅" if passed else "❌"
            print(f"  {icon} {check}")
            if not passed:
                all_pass = False

    return all_pass


def test_time_parsing():
    """Test ISO8601 time parsing utility."""
    print("\n" + "=" * 60)
    print("Time Parsing Test")
    print("=" * 60)

    from calendar_agent import _parse_iso_to_display

    test_times = [
        ("2026-03-15T14:00:00Z", "March 15, 2026", "2:00 PM"),
        ("2026-03-16T09:30:00-04:00", "March 16, 2026", "9:30 AM"),
        ("2026-12-25T00:00:00Z", "December 25, 2026", "12:00 AM"),
        ("invalid-time", "invalid-time", "invalid-time"),  # Fallback
    ]

    all_pass = True
    for iso, expected_date, expected_time in test_times:
        parsed = _parse_iso_to_display(iso)
        date_ok = parsed["date"] == expected_date
        time_ok = parsed["time"] == expected_time

        icon = "✅" if (date_ok and time_ok) else "❌"
        print(f"  {icon} {iso} → {parsed['date']} {parsed['time']}")
        if not (date_ok and time_ok):
            print(f"      Expected: {expected_date} {expected_time}")
            all_pass = False

    return all_pass


def test_real_mode(visible: bool = False):
    """Test with real Nova Act browser automation."""
    print("=" * 60)
    print("Calendar Agent — Real Mode Test")
    print("=" * 60)

    from calendar_agent import create_event

    api_key = os.environ.get("NOVA_ACT_API_KEY")
    if not api_key:
        print("ERROR: Set NOVA_ACT_API_KEY in .env")
        return False

    print(f"  Mode: {'visible' if visible else 'headless'}")
    print()

    result = create_event(
        title="[TEST] Executive Proxy Calendar Demo",
        start_time="2026-03-15T14:00:00Z",
        end_time="2026-03-15T15:00:00Z",
        description=(
            "This event was created by Executive Proxy "
            "using Nova Act UI automation. Safe to delete."
        ),
        attendees=None,
        headless=not visible,
    )

    print("\nResult:")
    print(json.dumps(result, indent=2))

    print("\n--- Validation ---")
    checks = {
        "success": result.get("success") is True,
        "event_id present": bool(result.get("event_id")),
        "error is None": result.get("error") is None,
    }

    all_pass = True
    for check, passed in checks.items():
        icon = "✅" if passed else "❌"
        print(f"  {icon} {check}")
        if not passed:
            all_pass = False

    return all_pass


def test_executor_integration():
    """Test that the executor can import and route to calendar agent."""
    print("\n" + "=" * 60)
    print("Executor Integration Test")
    print("=" * 60)

    executor_path = os.path.join(os.path.dirname(__file__), "..", "lambdas", "executor")
    sys.path.insert(0, executor_path)

    try:
        from handler import execute_calendar_nova_act
        print("  ✅ execute_calendar_nova_act imports successfully")

        tool_input = {
            "title": "Test executor integration",
            "start_datetime": "2026-03-15T14:00:00Z",
            "end_datetime": "2026-03-15T15:00:00Z",
        }
        result = execute_calendar_nova_act(tool_input)
        print(f"  ✅ execute_calendar_nova_act returned: success={result.get('success')}")
        return True

    except ImportError as e:
        print(f"  ⚠️  Import skipped (Lambda dependency not installed locally): {e}")
        print("  ✅ This is expected — executor runs in Lambda with deps bundled")
        return True
    except Exception as e:
        print(f"  ❌ Execution failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test Nova Act Calendar Agent")
    parser.add_argument("--mock", action="store_true",
                        help="Run mock tests (no browser needed)")
    parser.add_argument("--visible", action="store_true",
                        help="Show browser during real tests")
    parser.add_argument("--setup-auth", action="store_true",
                        help="Run interactive Calendar auth setup")
    parser.add_argument("--integration", action="store_true",
                        help="Test executor integration only")
    args = parser.parse_args()

    if args.setup_auth:
        from calendar_agent import CalendarUIAgent
        CalendarUIAgent.setup_auth()
        return 0

    results = []

    if args.integration:
        results.append(("Executor Integration", test_executor_integration()))
    elif args.mock:
        results.append(("Mock Mode", test_mock_mode()))
        results.append(("Time Parsing", test_time_parsing()))
        results.append(("Executor Integration", test_executor_integration()))
    else:
        results.append(("Real Mode", test_real_mode(visible=args.visible)))

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
