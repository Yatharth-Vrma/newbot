# Paper trading report: 2026-11-04

Fake money, real NSE prices. Nifty 50 column = what the same capital would be worth in a Nifty index fund since 2026-10-27.

| Bot | Start capital | Equity now | Return | Nifty 50 same period |
|---|---|---|---|---|
| swing | ₹100,000 | ₹100,299 | +0.30% | +4.66% |
| momentum | ₹500,000 | ₹500,514 | +0.10% | +4.66% |
| intraday | ₹100,000 | ₹102,234 | +2.23% | +4.66% |
| etf (Rs 3,000/month SIP) | invested ₹6,000 | ₹5,889 | -1.85% | same SIP in NIFTYBEES: ₹6,184 (+3.06%) |

## Today

**swing**: ok

**momentum**: ok
- regime: invest 0%: bear: index < 200-DMA, breadth 31%

**intraday**: ok
- mode: ACTIVE (learning period (5/40 trades))
- BUY JSWSTEEL x57 1324.65 -> 1334.6 (square_off)
- day P&L ₹493

**etf**: ok
- pick: LIQUIDBEES | scores (blended 3/6/12-month return): GOLDBEES +2.1%, MON100 +1.5%, MID150BEES -5.5%, NIFTYBEES -6.2%
- holding: 5 x LIQUIDBEES

Files: `paper/history.csv`, `paper/swing/journal_paper.csv`, `paper/momentum/state.json`, `paper/intraday/journal.csv`.
