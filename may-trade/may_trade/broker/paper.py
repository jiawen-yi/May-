"""In-memory paper ledger.

Records the entry intent and then the OCO intent. It does not simulate an
exchange fill and it does not talk to a broker.
"""

from __future__ import annotations

from typing import Sequence

from may_trade.broker.base import BrokerReceipt
from may_trade.errors import PolicyBreach
from may_trade.models import Book, Duration, OrderIntent, Position, Side


class PaperBroker:
    name = "paper"

    def __init__(self) -> None:
        self.recorded: list[OrderIntent] = []
        self.receipts: list[BrokerReceipt] = []
        self.planned_positions: dict[str, Position] = {}
        self._seq = 0

    def submit_open(self, intents: Sequence[OrderIntent]) -> list[BrokerReceipt]:
        if any(not item.routable for item in intents):
            raise PolicyBreach("Refusing a non-routable intent. Mag7 names need an explicit ack.")
        entries = [item for item in intents if item.intent_type == "entry"]
        ocos = [item for item in intents if item.intent_type == "oco"]
        if len(entries) != 1 or len(ocos) != 1:
            raise PolicyBreach("An open is one limit entry plus one OCO.")
        entry, oco = entries[0], ocos[0]
        self._validate_pair(entry, oco)
        entry_receipt = self._accept(entry, status="accepted")
        oco_receipt = self._accept(oco, status="working")
        self.planned_positions[entry.symbol] = self._planned_position(entry, oco)
        return [entry_receipt, oco_receipt]

    def submit(self, intent: OrderIntent) -> BrokerReceipt:
        if intent.intent_type == "entry":
            raise PolicyBreach(
                "Entry intents are accepted only together with an OCO via submit_open()."
            )
        return self._accept(intent, status="accepted")

    def cancel(self, order_id: str) -> BrokerReceipt:
        intent = OrderIntent(
            intent_id=order_id,
            group_id=order_id,
            intent_type="cancel",
            symbol="",
            side="sell",
            quantity=0,
            order_type="cancel",
            time_in_force="gtc",
            purpose="cancel",
        )
        return self._accept(intent, status="cancelled", message=f"cancelled {order_id}")

    def _validate_pair(self, entry: OrderIntent, oco: OrderIntent) -> None:
        if entry.order_type != "limit":
            raise PolicyBreach("Entry orders must be limit orders.")
        if entry.limit_price is None or entry.limit_price <= 0:
            raise PolicyBreach("Entry limit price is required.")
        if oco.order_type != "oco":
            raise PolicyBreach("Protection must be an OCO.")
        if entry.quantity < 1 or entry.quantity != oco.quantity:
            raise PolicyBreach("OCO quantity must match the entry quantity.")
        if entry.symbol != oco.symbol:
            raise PolicyBreach("OCO symbol must match the entry.")
        if entry.group_id != oco.group_id:
            raise PolicyBreach("Entry and OCO must share a group id.")
        expected_exit = "sell" if entry.side == "buy" else "buy"
        if entry.side not in ("buy", "short") or oco.side != expected_exit:
            raise PolicyBreach("OCO side does not close the entry.")
        kinds = {leg.kind: leg for leg in oco.legs}
        if set(kinds) != {"stop", "limit"}:
            raise PolicyBreach("OCO needs a stop leg and a limit leg.")
        if kinds["stop"].stop_price is None or kinds["limit"].limit_price is None:
            raise PolicyBreach("OCO legs are missing a stop or a target.")

    def _planned_position(self, entry: OrderIntent, oco: OrderIntent) -> Position:
        legs = {leg.kind: leg for leg in oco.legs}
        duration_value = str(entry.metadata.get("duration") or Duration.SWING_1_2.value)
        return Position(
            symbol=entry.symbol,
            shares=entry.quantity,
            cost=float(entry.limit_price or 0),
            stop=float(legs["stop"].stop_price or 0),
            target=float(legs["limit"].limit_price or 0),
            chain=str(entry.metadata.get("chain") or ""),
            side=Side.BUY if entry.side == "buy" else Side.SHORT,
            duration=Duration(duration_value),
            book=Book.SLEEVE,
            has_oco=True,
            oco_id=oco.intent_id,
        )

    def _accept(self, intent: OrderIntent, *, status: str, message: str = "") -> BrokerReceipt:
        self._seq += 1
        self.recorded.append(intent)
        receipt = BrokerReceipt(
            order_id=f"paper-{self._seq:04d}",
            status=status,
            intent_type=intent.intent_type,
            symbol=intent.symbol,
            quantity=intent.quantity,
            mode="paper",
            message=message or f"paper {status}",
            intent=intent,
        )
        self.receipts.append(receipt)
        return receipt
