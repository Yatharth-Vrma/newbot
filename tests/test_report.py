"""paper_daily.report: re-running a day that one bot already finished must keep that bot's numbers."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paper_daily  # noqa: E402


def test_same_day_rerun_keeps_etf_row(tmp_path, monkeypatch):
    monkeypatch.setattr(paper_daily, "ROOT", tmp_path)
    pd.DataFrame([{"date": "2026-10-28", "swing": 100000.0, "momentum": 500000, "intraday": 98834.58,
                   "nifty50": 22749.75, "etf_value": 2993.61, "etf_invested": 3000.0, "etf_nifty_sip": 2993.76}]
                 ).to_csv(tmp_path / "history.csv", index=False)
    cfg = {"capital": {"swing": 100000, "momentum": 500000, "intraday": 100000}, "etf_monthly_sip": 3000}
    results = {"swing": {"status": "ok", "date": "2026-10-28", "equity": 100500.0},
               "momentum": {"status": "ok", "date": "2026-10-28", "equity": 500000},
               "intraday": {"status": "already_done", "date": "2026-10-28"},
               "etf": {"status": "already_done", "date": "2026-10-28"},
               "benchmark": {"start_date": "2026-10-27", "start_close": 22749.75,
                             "last_date": "2026-10-28", "last_close": 22698.85}}
    paper_daily.report(cfg, results)
    hist = pd.read_csv(tmp_path / "history.csv")
    assert len(hist) == 1
    row = hist.iloc[0]
    assert row.swing == 100500.0 and row.nifty50 == 22698.85
    assert row.etf_invested == 3000.0 and row.intraday == 98834.58
