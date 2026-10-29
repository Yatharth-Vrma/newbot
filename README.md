# tradebot — Zerodha daily trading bot

A daily-candle trading bot for NSE stocks. It includes **10 classic strategies plus an ensemble**, a backtester that applies realistic Zerodha charges, a **paper-trading** mode, and a **live** mode that trades real money through Kite Connect.

> **Read this first.** No strategy here is guaranteed to make money. Most retail algos lose money once you add charges, slippage and tax. Run the backtest, then paper-trade for at least 1–3 months. Only go live with money you can afford to lose. This is not investment advice.

## The 10 strategies

| # | name | type | rule (long-only, daily) |
|---|------|------|---------------------|
| 1 | `sma_cross` | trend | Hold while the 50-day SMA is above the 200-day SMA (golden cross) |
| 2 | `ema_cross` | trend | Hold while EMA 9 > EMA 21 |
| 3 | `macd` | trend | Hold while the MACD(12,26) line is above its 9-day signal line |
| 4 | `rsi2` | mean reversion | Connors RSI(2): buy when RSI2 < 10 and price is above the 200-day SMA; exit when price closes above the 5-day SMA |
| 5 | `bollinger` | mean reversion | Buy on a close below the lower band (20, 2σ); exit at the middle band |
| 6 | `donchian` | breakout | Turtle rule: buy on a 55-day-high breakout; exit on a 20-day low |
| 7 | `supertrend` | trend | Hold while Supertrend(10, 3) is green |
| 8 | `momentum` | momentum | AQR-style 12-1 month time-series momentum is positive |
| 9 | `adx_dmi` | trend strength | Buy when ADX > 25 and +DI > −DI; exit when +DI < −DI |
| 10 | `ichimoku` | trend | Close above the cloud and Tenkan > Kijun |
| + | `ensemble` | vote | Hold when at least `min_votes` (default 6) of the 10 strategies agree |

There is no official "top 10" list. These are the most widely taught and traded rule-based systems. All of them are long-only, because shares bought for delivery (CNC) can't be held short overnight.

## How it trades

* The bot runs **once a day after market close, at about 16:30 IST**. It computes signals on the day's closing candles.
* It places **AMO limit orders** (CNC delivery) that fill at the next morning's open. The limit is the close ±1%, so it won't chase a big gap.
* The backtester uses the same execution model: signal on today's close, fill at tomorrow's open, whole shares only. It charges STT, stamp duty, exchange and SEBI fees, GST, DP charges and slippage.
* The bot only manages **shares it bought**. Shares you already held in a symbol are recorded as your baseline and are never sold.

**Risk controls** (in `config.yaml`):

* a cap on how much capital goes into one position
* kill switches: if equity falls 15% from its peak, or drops 5% in one day, the bot sells everything and writes `state/HALT`
* an order cap per run
* orders are throttled well below SEBI's 10 orders/second limit

## 1. Install

```bash
cd tradebot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q          # 15 tests should pass
```

## 2. Backtest all strategies

```bash
python backtest.py                       # symbols and dates from config.yaml, data from Yahoo (free)
python backtest.py --only supertrend donchian ensemble --start 2015-01-01
python backtest.py --demo                # synthetic prices, offline plumbing check only
```

The backtest prints a ranked table and writes `results/backtest_summary.csv`, `results/equity_curves.csv` and `results/equity_curves.png`.

How to read the table:

