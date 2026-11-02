# Paper trading report: 2026-11-02

Fake money, real NSE prices. Nifty 50 column = what the same capital would be worth in a Nifty index fund since 2026-10-27.

| Bot | Start capital | Equity now | Return | Nifty 50 same period |
|---|---|---|---|---|
| swing | ₹100,000 | ₹100,113 | +0.11% | +1.33% |
| momentum | ₹500,000 | ₹500,220 | +0.04% | +1.33% |
| intraday | ₹100,000 | ₹101,741 | +1.74% | +1.33% |
| etf (Rs 3,000/month SIP) | invested ₹6,000 | ₹5,889 | -1.85% | same SIP in NIFTYBEES: ₹6,025 (+0.41%) |

## Today

**swing**: already_done

**momentum**: already_done

**intraday**: ok
- mode: ACTIVE (learning period (4/40 trades))
- BUY JSWSTEEL x61 1261.43 -> 1304.61 (square_off)
- day P&L ₹2,559

**etf**: ok
- 👉 **YOUR REAL-MONEY ACTION THIS MONTH** (if you mirror it in Kite, delivery/CNC):
  - SELL 10 x MON100 (about ₹2,847)
  - BUY 5 x LIQUIDBEES (about ₹5,005)
- pick: LIQUIDBEES | scores (blended 3/6/12-month return): GOLDBEES +2.1%, MON100 +1.5%, MID150BEES -5.5%, NIFTYBEES -6.2%
- holding: 5 x LIQUIDBEES

Files: `paper/history.csv`, `paper/swing/journal_paper.csv`, `paper/momentum/state.json`, `paper/intraday/journal.csv`.
