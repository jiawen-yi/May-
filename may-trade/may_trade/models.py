"""Shared records for plans, quotes, accounts, and order intents.

Percents are fractions (0.03 == 3%). Prices are USD. Section references in
other modules point at the desk playbook; this package does not copy it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class Duration(str, Enum):
    INTRADAY = "intraday"  # 日内
    SWING_1_2 = "swing_1_2"  # 短波 1–2 day
    SWING_3_5 = "swing_3_5"  # 波段 3–5 day


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"
    SHORT = "short"
    COVER = "cover"


class Session(str, Enum):
    REGULAR = "regular"
    EXTENDED = "extended"


class InstrumentKind(str, Enum):
    COMMON_STOCK = "common_stock"
    UNLEVERED_ETF = "unlevered_etf"
    LEVERAGED_ETF = "leveraged_etf"
    OPTION = "option"
    OTHER = "other"


class Decision(str, Enum):
    PASS = "PASS"  # do
    FAIL = "FAIL"  # don't
    WAIT_PULLBACK = "WAIT_PULLBACK"  # rest a limit at the pullback


class Book(str, Enum):
    SLEEVE = "sleeve"
    LONG = "long"


DURATION_LABELS = {
    Duration.INTRADAY: "日内",
    Duration.SWING_1_2: "短波",
    Duration.SWING_3_5: "波段",
}


def to_plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_plain(v) for v in value]
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return value


@dataclass(frozen=True)
class Reason:
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass
class IntradayUnlock:
    """Caller assertion that the user explicitly asked for an intraday hold.

    ``explicit`` must be True. A scan, a soft tape, or a prior day-trade does
    not unlock the tag. The phrase is recorded for the journal; it is not
    parsed as a hidden permission.
    """

    explicit: bool = False
    phrase: str | None = None


@dataclass
class OcoLeg:
    kind: str  # "stop" or "limit"
    stop_price: float | None = None
    limit_price: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"kind": self.kind}
        if self.stop_price is not None:
            data["stop_price"] = self.stop_price
        if self.limit_price is not None:
            data["limit_price"] = self.limit_price
        return data


@dataclass
class OrderIntent:
    """A structured order the desk (or a paper adapter) can read.

    Intents are dry-run until a live route copies them. They are never a
    fill, and they never include broker credentials.
    """

    intent_type: str
    symbol: str
    side: str
    quantity: int
    order_type: str
    time_in_force: str
    intent_id: str
    group_id: str
    dry_run: bool = True
    limit_price: float | None = None
    stop_price: float | None = None
    legs: list[OcoLeg] = field(default_factory=list)
    purpose: str = ""
    book: str = Book.SLEEVE.value
    session: str = Session.REGULAR.value
    requires_user_ack: bool = False
    routable: bool = True
    trigger: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "intent_id": self.intent_id,
            "group_id": self.group_id,
            "intent_type": self.intent_type,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "order_type": self.order_type,
            "time_in_force": self.time_in_force,
            "dry_run": self.dry_run,
            "purpose": self.purpose,
            "book": self.book,
            "session": self.session,
            "routable": self.routable,
            "requires_user_ack": self.requires_user_ack,
        }
        if self.limit_price is not None:
            data["limit_price"] = self.limit_price
        if self.stop_price is not None:
            data["stop_price"] = self.stop_price
        if self.legs:
            data["legs"] = [leg.to_dict() for leg in self.legs]
        if self.trigger:
            data["trigger"] = self.trigger
        if self.metadata:
            data["metadata"] = to_plain(self.metadata)
        return data


@dataclass
class TradePlan:
    symbol: str
    side: Side
    entry: float
    stop: float
    target: float
    thesis: str
    chain: str
    instrument: InstrumentKind
    duration: Duration = Duration.SWING_1_2
    shares: int | None = None
    stop_basis: str = ""
    stop_is_structural: bool = True
    structural_stop: float | None = None
    entry_low: float | None = None
    entry_high: float | None = None
    is_add: bool = False
    event_planned: bool = False
    book: Book = Book.SLEEVE
    mag7_approved: bool = False

    def __post_init__(self) -> None:
        self.symbol = self.symbol.upper().strip()
        self.chain = self.chain.strip().lower()


@dataclass
class QuoteSnapshot:
    last: float
    day_change_pct: float
    session: Session = Session.REGULAR
    ma10: float | None = None
    rsi6: float | None = None
    high_52w: float | None = None
    spread_pct: float | None = None
    atr_intraday: float | None = None
    has_new_catalyst: bool = False
    benchmark_break_same_direction: bool = False
    sector: str | None = None
    sector_lagging: bool = False
    sector_score: float = 0.0
    soft_tape: bool = False
    high_vol: bool = False
    up_structure: bool = True
    event_in_hold_window: bool = False
    round_trip_cost: float | None = None
    round_trip_cost_per_share: float | None = None


@dataclass
class Position:
    symbol: str
    shares: int
    cost: float
    stop: float
    target: float
    chain: str
    side: Side = Side.BUY
    duration: Duration = Duration.SWING_1_2
    sleeve: bool = True
    book: Book = Book.SLEEVE
    oco_id: str | None = None
    has_oco: bool = True
    ladder_stage: int = 0
    trading_days_held: int = 0
    ytd_loser: bool = False
    mark: float | None = None
    no_second_overnight: bool = False

    def __post_init__(self) -> None:
        self.symbol = self.symbol.upper().strip()
        self.chain = self.chain.strip().lower()

    def to_dict(self) -> dict[str, Any]:
        return to_plain(asdict(self))


@dataclass
class AccountState:
    equity: float
    cash: float = 0.0
    day_pnl: float = 0.0
    consecutive_stop_losses: int = 0
    pause_new_entries: bool = False
    hard_pause: bool = False
    day_trades_rolling_5: int = 0
    intraday_opens_today: int = 0
    realized_loss_symbols_ytd: set[str] = field(default_factory=set)
    stopped_today: set[str] = field(default_factory=set)
    prior_sleeve_shares: dict[str, int] = field(default_factory=dict)
    positions: list[Position] = field(default_factory=list)
    mag7_approved: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.realized_loss_symbols_ytd = {s.upper() for s in self.realized_loss_symbols_ytd}
        self.stopped_today = {s.upper() for s in self.stopped_today}
        self.mag7_approved = {s.upper() for s in self.mag7_approved}
        self.prior_sleeve_shares = {k.upper(): int(v) for k, v in self.prior_sleeve_shares.items()}


@dataclass
class RiskBreakdown:
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Evaluation:
    decision: Decision
    symbol: str
    rr: float | None
    duration: Duration | None
    reasons: list[Reason]
    vetoes: list[Reason]
    risk: RiskBreakdown | None
    intents: list[OrderIntent]
    checks: dict[str, bool]
    sector_lagging: bool
    sector_effect: str
    notes: list[str] = field(default_factory=list)
    dry_run: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "symbol": self.symbol,
            "rr": None if self.rr is None else round(self.rr, 4),
            "duration": None if self.duration is None else self.duration.value,
            "duration_label": None if self.duration is None else DURATION_LABELS[self.duration],
            "reasons": [r.to_dict() for r in self.reasons],
            "vetoes": [r.to_dict() for r in self.vetoes],
            "risk": None if self.risk is None else self.risk.to_dict(),
            "checks": dict(self.checks),
            "sector_lagging": self.sector_lagging,
            "sector_effect": self.sector_effect,
            "notes": list(self.notes),
            "dry_run": self.dry_run,
            "intents": [intent.to_dict() for intent in self.intents],
        }


@dataclass
class ScanResult:
    ranked: list[Evaluation]
    stood_down: list[dict[str, str]] = field(default_factory=list)
    note: str = "sector_rank_is_sort_only"

    def to_dict(self) -> dict[str, Any]:
        return {
            "note": self.note,
            "stood_down": list(self.stood_down),
            "ranked": [item.to_dict() for item in self.ranked],
        }
