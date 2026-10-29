# Paper trading report: 2026-10-29

Fake money, real NSE prices. Nifty 50 column = what the same capital would be worth in a Nifty index fund since 2026-10-27.

| Bot | Start capital | Equity now | Return | Nifty 50 same period |
|---|---|---|---|---|
| swing | ₹100,000 | ₹100,033 | +0.03% | +0.82% |
| momentum | ₹500,000 | ₹500,147 | +0.03% | +0.82% |
| intraday | ₹100,000 | ₹99,354 | -0.65% | +0.82% |
| etf (Rs 3,000/month SIP) | invested ₹3,000 | ₹2,959 | -1.37% | same SIP in NIFTYBEES: ₹3,020 (+0.67%) |

## Today

**swing**: ok

**momentum**: ok
- regime: RISK-OFF (index below 200-day average): holding cash

**intraday**: ok
- mode: ACTIVE (learning period (2/40 trades))
- BUY JSWSTEEL x55 1243.87 -> 1254.62 (square_off)
- day P&L ₹520

**etf**: ok
- pick: MON100 | scores (blended 3/6/12-month return): MON100 +27.4%, GOLDBEES +11.5%, MID150BEES +2.6%, NIFTYBEES -5.0%
- holding: 10 x MON100

Files: `paper/history.csv`, `paper/swing/journal_paper.csv`, `paper/momentum/state.json`, `paper/intraday/journal.csv`.
