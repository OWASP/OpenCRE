"""Standalone Google device-flow check. No OpenCRE involved.

First run  : full device flow, saves the refresh token to .mcp_tokens.json
Later runs : refreshes silently, no browser, no re-approval

This mirrors what application/mcp/auth.py will do in v2, with a file
standing in for the OS keyring.
"""

import base64
import json
import os
import pathlib
import sys
import time

import requests

try:
    from dotenv import load_dotenv

    load_dotenv()  # pull GOOGLE_MCP_* out of .env at the repo root
except ImportError:
    pass

DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
SCOPES = "openid email profile"  # NEVER add a fourth - see docs/api/mcp.md
TOKEN_FILE = pathlib.Path(__file__).parent / ".mcp_tokens.json"

CLIENT_ID = os.environ.get("GOOGLE_MCP_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GOOGLE_MCP_CLIENT_SECRET")
if not CLIENT_ID or not CLIENT_SECRET:
    sys.exit(
        "GOOGLE_MCP_CLIENT_ID / GOOGLE_MCP_CLIENT_SECRET not found.\n"
        "Put them in .env at the repo root, or export them in this shell."
    )


def claims_of(id_token: str) -> dict:
    """Decode WITHOUT verifying - display only. Real code verifies the signature."""
    payload = id_token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def refresh(refresh_token: str) -> dict | None:
    """Trade a refresh token for fresh tokens. None if it is no longer valid."""
    r = requests.post(
        TOKEN_URL,
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if r.status_code == 200:
        return r.json()
    print(f"  refresh rejected [{r.status_code}] - falling back to device flow")
    return None


def device_flow() -> dict:
    """Full approval flow: print a code, wait for the human, return tokens."""
    r = requests.post(
        DEVICE_CODE_URL,
        data={"client_id": CLIENT_ID, "scope": SCOPES},
        timeout=30,
    )
    if r.status_code != 200:
        # Google's body says WHY (wrong client type, consent screen incomplete...).
        sys.exit(f"device/code failed [{r.status_code}]: {r.text}")
    d = r.json()

    # Google spells it verification_url; RFC 8628 says verification_uri.
    url = d.get("verification_url") or d["verification_uri"]
    print(f"\n  Open: {url}\n  Code: {d['user_code']}\n")

    interval = d.get("interval", 5)
    deadline = time.time() + d["expires_in"]
    while time.time() < deadline:
        time.sleep(interval)
        t = requests.post(
            TOKEN_URL,
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "device_code": d["device_code"],
                "grant_type": DEVICE_GRANT,
            },
            timeout=30,
        )
        body = t.json()
        if t.status_code == 200:
            return body
        err = body.get("error")
        if err == "authorization_pending":
            print("  waiting...")
            continue
        if err == "slow_down":
            interval += 5
            continue
        sys.exit(f"failed: {body}")
    sys.exit("timed out - the code expired before it was approved")


saved = json.loads(TOKEN_FILE.read_text()) if TOKEN_FILE.exists() else {}
tokens = refresh(saved["refresh_token"]) if saved.get("refresh_token") else None
if tokens is None:
    tokens = device_flow()

# A refresh response omits refresh_token - keep the one we already hold.
keep = tokens.get("refresh_token") or saved.get("refresh_token")
TOKEN_FILE.write_text(json.dumps({"refresh_token": keep, "saved_at": time.time()}))

claims = claims_of(tokens["id_token"])
print("refresh token held :", bool(keep))
print("sub                :", claims["sub"])
print("aud                :", claims["aud"])  # must be your MCP client id
print("email              :", claims.get("email"))
print("id_token expires   :", int(claims["exp"] - time.time()), "seconds")
print(f"\nsaved to {TOKEN_FILE.name} - re-run to confirm it refreshes with no browser")
