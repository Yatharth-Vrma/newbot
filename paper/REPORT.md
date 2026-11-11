# Paper trading report: 2026-11-11

Fake money, real NSE prices. Nifty 50 column = what the same capital would be worth in a Nifty index fund since 2026-10-27.

| Bot | Start capital | Equity now | Return | Nifty 50 same period |
|---|---|---|---|---|
| swing | ₹100,000 | ₹101,450 | +1.45% | +10.09% |
| momentum | ₹500,000 | ₹500,954 | +0.19% | +10.09% |
| intraday | ₹100,000 | ₹102,521 | +2.52% | +10.09% |
| etf (Rs 3,000/month SIP) | invested ₹6,000 | ₹5,889 | -1.85% | same SIP in NIFTYBEES: ₹6,545 (+9.09%) |

## Today

**swing**: already_done

**momentum**: already_done

**intraday**: ok
- mode: ACTIVE (learning period (12/40 trades))
- BUY HINDALCO x78 958.34 -> 958.71 (square_off)
- BUY TCS x30 2503.0 -> 2485.3 (stop)
- BUY SBIN x89 1061.22 -> 1059.93 (square_off)
- day P&L ₹-845

**etf**: ok
- pick: LIQUIDBEES | scores (blended 3/6/12-month return): GOLDBEES +2.1%, MON100 +1.5%, MID150BEES -5.5%, NIFTYBEES -6.2%
- holding: 5 x LIQUIDBEES

Files: `paper/history.csv`, `paper/swing/journal_paper.csv`, `paper/momentum/state.json`, `paper/intraday/journal.csv`.
