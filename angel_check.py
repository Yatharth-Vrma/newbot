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
    syms = ["RELIANCE", "HDFCBANK", "NIFTYBEES", "MON100", "GOLDBEES"]
    try:
        print("   tokens:", {s: a.token(s) for s in syms})
    except Exception as e:
        print(f"   token lookup FAILED -> {e}")
    try:
        px = a.ltp(syms)
        if px:
            print("2. Live prices: OK")
            for s, p in px.items():
                print(f"   {s:10s} Rs {p:,.2f}")
        else:
            ok = False
            print("2. Live prices: EMPTY. Raw reply from Angel:")
            print("  ", str(a.last_raw)[:1500])
    except Exception as e:
        ok = False
        print(f"2. Live prices: FAILED -> {e} | raw: {str(a.last_raw)[:1500]}")
    for label, interval, days in (("3. Daily candles", "1d", 20), ("4. 5-minute candles", "5m", 3)):
        try:
            d = a.candles("RELIANCE", interval, days=days)
            if len(d):
                print(f"{label}: OK ({len(d)} candles, last {d.index[-1]} close {d.close.iloc[-1]:,.2f})")
            else:
                ok = False
                print(f"{label}: EMPTY. Raw reply from Angel:")
                print("  ", str(a.last_raw)[:1500])
        except Exception as e:
            ok = False
            print(f"{label}: FAILED -> {e} | raw: {str(a.last_raw)[:1500]}")
    print("\nAll good: the bot can see live prices." if ok else "\nSome checks failed (see above).")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
