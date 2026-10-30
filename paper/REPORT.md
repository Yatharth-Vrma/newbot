# Paper trading report: 2026-10-30

Fake money, real NSE prices. Nifty 50 column = what the same capital would be worth in a Nifty index fund since 2026-10-27.

| Bot | Start capital | Equity now | Return | Nifty 50 same period |
|---|---|---|---|---|
| swing | ₹100,000 | ₹100,113 | +0.11% | +1.33% |
| momentum | ₹500,000 | ₹500,220 | +0.04% | +1.33% |
| intraday | ₹100,000 | ₹99,182 | -0.82% | +1.33% |
| etf (Rs 3,000/month SIP) | invested ₹3,000 | ₹2,921 | -2.62% | same SIP in NIFTYBEES: ₹3,031 (+1.04%) |

## Today

**swing**: ok

**momentum**: ok
- regime: RISK-OFF (index below 200-day average): holding cash

**intraday**: ok
- mode: ACTIVE (learning period (3/40 trades))
- SELL JSWSTEEL x60 1246.73 -> 1248.37 (square_off)
- day P&L ₹-172

**etf**: ok
- pick: MON100 | scores (blended 3/6/12-month return): MON100 +27.4%, GOLDBEES +11.5%, MID150BEES +2.6%, NIFTYBEES -5.0%
- holding: 10 x MON100

Files: `paper/history.csv`, `paper/swing/journal_paper.csv`, `paper/momentum/state.json`, `paper/intraday/journal.csv`.
