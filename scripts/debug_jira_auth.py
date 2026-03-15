import requests
from requests.auth import HTTPBasicAuth
import json
import os

email = "shashen624@gmail.com"
token = "ATATT3xFfGF0NNBo81TatpxKfLTEnicdNsUNcet8Wh2Hra_eZ_eWkJ3Z6ncDvxHC6Rs1BIG5DRQBrlFhP_oy16KD4f7Cgz7VLclBPaPyBSm4lX_gKeTFlhIknzM9005w_wYRKY3ayDUAfp9HVd4UJnFXEVrtMK6ocyTm8IzCxKRrPKswzzakaCI=5D2FD500"
url = "https://hrudhvik.atlassian.net/rest/api/3/myself"

print(f"Testing Jira Auth for {email}...")
print(f"Token length: {len(token)}")

auth = HTTPBasicAuth(email, token)

headers = {
   "Accept": "application/json"
}

try:
    response = requests.request(
       "GET",
       url,
       headers=headers,
       auth=auth
    )

    print(f"Status Code: {response.status_code}")
    print(f"Response Body: {response.text}")

    if response.status_code == 200:
        print("\nSUCCESS: Authentication verified!")
    else:
        print("\nFAILURE: Authentication failed.")
        if "Client must be authenticated" in response.text:
            print("Server returned 401 - Unauthorized. The email or token is likely incorrect.")

except Exception as e:
    print(f"Error during request: {e}")
