#!/usr/bin/env python3
"""Download/refresh free NSE end-of-day candles (split/bonus adjusted) for the symbols in config.yaml.

Source: github.com/BennyThadikaran/eod2_data (community dataset, updated about weekly).
Writes data/<SYMBOL>.csv for use with `data.source: csv`.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO = "https://github.com/BennyThadikaran/eod2_data.git"


def main(config="config.yaml"):
    cfg = yaml.safe_load(open(config))
    cache = Path(".cache/eod2_data")
    files = [f"/daily/{s.lower()}.csv" for s in cfg["symbols"]]
    if not (cache / ".git").exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", REPO, str(cache)], check=True)
    else:
        subprocess.run(["git", "-C", str(cache), "pull", "--depth", "1", "--ff-only", "-q"], check=True)
    subprocess.run(["git", "-C", str(cache), "sparse-checkout", "set", "--no-cone", *files], check=True)
    out = Path(cfg.get("data", {}).get("csv_folder", "data"))
    out.mkdir(exist_ok=True)
    for s in cfg["symbols"]:
        src = cache / "daily" / f"{s.lower()}.csv"
        if src.exists():
            shutil.copy(src, out / f"{s}.csv")
            last = src.read_text().strip().splitlines()[-1].split(",")[0]
            print(f"{s}: up to {last}")
        else:
            print(f"{s}: NOT FOUND in dataset", file=sys.stderr)


if __name__ == "__main__":
    main(*sys.argv[1:])
