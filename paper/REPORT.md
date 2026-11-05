# Paper trading report: 2026-11-05

Fake money, real NSE prices. Nifty 50 column = what the same capital would be worth in a Nifty index fund since 2026-10-27.

| Bot | Start capital | Equity now | Return | Nifty 50 same period |
|---|---|---|---|---|
| swing | ₹100,000 | ₹100,296 | +0.30% | +5.32% |
| momentum | ₹500,000 | ₹500,587 | +0.12% | +5.32% |
| intraday | ₹100,000 | ₹102,414 | +2.41% | +5.32% |
| etf (Rs 3,000/month SIP) | invested ₹6,000 | ₹5,889 | -1.85% | same SIP in NIFTYBEES: ₹6,243 (+4.05%) |

## Today

**swing**: ok

**momentum**: ok
- regime: invest 0%: bear: index < 200-DMA, breadth 31%

**intraday**: ok
- mode: ACTIVE (learning period (6/40 trades))
- SELL RELIANCE x55 1317.9 -> 1313.29 (square_off)
- day P&L ₹181

**etf**: ok
- pick: LIQUIDBEES | scores (blended 3/6/12-month return): GOLDBEES +2.1%, MON100 +1.5%, MID150BEES -5.5%, NIFTYBEES -6.2%
- holding: 5 x LIQUIDBEES

Files: `paper/history.csv`, `paper/swing/journal_paper.csv`, `paper/momentum/state.json`, `paper/intraday/journal.csv`.
