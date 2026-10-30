"""Build limit-entry and OCO intents. No market chase orders, no live routing."""

from __future__ import annotations

from uuid import uuid4

from may_trade.duration import ladder_for
from may_trade.errors import PolicyBreach
from may_trade.models import (
    DURATION_LABELS,
    Book,
    Duration,
    OcoLeg,
    OrderIntent,
    Session,
    Side,
    TradePlan,
)
from may_trade.money import long_side
from may_trade.universe import CASH_PARK_SYMBOLS


def build_open_intents(
    plan: TradePlan,
    *,
    duration: Duration,
    shares: int,
    effective_stop: float,
    rr: float,
    session: Session,
    routable: bool,
    requires_user_ack: bool,
    ytd_loser: bool,
) -> list[OrderIntent]:
    if shares < 1:
        raise PolicyBreach("Refusing an open intent with no shares.")
    if plan.side not in (Side.BUY, Side.SHORT):
        raise PolicyBreach("Open intents are buy or short.")

    group = uuid4().hex[:16]
    entry_side = "buy" if long_side(plan.side) else "short"
    exit_side = "sell" if long_side(plan.side) else "buy"
    rungs = [round(level, 4) for level in ladder_for(duration, ytd_loser=ytd_loser)]
    session_tag = "非正规时段" if session == Session.EXTENDED else "regular"
    meta = {
        "thesis": plan.thesis.strip(),
        "duration": duration.value,
        "duration_label": DURATION_LABELS[duration],
        "rr": round(rr, 4),
        "entry": round(plan.entry, 4),
        "stop": round(effective_stop, 4),
        "target": round(plan.target, 4),
        "stop_basis": plan.stop_basis.strip(),
        "chain": plan.chain,
        "is_add": plan.is_add,
        "ytd_loser": ytd_loser,
        "ladder": rungs,
        "session_tag": session_tag,
    }
    entry = OrderIntent(
        intent_id=_new_id(),
        group_id=group,
        intent_type="entry",
        symbol=plan.symbol,
        side=entry_side,
        quantity=shares,
        order_type="limit",
        time_in_force="day",
        limit_price=round(plan.entry, 4),
        purpose="open",
        book=Book.SLEEVE.value,
        session=session.value,
        routable=routable,
        requires_user_ack=requires_user_ack,
        metadata=meta,
    )
    oco = OrderIntent(
        intent_id=_new_id(),
        group_id=group,
        intent_type="oco",
        symbol=plan.symbol,
        side=exit_side,
        quantity=shares,
        order_type="oco",
        time_in_force="gtc",
        purpose="protection",
        book=Book.SLEEVE.value,
        session=session.value,
        routable=routable,
        requires_user_ack=requires_user_ack,
        trigger="on_entry_fill",
        legs=[
            OcoLeg(kind="stop", stop_price=round(effective_stop, 4)),
            OcoLeg(kind="limit", limit_price=round(plan.target, 4)),
        ],
        metadata={
            "duration": duration.value,
            "duration_label": DURATION_LABELS[duration],
            "chain": plan.chain,
            "session_tag": session_tag,
            "ladder": rungs,
        },
    )
    return [entry, oco]


def cash_park_intent(symbol: str, quantity: int, limit_price: float) -> OrderIntent:
    """Idle-cash park. Not a sleeve gate trade and not an OCO."""

    ticker = symbol.upper().strip()
    if ticker not in CASH_PARK_SYMBOLS:
        raise PolicyBreach("Idle cash parks in BOXX or SGOV only.")
    if quantity < 1 or limit_price <= 0:
        raise PolicyBreach("Cash-park intent needs a positive whole-share limit.")
    return OrderIntent(
        intent_id=_new_id(),
        group_id=_new_id(),
        intent_type="cash_park",
        symbol=ticker,
        side="buy",
        quantity=quantity,
        order_type="limit",
        time_in_force="day",
        limit_price=round(limit_price, 4),
        purpose="cash_park",
        book="cash",
        routable=True,
        metadata={"oco": False, "gate_exempt": True},
    )


def _new_id() -> str:
    return uuid4().hex[:12]
