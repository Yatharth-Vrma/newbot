#!/usr/bin/env python3
"""Daily Zerodha login (SEBI requires 2FA once per trading day; tokens expire ~6 AM next day).

  export KITE_API_KEY=xxxx KITE_API_SECRET=yyyy
  python kite_login.py

1. Opens the Kite login URL -> log in with your password + 2FA
2. You're redirected to your app's redirect URL with ?request_token=... in the address bar
3. Paste that full URL (or just the token) here -> access token saved to state/access_token.txt
"""
import os
import sys
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from kiteconnect import KiteConnect


def main():
    key, secret = os.environ.get("KITE_API_KEY"), os.environ.get("KITE_API_SECRET")
    if not key or not secret:
        sys.exit("Set KITE_API_KEY and KITE_API_SECRET environment variables first.")
    kite = KiteConnect(api_key=key)
    url = kite.login_url()
    print("Login here:\n", url)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    raw = input("\nPaste the redirect URL (or request_token): ").strip()
    token = parse_qs(urlparse(raw).query).get("request_token", [raw])[0]
    sess = kite.generate_session(token, api_secret=secret)
    out = Path(os.environ.get("TRADEBOT_STATE_DIR", "state")) / "access_token.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sess["access_token"])
    os.chmod(out, 0o600)
    kite.set_access_token(sess["access_token"])
    print(f"Logged in as {kite.profile()['user_name']}. Token saved to {out}.")


if __name__ == "__main__":
    main()
