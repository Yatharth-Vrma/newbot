"""Zerodha equity-delivery (CNC) charges model.

Approximate statutory rates. Verify against https://zerodha.com/charges before relying on them;
all numbers are overridable from config.yaml under `costs:`.
"""
from dataclasses import dataclass


@dataclass
class CostModel:
    brokerage_pct: float = 0.0          # Zerodha delivery brokerage is zero
    stt_pct: float = 0.001              # 0.1% on buy and sell (delivery)
    exchange_pct: float = 0.0000297     # NSE transaction charge
    sebi_pct: float = 0.000001          # Rs 10 per crore
    stamp_buy_pct: float = 0.00015      # 0.015% on buy side only
    gst_pct: float = 0.18               # on brokerage + exchange + SEBI fees
    dp_charge_per_sell: float = 15.93   # per scrip per day sold from demat (incl. GST)
    slippage_pct: float = 0.0005        # 5 bps assumed price slippage each side

    def charges(self, side: str, qty: int, price: float) -> float:
        """Total rupee cost of one fill (excluding slippage, which is applied to price)."""
        value = qty * price
        brokerage = value * self.brokerage_pct
        exch = value * self.exchange_pct
        sebi = value * self.sebi_pct
        total = brokerage + exch + sebi
        total += value * self.stt_pct
        total += (brokerage + exch + sebi) * self.gst_pct
        if side == "BUY":
            total += value * self.stamp_buy_pct
        else:
            total += self.dp_charge_per_sell
        return total

    def fill_price(self, side: str, price: float) -> float:
        return price * (1 + self.slippage_pct) if side == "BUY" else price * (1 - self.slippage_pct)

    @classmethod
    def from_config(cls, cfg: dict | None):
        return cls(**(cfg or {}))
