#!/usr/bin/env python3
"""Download research datasets from github.com/nathamlan2020-create/nsedata (free):
   data_n500/      Nifty 500 daily OHLCV 2005-2026 + Nifty 500 index   (~34 MB zip)
   intraday_data/  1-minute Kite candles, 33 Nifty 50 stocks 2015-2026 (~380 MB)   [--intraday]"""
import shutil, subprocess, sys, zipfile
from pathlib import Path

REPO = "https://github.com/nathamlan2020-create/nsedata.git"
cache = Path(".cache/nsedata")
paths = ["/daily/nse500_daily_2005-2026.zip", "/daily/indices/*"]
if "--intraday" in sys.argv:
    paths.append("/intraday/stocks_1min/kite_2015-2026/*")
if not (cache / ".git").exists():
    subprocess.run(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", REPO, str(cache)], check=True)
subprocess.run(["git", "-C", str(cache), "sparse-checkout", "set", "--no-cone", *paths], check=True)
out = Path("data_n500"); out.mkdir(exist_ok=True)
zipfile.ZipFile(cache / "daily/nse500_daily_2005-2026.zip").extractall(out)
shutil.copy(cache / "daily/indices/IDX_CRSLDX.csv", out / "_NIFTY500.idx")
print(f"{len(list(out.glob('*.csv')))} stock files in data_n500/")
if "--intraday" in sys.argv:
    d = Path("intraday_data"); d.mkdir(exist_ok=True)
    for f in (cache / "intraday/stocks_1min/kite_2015-2026").glob("*.csv.gz"):
        shutil.copy(f, d / f.name)
    print(f"{len(list(d.glob('*.csv.gz')))} files in intraday_data/")
