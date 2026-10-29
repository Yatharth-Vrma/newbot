#!/usr/bin/env python3
"""Connection test for Angel One SmartAPI (read-only). Prints NO secrets.

Run from GitHub: Actions -> angel-check -> Run workflow.
"""
import sys

import requests

from tradebot.angel_data import AngelData, AngelError


def main():
    try:
        ip = requests.get("https://api.ipify.org", timeout=10).text
    except Exception:
        ip = "unknown"
    print(f"Runner public IP: {ip}")
    a = AngelData()
    try:
        a.login()
        print("1. Login: OK")
    except Exception as e:
        print(f"1. Login: FAILED -> {e}")
        print("   Check the 4 secrets: ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PIN (4-digit login PIN), ANGEL_TOTP_SECRET")
        sys.exit(1)
    ok = True
    try:
        px = a.ltp(["RELIANCE", "HDFCBANK", "NIFTYBEES", "MON100", "GOLDBEES"])
        print("2. Live prices: OK")
        for s, p in px.items():
            print(f"   {s:10s} Rs {p:,.2f}")
    except AngelError as e:
        ok = False
        print(f"2. Live prices: FAILED -> {e}")
    try:
        d = a.candles("RELIANCE", "1d", days=20)
        print(f"3. Daily candles: OK ({len(d)} days, last {d.index[-1].date()} close {d.close.iloc[-1]:,.2f})")
        m = a.candles("RELIANCE", "5m", days=3)
        print(f"4. 5-minute candles: OK ({len(m)} candles, last {m.index[-1]})")
    except Exception as e:
        ok = False
        print(f"3/4. Candles: FAILED -> {e}")
    print("\nAll good: the bot can see live prices." if ok else "\nSome checks failed (see above).")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
