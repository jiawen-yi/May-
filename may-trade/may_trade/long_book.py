"""Long-horizon research book.

Proposals never become sleeve plans, never enter the setup gate, and never
enter the hourly scan. Short-term tape, stop ratchets, and the sleeve risk
engine do not close a long-book idea.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from may_trade.config import Settings
from may_trade.errors import FirewallError
from may_trade.models import InstrumentKind
from may_trade.universe import instrument_allowed

FIREWALL = "research_only_does_not_enter_sleeve_setup_gate_or_hourly_scan"

# Realized sleeve profits, when large enough to bother, are proposed into
# these long-book weights. They are not sleeve OCO orders.
PROFIT_WEIGHTS = (("QQQM", 0.30), ("SPYM", 0.30), ("SCHD", 0.40))


class LongAction:
    HOLD = "HOLD"
    ADD = "ADD"
    TRIM = "TRIM"
    EXIT = "EXIT"
    WATCH = "WATCH"


@dataclass
class LongHolding:
    symbol: str
    sector: str
    weight: float

    def __post_init__(self) -> None:
        self.symbol = self.symbol.upper().strip()
        self.sector = self.sector.strip().lower()


@dataclass
class LongProposal:
    symbol: str
    action: str
    thesis: str
    red_lines: list[str]
    valuation_anchor: str
    role: str
    size_pct_of_long_book: float
    sector: str
    next_review: date
    accepted: bool
    reasons: list[str] = field(default_factory=list)
    sleeve_executable: bool = False
    enters_setup_gate: bool = False
    enters_hourly_scan: bool = False
    attach_short_oco: bool = False
    firewall: str = FIREWALL

    def __post_init__(self) -> None:
        self.symbol = self.symbol.upper().strip()
        if self.sleeve_executable or self.enters_setup_gate or self.enters_hourly_scan or self.attach_short_oco:
            raise FirewallError(
                "A long-book proposal cannot be marked executable on the sleeve path."
            )
        if self.firewall != FIREWALL:
            raise FirewallError("Long-book firewall text cannot be cleared.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "book": "long",
            "symbol": self.symbol,
            "action": self.action,
            "thesis": self.thesis,
            "red_lines": list(self.red_lines),
            "valuation_anchor": self.valuation_anchor,
            "role": self.role,
            "size_pct_of_long_book": self.size_pct_of_long_book,
            "sector": self.sector,
            "next_review": self.next_review.isoformat(),
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "sleeve_executable": False,
            "enters_setup_gate": False,
            "enters_hourly_scan": False,
            "attach_short_oco": False,
            "firewall": self.firewall,
        }


@dataclass
class ProfitSweep:
    amount: float
    legs: list[dict[str, float | str]]
    book: str = "long"
    oco: bool = False
    sleeve_executable: bool = False
    firewall: str = FIREWALL

    def __post_init__(self) -> None:
        if self.sleeve_executable or self.oco:
            raise FirewallError("Realized-profit splits are long-book proposals, not sleeve orders.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "book": self.book,
            "amount": round(self.amount, 2),
            "legs": list(self.legs),
            "oco": False,
            "sleeve_executable": False,
            "firewall": self.firewall,
        }


def propose(
    *,
    symbol: str,
    action: str,
    thesis: str,
    red_lines: list[str],
    valuation_anchor: str,
    role: str,
    size_pct: float,
    sector: str,
    next_review: date,
    instrument: InstrumentKind = InstrumentKind.COMMON_STOCK,
    holdings: list[LongHolding] | None = None,
    settings: Settings | None = None,
) -> LongProposal:
    """Size is the resulting weight of this name inside the long book, not a sleeve risk."""

    settings = settings or Settings()
    reasons: list[str] = []
    banned = instrument_allowed(symbol, instrument)
    if banned is not None:
        reasons.append(banned.message)
    if not thesis or not thesis.strip():
        reasons.append("Long-book thesis is required.")
    if not valuation_anchor or not valuation_anchor.strip():
        reasons.append("A valuation anchor is required.")
    if size_pct < 0:
        reasons.append("Weight cannot be negative.")
    if size_pct > settings.long_name_cap_pct + 1e-12:
        reasons.append("Single-name weight cannot exceed 15% of the long book.")
    sector_key = sector.strip().lower()
    others = 0.0
    for holding in holdings or []:
        if holding.sector == sector_key and holding.symbol != symbol.upper().strip():
            others += holding.weight
    if others + max(size_pct, 0.0) > settings.long_sector_cap_pct + 1e-12:
        reasons.append("Sector weight cannot exceed 35% of the long book.")
    return LongProposal(
        symbol=symbol,
        action=action,
        thesis=thesis.strip(),
        red_lines=list(red_lines),
        valuation_anchor=valuation_anchor.strip(),
        role=role,
        size_pct_of_long_book=size_pct,
        sector=sector_key,
        next_review=next_review,
        accepted=not reasons,
        reasons=reasons,
    )


def as_sleeve_plan(proposal: object) -> None:
    """Long-book output is not a sleeve input. This always refuses."""

    raise FirewallError(
        f"{type(proposal).__name__} stays in the research book. Long-book proposals do not "
        "become sleeve plans, do not enter Setup Gate, and do not enter the hourly scan."
    )


def sleeve_candidates(proposals: object) -> None:
    raise FirewallError(
        f"The long book cannot feed the sleeve auto-exec path ({type(proposals).__name__})."
    )


def allocate_realized_profit(amount: float, settings: Settings | None = None) -> ProfitSweep | None:
    """Propose a long-book split of a realized sleeve gain. Returns None under the dust line."""

    settings = settings or Settings()
    if amount <= settings.min_sweep_dollars:
        return None
    legs = [
        {"symbol": symbol, "weight": weight, "amount": round(amount * weight, 2)}
        for symbol, weight in PROFIT_WEIGHTS
    ]
    return ProfitSweep(amount=amount, legs=legs)
