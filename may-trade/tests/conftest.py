"""Shared plan / quote / account factories. Defaults are a passing 1–2 day swing."""

from __future__ import annotations

from datetime import datetime

from may_trade.duration import ET
from may_trade.models import (
    AccountState,
    Duration,
    InstrumentKind,
    QuoteSnapshot,
    Session,
    Side,
    TradePlan,
)

AS_OF = datetime(2026, 10, 23, 10, 30, tzinfo=ET)


def make_plan(**overrides) -> TradePlan:
    base = dict(
        symbol="ANET",
        side=Side.BUY,
        entry=100.0,
        stop=95.0,
        target=112.0,
        thesis="Pullback is holding the recent shelf; the stop is the swing low under that shelf.",
        chain="optics",
        instrument=InstrumentKind.COMMON_STOCK,
        duration=Duration.SWING_1_2,
        shares=50,
        stop_basis="swing low under the last platform",
        stop_is_structural=True,
        structural_stop=95.0,
    )
    base.update(overrides)
    if "stop" in overrides and "structural_stop" not in overrides:
        base["structural_stop"] = base["stop"]
    return TradePlan(**base)


def make_quote(**overrides) -> QuoteSnapshot:
    base = dict(
        last=100.2,
        day_change_pct=0.004,
        session=Session.REGULAR,
        ma10=99.0,
        rsi6=58.0,
        high_52w=150.0,
        spread_pct=0.0004,
        has_new_catalyst=False,
        benchmark_break_same_direction=False,
        sector_lagging=False,
        sector_score=1.0,
        soft_tape=False,
        high_vol=False,
        up_structure=True,
        round_trip_cost=2.0,
    )
    base.update(overrides)
    return QuoteSnapshot(**base)


def make_account(**overrides) -> AccountState:
    base = dict(
        equity=100_000.0,
        cash=25_000.0,
        day_pnl=0.0,
        consecutive_stop_losses=0,
        pause_new_entries=False,
        hard_pause=False,
        day_trades_rolling_5=0,
        intraday_opens_today=0,
        realized_loss_symbols_ytd=set(),
        stopped_today=set(),
        prior_sleeve_shares={},
        positions=[],
        mag7_approved=set(),
    )
    base.update(overrides)
    return AccountState(**base)


def reason_codes(result) -> list[str]:
    return [item.code for item in result.reasons]
