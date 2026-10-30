"""Broker boundary. Adapters accept intents; they are not imported by the gate."""

from __future__ import annotations

from typing import Protocol, Sequence

from may_trade.models import OrderIntent


class BrokerReceipt:
    """What an adapter returns after it accepts an intent into its own ledger."""

    def __init__(
        self,
        *,
        order_id: str,
        status: str,
        intent_type: str,
        symbol: str,
        quantity: int,
        mode: str,
        message: str,
        intent: OrderIntent,
    ) -> None:
        self.order_id = order_id
        self.status = status
        self.intent_type = intent_type
        self.symbol = symbol
        self.quantity = quantity
        self.mode = mode
        self.message = message
        self.intent = intent

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "status": self.status,
            "intent_type": self.intent_type,
            "symbol": self.symbol,
            "quantity": self.quantity,
            "mode": self.mode,
            "message": self.message,
            "intent": self.intent.to_dict(),
        }


class BrokerAdapter(Protocol):
    name: str

    def submit_open(self, intents: Sequence[OrderIntent]) -> list[BrokerReceipt]:
        """Accept one limit entry together with its protective OCO."""

    def submit(self, intent: OrderIntent) -> BrokerReceipt:
        """Accept a single non-entry intent (cancel, trim, flatten, park)."""

    def cancel(self, order_id: str) -> BrokerReceipt:
        """Cancel a previously accepted order id."""
