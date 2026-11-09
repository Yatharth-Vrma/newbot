# Paper trading report: 2026-11-09

Fake money, real NSE prices. Nifty 50 column = what the same capital would be worth in a Nifty index fund since 2026-10-27.

| Bot | Start capital | Equity now | Return | Nifty 50 same period |
|---|---|---|---|---|
| swing | ₹100,000 | ₹101,450 | +1.45% | +10.02% |
| momentum | ₹500,000 | ₹500,954 | +0.19% | +10.02% |
| intraday | ₹100,000 | ₹103,366 | +3.37% | +10.02% |
| etf (Rs 3,000/month SIP) | invested ₹6,000 | ₹5,889 | -1.85% | same SIP in NIFTYBEES: ₹6,511 (+8.52%) |

## Today

**swing**: ok

**momentum**: ok
- regime: invest 0%: bear: index < 200-DMA, breadth 31%

**intraday**: ok
- mode: ACTIVE (learning period (10/40 trades))
- SELL KOTAKBANK x193 479.41 -> 477.34 (square_off)
- BUY ICICIBANK x61 1587.38 -> 1578.48 (stop)
- day P&L ₹-305

**etf**: ok
- pick: LIQUIDBEES | scores (blended 3/6/12-month return): GOLDBEES +2.1%, MON100 +1.5%, MID150BEES -5.5%, NIFTYBEES -6.2%
- holding: 5 x LIQUIDBEES

Files: `paper/history.csv`, `paper/swing/journal_paper.csv`, `paper/momentum/state.json`, `paper/intraday/journal.csv`.
