#!/usr/bin/env python3
"""
allie_wc_token.py
Fetches and caches a fresh WebClerk Bearer token for Allie or Athena.

Reads credentials from /Volumes/Allie/config/wc_credentials.json (not profile.json —
credentials are kept separate from the sovereignty declaration).

Usage:
  # Print token to stdout (for use in scripts)
  python3 allie_wc_token.py
  python3 allie_wc_token.py --agent athena

  # As env var:
  export WC_TOKEN=$(python3 /Volumes/Allie/scripts/allie_wc_token.py)

  # In Python:
  from allie_wc_token import get_token
  token = get_token("allie")

Token is cached in /tmp/allie_wc_token_{agent}.json and reused until 5 min
before expiry. No credentials are printed to stdout — only the token itself.
"""

import sys
import json
import time
import pathlib
import argparse
import urllib.request
import urllib.error

ALLIE = pathlib.Path("/Volumes/Allie")
CREDS_PATH = ALLIE / "config" / "wc_credentials.json"
WC_BASE = "http://localhost:8000"
TOKEN_URL = "/wcapi/token/"
REFRESH_URL = "/wcapi/token_refresh/"
EXPIRY_BUFFER_S = 300   # refresh 5 min before expiry


def load_credentials(agent: str = "allie") -> dict:
    """Load credentials from wc_credentials.json."""
    if not CREDS_PATH.exists():
        print(f"ERROR: {CREDS_PATH} not found. Run setup to create it.", file=sys.stderr)
        sys.exit(1)
    creds = json.loads(CREDS_PATH.read_text())
    if agent not in creds:
        print(f"ERROR: No credentials for agent '{agent}' in {CREDS_PATH}", file=sys.stderr)
        sys.exit(1)
    return creds[agent]


def cache_path(agent: str) -> pathlib.Path:
    return pathlib.Path(f"/tmp/allie_wc_token_{agent}.json")


def load_cached(agent: str) -> str | None:
    """Return cached token if still valid, else None."""
    cp = cache_path(agent)
    if not cp.exists():
        return None
    try:
        data = json.loads(cp.read_text())
        # expires_at is Unix timestamp
        if time.time() < data.get("expires_at", 0) - EXPIRY_BUFFER_S:
            return data["access"]
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def save_cached(agent: str, access: str, expires_at: float):
    cache_path(agent).write_text(json.dumps({
        "access": access,
        "expires_at": expires_at,
        "agent": agent,
    }))


def fetch_token(email: str, password: str) -> dict:
    """POST to /wcapi/token/ and return the data dict."""
    payload = json.dumps({"email": email, "password": password}).encode()
    req = urllib.request.Request(
        f"{WC_BASE}{TOKEN_URL}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        result = json.loads(e.read())

    if result.get("status") != "success":
        msg = result.get("message") or result.get("error", {}).get("details", "unknown error")
        print(f"ERROR: WebClerk auth failed: {msg}", file=sys.stderr)
        sys.exit(1)

    return result["data"]


def get_token(agent: str = "allie") -> str:
    """Return a valid Bearer token for the given agent. Uses cache when possible."""
    # Try cache first
    cached = load_cached(agent)
    if cached:
        return cached

    # Fetch fresh token
    creds = load_credentials(agent)
    data = fetch_token(creds["email"], creds["password"])

    access = data["access"]

    # Decode expiry from JWT payload (middle segment, base64)
    import base64
    parts = access.split(".")
    if len(parts) == 3:
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.b64decode(padded))
        expires_at = float(payload.get("exp", time.time() + 1800))
    else:
        expires_at = time.time() + 1800

    save_cached(agent, access, expires_at)
    return access


def main():
    parser = argparse.ArgumentParser(description="Get WebClerk Bearer token for an agent")
    parser.add_argument("--agent", default="allie", choices=["allie", "athena"],
                        help="Which agent to get a token for (default: allie)")
    parser.add_argument("--setup", action="store_true",
                        help="Create wc_credentials.json interactively")
    args = parser.parse_args()

    if args.setup:
        run_setup()
        return

    print(get_token(args.agent))


def run_setup():
    """Interactive setup — writes wc_credentials.json."""
    print(f"\nWebClerk credential setup")
    print(f"  Writing to: {CREDS_PATH}\n")

    creds = {}
    if CREDS_PATH.exists():
        creds = json.loads(CREDS_PATH.read_text())

    for agent, defaults in [
        ("allie",  {"email": "allie@jpods.com",  "wc_id": 48,  "connection_id": 22}),
        ("athena", {"email": "athena@jpods.com", "wc_id": 49,  "connection_id": 23}),
    ]:
        print(f"  {agent.capitalize()} ({defaults['email']}):")
        password = input(f"    Password: ").strip()
        if not password:
            print(f"    Skipped.")
            continue
        creds[agent] = {
            "email": defaults["email"],
            "password": password,
            "user_id": defaults["wc_id"],
            "connection_id": defaults["connection_id"],
            "endpoint": WC_BASE,
        }
        # Test it
        try:
            data = fetch_token(defaults["email"], password)
            print(f"    OK — token obtained, user_id={defaults['wc_id']}")
        except SystemExit:
            print(f"    FAILED — credentials not saved for {agent}")
            creds.pop(agent, None)

    if creds:
        CREDS_PATH.write_text(json.dumps(creds, indent=2))
        # Restrict permissions — credentials file
        CREDS_PATH.chmod(0o600)
        print(f"\n  Saved to {CREDS_PATH} (mode 600)")
    else:
        print("\n  Nothing saved.")


if __name__ == "__main__":
    main()
