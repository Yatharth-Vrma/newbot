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
    try:
        o = a.today_ohlc(syms)
        if o:
            print("3. Today's live candle: OK")
            for s, c in o.items():
                print(f"   {s:10s} open {c['open']:,.2f}  high {c['high']:,.2f}  low {c['low']:,.2f}  now {c['last']:,.2f}  (prev close {c['prev_close']:,.2f})")
        else:
            ok = False
            print("3. Today's live candle: EMPTY. Raw:", str(a.last_raw)[:800])
    except Exception as e:
        ok = False
        print(f"3. Today's live candle: FAILED -> {e}")
    try:  # optional: Angel's candle-history service (Yahoo covers history if this is unavailable)
        d = a.candles("RELIANCE", "1d", days=20)
        print(f"4. (optional) Candle history: OK ({len(d)} daily candles)" if len(d) else
              f"4. (optional) Candle history: empty. Raw: {str(a.last_raw)[:500]}")
    except Exception as e:
        print(f"4. (optional) Candle history: not available -> {str(e)[:500]}")
    print("\nAll good: the bot can see live prices." if ok else "\nSome checks failed (see above).")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
