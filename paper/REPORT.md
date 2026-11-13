# Paper trading report: 2026-11-13

Fake money, real NSE prices. Nifty 50 column = what the same capital would be worth in a Nifty index fund since 2026-10-27.

| Bot | Start capital | Equity now | Return | Nifty 50 same period |
|---|---|---|---|---|
| swing | ₹100,000 | ₹101,451 | +1.45% | +11.21% |
| momentum | ₹500,000 | ₹501,175 | +0.23% | +11.21% |
| intraday | ₹100,000 | ₹102,674 | +2.67% | +11.21% |
| etf (Rs 3,000/month SIP) | invested ₹6,000 | ₹5,889 | -1.85% | same SIP in NIFTYBEES: ₹6,582 (+9.70%) |

## Today

**swing**: ok

**momentum**: ok
- regime: invest 0%: bear: index < 200-DMA, breadth 31%

**intraday**: ok
- mode: ACTIVE (learning period (17/40 trades))
- SELL SBIN x83 1080.93 -> 1081.22 (square_off)
- BUY DRREDDY x75 1395.42 -> 1388.18 (stop)
- day P&L ₹-730

**etf**: ok
- pick: LIQUIDBEES | scores (blended 3/6/12-month return): GOLDBEES +2.1%, MON100 +1.5%, MID150BEES -5.5%, NIFTYBEES -6.2%
- holding: 5 x LIQUIDBEES

Files: `paper/history.csv`, `paper/swing/journal_paper.csv`, `paper/momentum/state.json`, `paper/intraday/journal.csv`.
