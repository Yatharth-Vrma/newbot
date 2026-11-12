# Paper trading report: 2026-11-12

Fake money, real NSE prices. Nifty 50 column = what the same capital would be worth in a Nifty index fund since 2026-10-27.

| Bot | Start capital | Equity now | Return | Nifty 50 same period |
|---|---|---|---|---|
| swing | ₹100,000 | ₹101,328 | +1.33% | +11.01% |
| momentum | ₹500,000 | ₹501,101 | +0.22% | +11.01% |
| intraday | ₹100,000 | ₹103,404 | +3.40% | +11.01% |
| etf (Rs 3,000/month SIP) | invested ₹6,000 | ₹5,889 | -1.85% | same SIP in NIFTYBEES: ₹6,545 (+9.09%) |

## Today

**swing**: ok
- BUY BHARTIARTL x4 (AMO limit 2130.1)

**momentum**: ok
- regime: invest 0%: bear: index < 200-DMA, breadth 31%

**intraday**: ok
- mode: ACTIVE (learning period (15/40 trades))
- SELL APOLLOHOSP x10 8488.9 -> 8502.55 (square_off)
- BUY SBIN x85 1073.82 -> 1087.67 (square_off)
- day P&L ₹883

**etf**: already_done

Files: `paper/history.csv`, `paper/swing/journal_paper.csv`, `paper/momentum/state.json`, `paper/intraday/journal.csv`.
