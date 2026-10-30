"""Route intents. Dry-run unless --live and MAY_LIVE_TRADING=1 are both set."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Sequence

from may_trade.broker.base import BrokerAdapter, BrokerReceipt
from may_trade.errors import LiveTradingDisabled, PolicyBreach
from may_trade.models import OrderIntent


@dataclass
class RouteResult:
    routed: bool
    dry_run: bool
    receipts: list[BrokerReceipt]
    message: str

    def to_dict(self) -> dict:
        return {
            "routed": self.routed,
            "dry_run": self.dry_run,
            "message": self.message,
            "receipts": [item.to_dict() for item in self.receipts],
        }


def route_open(
    intents: Sequence[OrderIntent],
    broker: BrokerAdapter,
    *,
    live: bool,
) -> RouteResult:
    if not intents:
        raise PolicyBreach("Nothing to route.")
    if not live:
        return RouteResult(False, True, [], "dry_run")
    if os.environ.get("MAY_LIVE_TRADING") != "1":
        raise LiveTradingDisabled(
            "Refusing to route: pass --live and set MAY_LIVE_TRADING=1. "
            "Default mode records intents only."
        )
    live_intents = [replace(item, dry_run=False) for item in intents]
    receipts = list(broker.submit_open(live_intents))
    return RouteResult(True, False, receipts, "routed")
