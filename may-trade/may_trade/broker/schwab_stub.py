"""Schwab web adapter stub.

Live fills are typed into the Schwab web UI by a person. This class does not
store credentials, scrape a session, or submit an order.
"""

from __future__ import annotations

from typing import Sequence

from may_trade.broker.base import BrokerReceipt
from may_trade.models import OrderIntent

_MESSAGE = (
    "SchwabWebAdapter does not place or cancel orders. "
    "Live fills go through the Schwab web UI, outside this repository. "
    "This package does not store Schwab credentials or scrape a logged-in session. "
    "Use PaperBroker for dry-run intents, or hand the JSON intent to a human."
)


class SchwabWebAdapter:
    name = "schwab_web"

    def submit_open(self, intents: Sequence[OrderIntent]) -> list[BrokerReceipt]:
        raise NotImplementedError(_MESSAGE)

    def submit(self, intent: OrderIntent) -> BrokerReceipt:
        raise NotImplementedError(_MESSAGE)

    def cancel(self, order_id: str) -> BrokerReceipt:
        raise NotImplementedError(_MESSAGE)
