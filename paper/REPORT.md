# Paper trading report: 2026-11-06

Fake money, real NSE prices. Nifty 50 column = what the same capital would be worth in a Nifty index fund since 2026-10-27.

| Bot | Start capital | Equity now | Return | Nifty 50 same period |
|---|---|---|---|---|
| swing | ₹100,000 | ₹101,326 | +1.33% | +10.02% |
| momentum | ₹500,000 | ₹500,734 | +0.15% | +10.02% |
| intraday | ₹100,000 | ₹103,671 | +3.67% | +10.02% |
| etf (Rs 3,000/month SIP) | invested ₹6,000 | ₹5,889 | -1.85% | same SIP in NIFTYBEES: ₹6,494 (+8.23%) |

## Today

**swing**: ok

**momentum**: ok
- regime: invest 0%: bear: index < 200-DMA, breadth 31%

**intraday**: ok
- mode: ACTIVE (learning period (7/40 trades))
- BUY TITAN x19 4858.26 -> 4992.5 (square_off)
- SELL HINDALCO x98 898.88 -> 904.37 (stop)
- BUY TCS x28 2559.47 -> 2540.74 (stop)
- day P&L ₹1,256

**etf**: ok
- pick: LIQUIDBEES | scores (blended 3/6/12-month return): GOLDBEES +2.1%, MON100 +1.5%, MID150BEES -5.5%, NIFTYBEES -6.2%
- holding: 5 x LIQUIDBEES

Files: `paper/history.csv`, `paper/swing/journal_paper.csv`, `paper/momentum/state.json`, `paper/intraday/journal.csv`.
