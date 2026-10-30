"""Automatic no-trade checks.

A lagging sector is not one of them. Sector rank only sorts the scan.
"""

from __future__ import annotations

from may_trade.codes import Code
from may_trade.config import Settings
from may_trade.models import QuoteSnapshot, Reason, Session, Side, TradePlan
from may_trade.money import long_side


def automatic_vetoes(
    plan: TradePlan,
    quote: QuoteSnapshot,
    settings: Settings,
) -> list[Reason]:
    reasons: list[Reason] = []
    reasons.extend(_stale(plan, quote))
    reasons.extend(_chase(plan, quote, settings))
    reasons.extend(_day_down(plan, quote, settings))
    reasons.extend(_near_high(plan, quote, settings))
    reasons.extend(_spread(quote, settings))
    if quote.benchmark_break_same_direction:
        reasons.append(
            Reason(
                Code.BENCHMARK_SAME_DIRECTION,
                "QQQ or SOXX broke today and this open is the same direction as that break.",
            )
        )
    # sector_lagging is intentionally unread. A full gate pass is not vetoed
    # for a lagging group, and a lagging group does not skip the gate.
    return reasons


def estimate_round_trip_cost(quote: QuoteSnapshot, entry: float, shares: int) -> float:
    total = 0.0 if quote.round_trip_cost is None else float(quote.round_trip_cost)
    per_share = quote.round_trip_cost_per_share or 0.0
    total += per_share * shares
    if quote.round_trip_cost is None and quote.round_trip_cost_per_share is None:
        if quote.spread_pct is not None and quote.spread_pct > 0:
            total += quote.spread_pct * entry * shares
    return total


def round_trip_veto(cost: float, expected_profit: float, settings: Settings) -> Reason | None:
    if expected_profit <= 0:
        return None
    if cost + 1e-9 >= expected_profit * settings.round_trip_cost_fraction:
        return Reason(
            Code.ROUND_TRIP_COST,
            "Round-trip cost is at least one fifth of the expected profit.",
        )
    return None


def _stale(plan: TradePlan, quote: QuoteSnapshot) -> list[Reason]:
    missing: list[str] = []
    if quote.ma10 is None:
        missing.append("ma10")
    if quote.rsi6 is None:
        missing.append("rsi6")
    if long_side(plan.side) and quote.high_52w is None:
        missing.append("high_52w")
    if not missing:
        return []
    return [
        Reason(
            Code.STALE_QUOTE,
            "Missing " + ", ".join(missing) + ". Incomplete quotes are not a signal.",
        )
    ]


def _chase(plan: TradePlan, quote: QuoteSnapshot, settings: Settings) -> list[Reason]:
    if not long_side(plan.side) or quote.ma10 is None or quote.rsi6 is None:
        return []
    if quote.ma10 <= 0:
        return []
    extension = (plan.entry - quote.ma10) / quote.ma10
    if extension > settings.ma10_chase_pct and quote.rsi6 > settings.rsi_chase:
        return [
            Reason(
                Code.CHASE_EXTENDED,
                "Entry is more than 8% above MA10 and RSI(6) is above 80.",
            )
        ]
    return []


def _day_down(plan: TradePlan, quote: QuoteSnapshot, settings: Settings) -> list[Reason]:
    if plan.side != Side.BUY:
        return []
    # Strictly more than the threshold. A print of exactly -3% is not a veto.
    if quote.day_change_pct < -settings.day_down_veto_pct:
        return [
            Reason(
                Code.DAY_DOWN,
                "The name is down more than 3% on the day. No bottom-fishing.",
            )
        ]
    return []


def _near_high(plan: TradePlan, quote: QuoteSnapshot, settings: Settings) -> list[Reason]:
    if not long_side(plan.side) or quote.high_52w is None or quote.has_new_catalyst:
        return []
    if quote.high_52w <= 0:
        return []
    distance = (quote.high_52w - plan.entry) / quote.high_52w
    if distance < settings.high_52w_proximity_pct:
        return [
            Reason(
                Code.NEAR_52W_HIGH,
                "Entry is inside 3% of the 52-week high without a new catalyst.",
            )
        ]
    return []


def _spread(quote: QuoteSnapshot, settings: Settings) -> list[Reason]:
    if quote.session != Session.EXTENDED:
        return []
    if quote.spread_pct is None or quote.spread_pct > settings.extended_spread_max_pct:
        return [
            Reason(
                Code.EXTENDED_SPREAD,
                "Extended-hours spread is above 0.5% or was not provided.",
            )
        ]
    return []
