"""READ-ONLY Angel One SmartAPI client: live prices and candles. It has NO order functions.

Credentials come from environment variables (GitHub Secrets):
  ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PIN, ANGEL_TOTP_SECRET
Endpoints used (SmartAPI REST):
  login        POST /rest/auth/angelbroking/user/v1/loginByPassword
  quote        POST /rest/secure/angelbroking/market/v1/quote/
  candles      POST /rest/secure/angelbroking/historical/v1/getCandleData
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pandas as pd

HOSTS = ["https://apiconnect.angelone.in", "https://apiconnect.angelbroking.com"]
SCRIP_MASTER = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
INTERVALS = {"1m": "ONE_MINUTE", "3m": "THREE_MINUTE", "5m": "FIVE_MINUTE", "15m": "FIFTEEN_MINUTE",
             "30m": "THIRTY_MINUTE", "1h": "ONE_HOUR", "1d": "ONE_DAY"}


class AngelError(RuntimeError):
    pass


class AngelData:
    def __init__(self, api_key=None, client_id=None, pin=None, totp_secret=None, session=None):
        import requests

        self.api_key = api_key or os.environ["ANGEL_API_KEY"]
        self.client_id = client_id or os.environ["ANGEL_CLIENT_ID"]
        self.pin = pin or os.environ["ANGEL_PIN"]
        self.totp_secret = (totp_secret or os.environ["ANGEL_TOTP_SECRET"]).replace(" ", "")
        self.http = session or requests.Session()
        self.host = HOSTS[0]
        self.jwt = None
        self._tokens: dict[str, str] = {}
        self._last_call = 0.0

    # ---------------------------------------------------------------- plumbing
    def _headers(self, auth=True):
        h = {"Content-Type": "application/json", "Accept": "application/json", "X-UserType": "USER",
             "X-SourceID": "WEB", "X-ClientLocalIP": "127.0.0.1", "X-ClientPublicIP": "127.0.0.1",
             "X-MACAddress": "00:00:00:00:00:00", "X-PrivateKey": self.api_key}
        if auth and self.jwt:
            h["Authorization"] = f"Bearer {self.jwt}"
        return h

    def _post(self, path, body, auth=True):
        wait = 0.35 - (time.time() - self._last_call)    # stay under ~3 requests/second
        if wait > 0:
            time.sleep(wait)
        last_err = None
        for host in [self.host] + [h for h in HOSTS if h != self.host]:
            try:
                r = self.http.post(host + path, headers=self._headers(auth), data=json.dumps(body), timeout=20)
                self._last_call = time.time()
                data = r.json()
                self.host = host
                if not data.get("status", False) and data.get("data") is None:
                    raise AngelError(f"{path}: {data.get('message')} ({data.get('errorcode')})")
                return data.get("data")
            except AngelError:
                raise
            except Exception as e:  # network / DNS / non-JSON: try the other host
                last_err = e
        raise AngelError(f"{path}: {last_err}")

    # ---------------------------------------------------------------- public
    def login(self):
        import pyotp

        data = self._post("/rest/auth/angelbroking/user/v1/loginByPassword",
                          {"clientcode": self.client_id, "password": self.pin,
                           "totp": pyotp.TOTP(self.totp_secret).now()}, auth=False)
        self.jwt = data["jwtToken"]
        return True

    def token(self, symbol: str, exchange="NSE") -> str:
        """NSE trading symbol (RELIANCE, NIFTYBEES, M&M) -> Angel symbol token, via the public scrip master."""
        if not self._tokens:
            cache = Path(".cache/angel_scrips.json")
            if cache.exists() and time.time() - cache.stat().st_mtime < 86400:
                rows = json.loads(cache.read_text())
            else:
                rows = self.http.get(SCRIP_MASTER, timeout=60).json()
                rows = [r for r in rows if r.get("exch_seg") == "NSE"]
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(rows))
            for r in rows:
                sym = r["symbol"]
                if sym.endswith("-EQ"):
                    self._tokens[sym[:-3]] = r["token"]
                elif sym.endswith("-BE"):
                    self._tokens.setdefault(sym[:-3], r["token"])
                else:
                    self._tokens.setdefault(r.get("name") or sym, r["token"])
        if symbol not in self._tokens:
            raise AngelError(f"unknown symbol {symbol}")
        return self._tokens[symbol]

    def ltp(self, symbols: list[str]) -> dict[str, float]:
        """Last traded price for up to ~50 NSE symbols in one call."""
        tok = {self.token(s): s for s in symbols}
        out = {}
        items = list(tok)
        for i in range(0, len(items), 50):
            data = self._post("/rest/secure/angelbroking/market/v1/quote/",
                              {"mode": "LTP", "exchangeTokens": {"NSE": items[i:i + 50]}})
            for q in (data or {}).get("fetched", []):
                out[tok[str(q["symbolToken"])]] = float(q["ltp"])
        return out

    def candles(self, symbol: str, interval="1d", days=30) -> pd.DataFrame:
        """OHLCV candles up to now (today's candle is still forming during market hours)."""
        now = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None)
        start = now - pd.Timedelta(days=days)
        data = self._post("/rest/secure/angelbroking/historical/v1/getCandleData",
                          {"exchange": "NSE", "symboltoken": self.token(symbol), "interval": INTERVALS[interval],
                           "fromdate": start.strftime("%Y-%m-%d 09:15"), "todate": now.strftime("%Y-%m-%d %H:%M")})
        df = pd.DataFrame(data or [], columns=["date", "open", "high", "low", "close", "volume"])
        if df.empty:
            return df
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        return df.set_index("date").astype(float)
