"""Open-lot management: OCO repair, profit ladder, stop ratchet, time stop.

Long stops only move up. Short stops only move down. A missing protective
order is replaced before any new idea. This module does not place orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import uuid4

from may_trade.duration import INTRADAY_FLAT_BY, in_et, ladder_for, planned_days
from may_trade.errors import PolicyBreach
from may_trade.models import DURATION_LABELS, Book, Duration, OcoLeg, OrderIntent, Position, Side
from may_trade.money import PRICE_TOL, is_looser, long_side, ratchet


@dataclass
class LifecycleResult:
    action: str
    intents: list[OrderIntent]
    position: Position
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "notes": list(self.notes),
            "position": self.position.to_dict(),
            "intents": [item.to_dict() for item in self.intents],
        }


def move_stop(position: Position, new_stop: float) -> Position:
    """Apply a stop change that only ratchets. Raises on a loosen."""

    if is_looser(position.side, new_stop, position.stop):
        if long_side(position.side):
            raise PolicyBreach("Long stops only move up.")
        raise PolicyBreach("Short stops only move down.")
    return replace(position, stop=new_stop)


def manage_position(position: Position, mark: float, as_of: datetime) -> LifecycleResult:
    pos = replace(position)
    if pos.book != Book.SLEEVE or not pos.sleeve:
        return LifecycleResult(
            "skip",
            [],
            pos,
            ["long-book and non-sleeve lots are not managed on the sleeve ladder"],
        )
    if pos.shares <= 0:
        return LifecycleResult("hold", [], pos, ["already_flat"])
    if _breached(pos, mark):
        return _flatten(pos, mark, "stop_breached")
    if pos.no_second_overnight and pos.trading_days_held >= 2:
        return _flatten(pos, mark, "second_overnight")
    if (
        pos.duration == Duration.INTRADAY
        and pos.trading_days_held == 0
        and in_et(as_of).timetz().replace(tzinfo=None) >= INTRADAY_FLAT_BY
    ):
        return _flatten(pos, mark, "session_flat")
    if pos.duration == Duration.INTRADAY and pos.trading_days_held >= 1:
        return _overnight_intraday(pos, mark)
    ladder = _maybe_ladder(pos, mark)
    if ladder is not None:
        return ladder
    if pos.ytd_loser and gain_pct(pos, mark) > PRICE_TOL and _risk_open(pos):
        return _ratchet_to(pos, pos.cost, "loser_breakeven")
    window = planned_days(pos.duration)
    if pos.trading_days_held > window + 1:
        return _flatten(pos, mark, "time_stop")
    if pos.trading_days_held > window and _risk_open(pos):
        return _ratchet_to(pos, pos.cost, "time_stop_breakeven")
    if not pos.has_oco:
        return _replace_protection(pos, pos.stop, pos.target, "missing_oco")
    return LifecycleResult("hold", [], pos, [])


def gain_pct(position: Position, mark: float) -> float:
    if position.cost <= 0:
        return 0.0
    if long_side(position.side):
        return (mark - position.cost) / position.cost
    return (position.cost - mark) / position.cost


def _breached(position: Position, mark: float) -> bool:
    if long_side(position.side):
        return mark <= position.stop + 1e-9
    return mark >= position.stop - 1e-9


def _risk_open(position: Position) -> bool:
    """True when the stop has not yet reached the cost (risk still open)."""

    if long_side(position.side):
        return position.stop < position.cost - PRICE_TOL
    return position.stop > position.cost + PRICE_TOL


def _level_price(cost: float, side: Side, level: float) -> float:
    if long_side(side):
        return round(cost * (1 + level), 4)
    return round(cost * (1 - level), 4)


def _partial_trim(shares: int) -> int:
    if shares <= 1:
        return 0
    third = shares // 3
    if third < 1:
        return 1
    if shares - third < 1:
        return shares - 1
    return third


def _final_trim(shares: int) -> int:
    if shares <= 1:
        return shares
    leave = shares // 4
    return shares - leave


def _maybe_ladder(position: Position, mark: float) -> LifecycleResult | None:
    rungs = ladder_for(position.duration, ytd_loser=position.ytd_loser)
    gain = gain_pct(position, mark)
    desired = 0
    for index, level in enumerate(rungs):
        if gain + 1e-12 >= level:
            desired = index + 1
    if desired <= position.ladder_stage:
        return None

    shares = position.shares
    stop = position.stop
    sold = 0
    if desired == len(rungs):
        sold = _final_trim(shares)
        shares -= sold
        stop = ratchet(position.side, stop, _level_price(position.cost, position.side, rungs[-2]))
        stage = desired
    else:
        stage = position.ladder_stage
        for step in range(position.ladder_stage + 1, desired + 1):
            trim = _partial_trim(shares)
            sold += trim
            shares -= trim
            level = 0.0 if step == 1 else rungs[step - 2]
            stop = ratchet(position.side, stop, _level_price(position.cost, position.side, level))
            stage = step

    updated = replace(
        position,
        shares=shares,
        stop=round(stop, 4),
        ladder_stage=stage,
        has_oco=shares > 0,
    )
    intents = _transition(position, updated, sold, mark, "ladder_trim")
    return LifecycleResult("ladder", intents, updated, [f"rung_{stage}"])


def _overnight_intraday(position: Position, mark: float) -> LifecycleResult:
    if position.trading_days_held >= 2 or position.no_second_overnight:
        return _flatten(position, mark, "second_overnight")
    if _breached(position, mark):
        return _flatten(position, mark, "stop_breached")
    near = _level_price(position.cost, position.side, 0.04)
    if long_side(position.side):
        new_target = min(position.target, near)
        if mark >= new_target - 1e-9:
            return _flatten(position, mark, "retag_target_met")
    else:
        new_target = max(position.target, near)
        if mark <= new_target + 1e-9:
            return _flatten(position, mark, "retag_target_met")
    updated = replace(
        position,
        duration=Duration.SWING_1_2,
        target=round(new_target, 4),
        no_second_overnight=True,
        has_oco=True,
    )
    intents = _transition(position, updated, 0, mark, "retag_swing")
    return LifecycleResult(
        "retag",
        intents,
        updated,
        ["retag_swing_1_2", "no_second_overnight"],
    )


def _ratchet_to(position: Position, new_stop: float, purpose: str) -> LifecycleResult:
    tightened = round(ratchet(position.side, position.stop, new_stop), 4)
    if abs(tightened - position.stop) <= PRICE_TOL and position.has_oco:
        return LifecycleResult("hold", [], position, [f"{purpose}_already_tight"])
    updated = replace(position, stop=tightened, has_oco=True)
    return LifecycleResult(purpose, _transition(position, updated, 0, None, purpose), updated, [purpose])


def _replace_protection(
    position: Position, stop: float, target: float, purpose: str
) -> LifecycleResult:
    updated = replace(position, stop=stop, target=target, has_oco=True)
    return LifecycleResult("protect", _transition(position, updated, 0, None, purpose), updated, [purpose])


def _flatten(position: Position, mark: float, purpose: str) -> LifecycleResult:
    updated = replace(position, shares=0, has_oco=False)
    intents = _transition(position, updated, position.shares, mark, purpose)
    return LifecycleResult("flatten", intents, updated, [purpose])


def _transition(
    previous: Position,
    updated: Position,
    sell_qty: int,
    mark: float | None,
    purpose: str,
) -> list[OrderIntent]:
    """Cancel, re-arm the remainder, then sell. Keeps the naked window short."""

    group = uuid4().hex[:16]
    exit_side = "sell" if long_side(previous.side) else "buy"
    intents: list[OrderIntent] = []
    if previous.has_oco:
        intents.append(
            _intent(
                group,
                intent_type="cancel",
                symbol=previous.symbol,
                side=exit_side,
                quantity=previous.shares,
                order_type="cancel",
                time_in_force="gtc",
                purpose="cancel_oco",
                metadata={"oco_id": previous.oco_id or "", "reason": purpose},
            )
        )
    if updated.shares > 0:
        intents.append(
            _intent(
                group,
                intent_type="oco",
                symbol=updated.symbol,
                side=exit_side,
                quantity=updated.shares,
                order_type="oco",
                time_in_force="gtc",
                purpose="protection",
                trigger="replace",
                legs=[
                    OcoLeg(kind="stop", stop_price=round(updated.stop, 4)),
                    OcoLeg(kind="limit", limit_price=round(updated.target, 4)),
                ],
                metadata={
                    "duration": updated.duration.value,
                    "duration_label": DURATION_LABELS[updated.duration],
                    "reason": purpose,
                },
            )
        )
    if sell_qty > 0:
        if mark is None:
            raise PolicyBreach("A reduce or flatten needs a limit price.")
        intents.append(
            _intent(
                group,
                intent_type="flatten" if updated.shares == 0 else "trim",
                symbol=previous.symbol,
                side=exit_side,
                quantity=sell_qty,
                order_type="limit",
                time_in_force="day",
                limit_price=round(mark, 4),
                purpose=purpose,
                metadata={"marketable": True, "reason": purpose},
            )
        )
    return intents


def _intent(group: str, **kwargs) -> OrderIntent:
    return OrderIntent(
        intent_id=uuid4().hex[:12],
        group_id=group,
        book=Book.SLEEVE.value,
        dry_run=True,
        **kwargs,
    )
