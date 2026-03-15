import os
from pathlib import Path

# Try dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

USER_DATA_DIR = Path(__file__).parent / "browser_profile"
USER_DATA_DIR.mkdir(exist_ok=True)

def setup_auth():
    """One-time authentication setup for Jira and Google Calendar."""
    
    print("🔐 Setting up authentication...")
    print(f"📁 Profile: {USER_DATA_DIR}")
    
    api_key = os.getenv("NOVA_ACT_API_KEY")
    if not api_key:
        print("ERROR: NOVA_ACT_API_KEY environment variable is not set.")
        return

    jira_url = os.getenv("JIRA_BASE_URL", "https://yourorg.atlassian.net")
    
    try:
        from nova_act import NovaAct
    except ImportError:
        print("ERROR: nova-act SDK not installed. Run: pip install nova-act")
        return

    # Use a real NovaAct instance
    with NovaAct(
        starting_page=jira_url,
        nova_act_api_key=api_key,
        headless=False,
        user_data_dir=str(USER_DATA_DIR),
        clone_user_data_dir=False
    ) as _:
        input("\n✅ Log into Jira and Google (if needed), then press ENTER...")
        
        print("\n✅ Authentication saved to browser_profile/")
        print("   Future runs will reuse this session.")

if __name__ == "__main__":
    setup_auth()