* Compare each strategy with `buy_and_hold`.
* Pick your strategy using the in-sample columns.
* Trust it only if `oos_sharpe` and `oos_cagr` (the last 30% of the period, which you didn't tune on) still hold up.
* The Sharpe ratio is measured against a 6.5% risk-free rate. A negative Sharpe means you'd have done better in an FD.

## Daily paper trading on live data (free, automatic, on GitHub)

`paper_daily.py` runs three paper bots on real NSE prices from Yahoo Finance every trading day at about 17:15 IST. It uses fake money only, and a Nifty 50 buy-and-hold is tracked alongside as the benchmark:

| Bot | What it does | Capital |
|---|---|---|
| `momentum` | Every month, buys the top 20 of the Nifty 500 ranked by 6- and 12-month momentum. Holds cash when the Nifty 500 is below its 200-day average | ₹5 lakh |
| `swing` | The daily trend bot (`config.yaml` strategy) on 10 large caps | ₹1 lakh |
| `intraday` | The **live** ORB bot code replayed on that day's real 1-minute candles | ₹1 lakh |

Results go to `paper/REPORT.md` (opens nicely on GitHub, including on a phone), `paper/history.csv` and the journals for each bot.

### Setup (about 10 minutes, ₹0)
1. Create a GitHub account, then a new repository, for example `tradebot-paper`. Make it **public**: Actions minutes are unlimited for public repos, and Claude can read it for your daily review. Only fake-money results go in it.
2. Upload the contents of this folder. Either drag and drop on github.com ("Add file → Upload files", including the `.github` folder), or run:
   ```bash
   git init && git add . && git commit -m "tradebot" && git branch -M main
   git remote add origin https://github.com/<you>/tradebot-paper.git && git push -u origin main
   ```
3. Open **Settings → Actions → General → Workflow permissions** and select **Read and write**.
4. Open **Actions → paper-trading → Run workflow** to run it once now. After that it runs by itself every weekday.

GitHub turns off scheduled workflows in public repos after 60 days without activity. The bot's own daily commits usually keep it active. If it ever stops, click "Enable workflow" in the Actions tab.

### Daily review
Ask Claude for a "daily review" and give it your repo URL. It reads `paper/` and reports:
* what each bot did
* how each bot compares with Nifty
* whether live behaviour matches the backtest (slippage, win rate, drawdown)
* one or two concrete improvements, with a test to prove each one before it goes in

### Momentum backtest (2006–2026, after Zerodha charges and Indian capital-gains tax)

```
python get_research_data.py && python backtest_momentum.py
```

| | CAGR | Sharpe | Max drawdown |
|---|---|---|---|
| Momentum top 20 + regime filter | 23.0% | 0.76 | −47.5% |
| Momentum top 30 + regime filter | 25.5% | 0.86 | −42.5% |
| Equal weight of the same 500 (no costs, no tax) | 22.3% | 0.80 | −66.4% |
| Nifty 500 index (price only) | 11.1% | 0.31 | −64.3% |

The data only contains stocks that are in the Nifty 500 today, so all the numbers above are inflated. The fair real-world reference is NSE's own **Nifty200 Momentum 30 TRI**: **18.8% a year against 13.9% for the Nifty 200 TRI** (Apr 2005–Jun 2026, HDFC MF factsheet).

For hands-off investing, an index fund on that index captures the same idea, and the fund's rebalancing doesn't trigger capital-gains tax for you.

## Free data with no API key

```bash
python update_data.py        # pulls split/bonus-adjusted NSE EOD candles (eod2_data on GitHub, updated ~weekly) into data/
```

`config.yaml` uses `data.source: csv`, which reads these files.

## Paper trade with catch-up (works anywhere, including inside Claude)

```bash
python run_bot.py --catch-up --since 2026-01-01   # start a paper account on a past date and replay every day
python update_data.py && python run_bot.py --catch-up   # later: replay only the new days
```

Each replayed day only sees candles up to that day, so the result is identical to having run the bot every evening.

## 3. Paper trade daily (fake money, real prices)

Set `strategy:` in `config.yaml`, keep `mode: paper`, then run:

```bash
python run_bot.py            # run once per trading day after 16:30 IST
```

Each run updates `state/paper.json` (cash, positions, fills), `state/journal_paper.csv` (daily equity) and `state/bot.log`.

To schedule it with cron (Mac/Linux), run `crontab -e` and add:

```
30 16 * * 1-5 cd /path/to/tradebot && .venv/bin/python run_bot.py >> state/cron.log 2>&1
```

## 4. Go live with Zerodha (real money)

SEBI's retail-algo framework applies from 1 April 2026. It requires:

* a registered API app
* a **static IP that is whitelisted**
* a **2FA login once per trading day**

Setup steps:

1. **Create a Kite Connect app** at developers.kite.trade. The *Personal* API is free for placing orders but includes no market data. Keep `data.source: yfinance`, or use `kite` if you pay for the Connect plan (historical data is included at ₹2000/month).
2. **Get a static IP.** The easiest way is a small Linux VPS in India with a fixed IP, such as AWS Mumbai with an Elastic IP or DigitalOcean Bangalore. Register that IP in your Kite app. Orders from any other IP are rejected.
3. **Deploy this folder to the VPS** and set your keys as environment variables:
   ```bash
   export KITE_API_KEY=... KITE_API_SECRET=...
   ```
4. **Log in every trading day**, any time before the 16:30 run. Tokens expire around 6 AM:
   ```bash
   python kite_login.py         # opens the login page; paste the redirect URL back in
   ```
5. **Run live.** Copy the config, then set `mode: live` and a small `capital` in the copy:
   ```bash
   cp config.yaml config.live.yaml
   TRADEBOT_LIVE=YES python run_bot.py --config config.live.yaml
   ```
   Live and paper keep separate state files (`state/live.json` and `state/paper.json`).
6. **To stop the bot:** `touch state/HALT`. To resume: `rm state/HALT`.

Start small (₹10–25k) for the first month and compare live fills with the paper run.

## Intraday bot (MIS) — ORB "Stocks in Play"

This is the most widely cited intraday strategy online: Zarattini, Barbon & Aziz (2023), *A Profitable Day Trading Strategy for the U.S. Equity Market*. The bot follows these rules each trading day:

1. **09:20 — pick the stocks.** Look at the first 5-minute candle of each of 33 Nifty 50 stocks. Keep the 3 whose volume is highest relative to their usual first-5-minute volume (relative volume above 1).
2. **Place the entry.** If the candle is green, buy above its high. If it's red, sell short below its low. Both use stop-limit orders.
3. **Set the stop-loss.** The stop is 0.25 × the 14-day ATR from the entry fill, so each trade risks 0.5% of capital.
4. **Day loss limit.** If the day's total loss reaches 2%, the bot squares off everything and stops for the day.
5. **15:00 — cancel unfilled entries.**
6. **15:15 — square off all positions.**

### Results on real 1-minute Zerodha data (33 Nifty 50 stocks, 2015–2026)

| What was tested | Result |
|---|---|
| Every ORB variant, before charges | a small positive edge (+0.03 to +0.17 R per trade) |
| Every ORB variant, after Zerodha MIS charges and 3 bps slippage | **a loss**; the 2023–26 out-of-sample period was negative for every variant |
| The actual live-bot code, replayed day by day over 2023–Oct 2026 (₹1 lakh) | **−₹86,583** at 3 bps slippage, **−₹60,837** at 1 bps |
| Backtest engine, best variant, assuming 0 slippage | +52% a year (unrealistic); +8% a year from 2023 at 1 bps |

Charges of about ₹90 per round trip (STT, brokerage, exchange fees, GST) are about 0.18 R per trade on a ₹500 risk, which is larger than the strategy's edge. This matches SEBI's finding that about 7 in 10 individual intraday cash traders lose money.

**Do not run this with real money.** Forward-test it in paper mode first, and judge it by the `entry_slip_bps` column in the journal.

### Commands

```bash
python get_research_data.py --intraday                       # free 1-min data (~380 MB)
python backtest_intraday.py                                 # 12 ORB variants with Zerodha MIS charges
python replay_intraday.py --from 2026-09-01 --to 2026-10-19 # run the LIVE bot code on past days
python run_intraday.py --paper                              # live prices, simulated orders (start ~09:00 IST)
TRADEBOT_LIVE=YES python run_intraday.py --live --capital 25000   # real money
```

To run it live you need:

* the Kite Connect plan at ₹500/month, which includes the WebSocket and historical data the bot needs
* your static IP whitelisted in the Kite app
* the daily `kite_login.py` login
* the bot started at about 09:00 IST, for example from cron with `0 9 * * 1-5`, on a VPS in Mumbai

The bot writes `state/intraday/<mode>/journal.csv` and `bot.log`. To stop it: `touch state/intraday/live/HALT`.

## Tax (India) — check with a CA

Gains on shares held under 12 months are STCG at 20%. Frequent trading may be treated as business income. STT, stamp duty and other charges are already included in the backtest.

## Other open-source projects worth knowing

* **OpenAlgo** (marketcalls/openalgo): a self-hosted platform with one API for 20+ Indian brokers. Good if you want TradingView/Amibroker alerts, or another broker such as Dhan or Fyers.
* **Freqtrade**: the most mature open-source crypto bot. Not for NSE.
* **Backtrader / vectorbt**: Python backtesting libraries for heavier research.
* **QuantConnect LEAN**: an institutional-grade engine, mostly aimed at US markets.

## Files

```
config.yaml          all settings
backtest.py          rank all strategies
run_bot.py           one daily bot run (paper or live)
kite_login.py        daily Zerodha 2FA login -> state/access_token.txt
tradebot/strategies.py   the 10 strategies + ensemble   <- add your own here
tradebot/indicators.py   SMA/EMA/RSI/ATR/MACD/Bollinger/Supertrend/ADX/Ichimoku
tradebot/backtest.py     execution + metrics
tradebot/broker.py       PaperBroker, ZerodhaBroker
tradebot/runner.py       daily logic, risk checks, kill switch
paper_daily.py           daily paper run of all bots on live Yahoo data (GitHub Action)
review.py                numbers for the daily review
config_paper.yaml        paper capital per bot
.github/workflows/paper.yml   the free daily schedule
tradebot/momentum.py     monthly Nifty 500 momentum rotation (+ paper_momentum.py)
tradebot/intraday/       ORB engine, live bot, Kite/paper/replay adapters
backtest_momentum.py / backtest_intraday.py / replay_intraday.py   research
tradebot/etf_rotation.py monthly ETF dual-momentum SIP
tradebot/live_data.py    free Yahoo data used by all paper bots
tradebot/angel_data.py   read-only Angel One SmartAPI data client (no order functions)
angel_check.py           Angel login/data check (.github/workflows/angel-check.yml, manual)
tests/                   look-ahead, cost, paper end-to-end, kill-switch, intraday and data-parsing tests
```
