"""Angel client offline test with a fake HTTP session; also proves there is no order-placing code."""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tradebot import angel_data  # noqa: E402


class FakeResp:
    def __init__(self, data):
        self._d = data

    def json(self):
        return self._d


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, timeout=None):
        return FakeResp([{"exch_seg": "NSE", "symbol": "RELIANCE-EQ", "token": "2885", "name": "RELIANCE"},
                         {"exch_seg": "NSE", "symbol": "NIFTYBEES-EQ", "token": "10576", "name": "NIFTYBEES"}])

    def post(self, url, headers=None, data=None, timeout=None):
        self.calls.append((url, headers))
        if "login" in url:
            return FakeResp({"status": True, "data": {"jwtToken": "JWT"}})
        if "quote" in url:
            return FakeResp({"status": True, "data": {"fetched": [{"symbolToken": "2885", "ltp": 1205.5},
                                                                  {"symbolToken": "10576", "ltp": 270.1}]}})
        return FakeResp({"status": True, "data": [["2026-10-28T00:00:00+05:30", 1, 2, 0.5, 1.5, 100]]})


def test_read_only_client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    a = angel_data.AngelData("k", "c", "1234", "JBSWY3DPEHPK3PXP", session=FakeSession())
    a.login()
    assert a.ltp(["RELIANCE", "NIFTYBEES"]) == {"RELIANCE": 1205.5, "NIFTYBEES": 270.1}
    df = a.candles("RELIANCE", "1d", 5)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"] and len(df) == 1
    assert a.http.calls[-1][1]["Authorization"] == "Bearer JWT"
    src = inspect.getsource(angel_data).lower()
    assert "placeorder" not in src and "order/v1" not in src  # no order endpoints at all
