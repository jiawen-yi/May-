"""Hard limits: per-trade risk, daily halt, stack, concentration, chain, brakes.

Sleeve gross cap is account equity (the hard-limit table after the fixed-dollar
sleeve was retired). The 40% name cap and the 3% stacked-risk cap still bind.
Negative cash is not a veto. Only this symbol's own realized loss tightens size.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from may_trade.codes import Code
from may_trade.config import Settings
from may_trade.models import (
    AccountState,
    Book,
    Duration,
    Position,
    QuoteSnapshot,
    Reason,
    Session,
    Side,
    TradePlan,
)
from may_trade.money import cents, exceeds, long_side


@dataclass
class RiskAssessment:
    shares: int
    per_trade_risk: float
    per_trade_risk_pct: float
    risk_cap_pct: float
    stack_risk: float
    stack_risk_pct: float
    concentration_pct: float
    chain_positions: int
    notional: float
    sleeve_gross: float
    size_multiplier: float
    allowed: bool
    reasons: list[Reason] = field(default_factory=list)

    def breakdown(self):
        from may_trade.models import RiskBreakdown

        return RiskBreakdown(
            shares=self.shares,
            per_trade_risk=round(self.per_trade_risk, 2),
            per_trade_risk_pct=round(self.per_trade_risk_pct, 6),
            risk_cap_pct=round(self.risk_cap_pct, 6),
            stack_risk=round(self.stack_risk, 2),
            stack_risk_pct=round(self.stack_risk_pct, 6),
            concentration_pct=round(self.concentration_pct, 6),
            chain_positions=self.chain_positions,
            notional=round(self.notional, 2),
            sleeve_gross=round(self.sleeve_gross, 2),
            size_multiplier=round(self.size_multiplier, 4),
            allowed=self.allowed,
        )


def sleeve_positions(account: AccountState) -> list[Position]:
    return [
        item
        for item in account.positions
        if item.sleeve and item.book == Book.SLEEVE and item.shares > 0
    ]


def chain_occupancy(account: AccountState) -> dict[str, set[str]]:
    occupied: dict[str, set[str]] = {}
    for item in sleeve_positions(account):
        occupied.setdefault(item.chain, set()).add(item.symbol)
    return occupied


def position_open_risk(position: Position) -> float:
    if position.side == Side.SHORT:
        per_share = position.stop - position.cost
    else:
        per_share = position.cost - position.stop
    if per_share <= 0:
        return 0.0
    return per_share * position.shares


def position_market_value(position: Position) -> float:
    price = position.mark if position.mark is not None else position.cost
    return max(0.0, price) * position.shares


def _max_shares(budget: float, per_unit: float) -> int:
    if budget <= 0 or per_unit <= 0:
        return 0
    count = int(math.floor((budget + 1e-6) / per_unit))
    while count > 0 and cents(count * per_unit) > cents(budget):
        count -= 1
    return count


def assess_risk(
    plan: TradePlan,
    quote: QuoteSnapshot,
    account: AccountState,
    *,
    duration: Duration,
    effective_stop: float,
    settings: Settings,
) -> RiskAssessment:
    reasons: list[Reason] = []
    if account.equity <= 0:
        reasons.append(Reason(Code.INVALID_EQUITY, "Account equity must be positive."))

    if account.hard_pause:
        reasons.append(Reason(Code.HARD_PAUSE, "Hard pause is on. No new sleeve opens or adds."))
    if account.pause_new_entries or account.consecutive_stop_losses >= settings.consecutive_stops_to_pause:
        reasons.append(
            Reason(
                Code.LOSS_BRAKE,
                "Two consecutive stop-outs pause new entries for the next session.",
            )
        )

    day_loss = -min(account.day_pnl, 0.0)
    halt_line = account.equity * settings.day_loss_halt_pct
    if account.equity > 0 and cents(day_loss) > 0 and cents(day_loss) >= cents(halt_line):
        reasons.append(
            Reason(
                Code.DAILY_LOSS_HALT,
                "Day loss has reached 1.5% of equity. No new opens or adds.",
            )
        )

    if plan.symbol in account.stopped_today:
        reasons.append(
            Reason(
                Code.STOP_COOLDOWN,
                "This symbol was stopped today. No re-entry until the next session.",
            )
        )

    occupied = chain_occupancy(account)
    chain_symbols = occupied.get(plan.chain, set())
    if plan.symbol not in chain_symbols and len(chain_symbols) >= settings.chain_max_positions:
        reasons.append(
            Reason(
                Code.CHAIN_FULL,
                "That industry chain already has 2 sleeve positions.",
            )
        )

    ytd_loser = plan.symbol in account.realized_loss_symbols_ytd
    cap = min(
        settings.duration_cap(duration.value),
        settings.per_trade_hard_cap_pct,
    )
    if ytd_loser:
        cap = min(cap, settings.loser_risk_cap_pct)

    multiplier = 1.0
    if quote.soft_tape:
        multiplier *= settings.soft_tape_size_multiplier
    if quote.session == Session.EXTENDED:
        multiplier *= settings.extended_size_multiplier
    risk_cap = cap * multiplier

    per_share = (plan.entry - effective_stop) if long_side(plan.side) else (effective_stop - plan.entry)
    if per_share <= 0 or plan.entry <= 0:
        reasons.append(Reason(Code.STOP_GEOMETRY, "Stop is on the wrong side of entry."))
        per_share = 0.0

    equity = account.equity if account.equity > 0 else 0.0
    risk_budget = equity * risk_cap
    shares_risk = _max_shares(risk_budget, per_share) if per_share > 0 else 0

    same_name_mv = sum(
        position_market_value(item)
        for item in sleeve_positions(account)
        if item.symbol == plan.symbol
    )
    conc_room = equity * settings.name_concentration_max_pct - same_name_mv
    shares_conc = _max_shares(conc_room, plan.entry)

    sleeve_mv = sum(position_market_value(item) for item in sleeve_positions(account))
    shares_sleeve = _max_shares(equity - sleeve_mv, plan.entry)

    open_stack = sum(position_open_risk(item) for item in sleeve_positions(account))
    stack_room = equity * settings.stack_risk_max_pct - open_stack
    shares_stack = _max_shares(stack_room, per_share) if per_share > 0 else 0

    shares_loser: int | None = None
    if ytd_loser:
        notional_shares = _max_shares(settings.wash_rebuy_notional_cap, plan.entry)
        limits = [notional_shares]
        prior = account.prior_sleeve_shares.get(plan.symbol, 0)
        if prior >= 1:
            limits.append(prior // 2)
        shares_loser = min(limits)
        if quote.ma10 is None or quote.ma10 <= 0:
            reasons.append(
                Reason(
                    Code.LOSER_MA10_REQUIRED,
                    "A symbol with a realized loss this year needs MA10 before a re-entry.",
                )
            )
        else:
            if long_side(plan.side):
                extension = (plan.entry - quote.ma10) / quote.ma10
            else:
                extension = (quote.ma10 - plan.entry) / quote.ma10
            if extension > settings.loser_ma10_max_extension:
                reasons.append(
                    Reason(
                        Code.LOSER_NOT_PULLED_BACK,
                        "Re-entry after a realized loss has to be within 3% of MA10.",
                    )
                )

    if duration == Duration.INTRADAY and equity > 0:
        if equity < settings.pdt_equity and account.day_trades_rolling_5 >= settings.pdt_day_trades:
            reasons.append(
                Reason(
                    Code.PDT_LIMIT,
                    "Account under $25k is at the rolling day-trade limit.",
                )
            )
        if account.intraday_opens_today >= settings.max_intraday_per_day:
            reasons.append(
                Reason(
                    Code.DESK_INTRADAY_CAP,
                    "Desk cap is 2 intraday opens per session.",
                )
            )

    if quote.event_in_hold_window and not plan.event_planned and duration != Duration.INTRADAY:
        reasons.append(
            Reason(
                Code.UNPLANNED_EVENT,
                "An unplanned event sits inside the hold window. Do not open a swing into it.",
            )
        )

    limits = [shares_risk, shares_conc, shares_sleeve, shares_stack]
    if shares_loser is not None:
        limits.append(shares_loser)
    max_shares = max(0, min(limits)) if limits else 0

    if plan.shares is None:
        shares = max_shares
        if shares < 1:
            reasons.append(
                Reason(
                    Code.SIZE_BELOW_ONE_SHARE,
                    "Risk, concentration, or stack room cannot fund one share.",
                )
            )
    else:
        shares = int(plan.shares)
        if shares < 1:
            reasons.append(Reason(Code.SIZE_BELOW_ONE_SHARE, "Share count must be at least 1."))
        else:
            if per_share > 0 and exceeds(shares * per_share, risk_budget):
                reasons.append(
                    Reason(
                        Code.PER_TRADE_RISK,
                        "Entry-to-stop risk is above the hold-length cap (and the 2% hard cap).",
                    )
                )
            if exceeds(same_name_mv + shares * plan.entry, equity * settings.name_concentration_max_pct):
                reasons.append(
                    Reason(Code.CONCENTRATION, "Sleeve market value in this name would exceed 40% of equity.")
                )
            if exceeds(sleeve_mv + shares * plan.entry, equity):
                reasons.append(
                    Reason(Code.SLEEVE_CAP, "Sleeve gross would exceed account equity.")
                )
            if per_share > 0 and exceeds(open_stack + shares * per_share, equity * settings.stack_risk_max_pct):
                reasons.append(
                    Reason(
                        Code.STACK_RISK,
                        "Open stop-risk plus this trade would exceed 3% of equity.",
                    )
                )
            if shares_loser is not None and shares > shares_loser:
                reasons.append(
                    Reason(
                        Code.WASH_REBUY_SIZE,
                        "This symbol lost money this year. Size is capped at half the prior lot "
                        "or the rebuy notional cap, whichever is smaller.",
                    )
                )

    per_trade = shares * per_share
    notional = shares * plan.entry
    stack = open_stack + per_trade
    gross = sleeve_mv + notional
    name_mv = same_name_mv + notional
    return RiskAssessment(
        shares=shares,
        per_trade_risk=per_trade,
        per_trade_risk_pct=(per_trade / equity) if equity else 0.0,
        risk_cap_pct=risk_cap,
        stack_risk=stack,
        stack_risk_pct=(stack / equity) if equity else 0.0,
        concentration_pct=(name_mv / equity) if equity else 0.0,
        chain_positions=len(chain_symbols | ({plan.symbol} if shares else set())),
        notional=notional,
        sleeve_gross=gross,
        size_multiplier=multiplier,
        allowed=not reasons,
        reasons=reasons,
    )
