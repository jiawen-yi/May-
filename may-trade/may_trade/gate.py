"""Setup gate: entry, structural stop, target, R:R, thesis.

A stop that is tighter than the named structure is rejected. Intraday is the
one hold that may use the tighter of that structure and half an intraday ATR,
because the hold rule says so — not because a wider structure failed R:R.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from may_trade.codes import Code
from may_trade.config import Settings
from may_trade.models import Duration, QuoteSnapshot, Reason, Side, TradePlan
from may_trade.money import PRICE_TOL, is_looser, is_tighter, long_side


@dataclass
class SetupGate:
    ok: bool
    rr: float | None
    effective_stop: float | None
    reasons: list[Reason] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def measure_rr(side: Side, entry: float, stop: float, target: float) -> float | None:
    if min(entry, stop, target) <= 0:
        return None
    if long_side(side):
        risk = entry - stop
        reward = target - entry
    elif side == Side.SHORT:
        risk = stop - entry
        reward = entry - target
    else:
        return None
    if risk <= PRICE_TOL or reward <= PRICE_TOL:
        return None
    return reward / risk


def resolve_stop(
    plan: TradePlan,
    quote: QuoteSnapshot,
    duration: Duration | None,
    settings: Settings,
) -> tuple[float | None, list[Reason], list[str]]:
    """Return the stop that R:R is allowed to use."""

    reasons: list[Reason] = []
    notes: list[str] = []
    if not plan.stop_is_structural:
        reasons.append(
            Reason(
                Code.STOP_NOT_STRUCTURAL,
                "The stop has to be the structural stop. Tightening it to clear the gate is refused.",
            )
        )
    if not plan.stop_basis or not str(plan.stop_basis).strip():
        reasons.append(
            Reason(
                Code.STOP_BASIS_MISSING,
                "Name the stop (structure, level) before the trade exists.",
            )
        )

    structural = plan.structural_stop if plan.structural_stop is not None else plan.stop

    if duration == Duration.INTRADAY:
        return _intraday_stop(plan, quote, structural, settings, reasons, notes)

    if abs(plan.stop - structural) > PRICE_TOL:
        if is_tighter(plan.side, plan.stop, structural):
            reasons.append(
                Reason(
                    Code.STOP_TIGHTENED_FOR_GATE,
                    "Structural stop was tightened. R:R has to clear on the honest stop.",
                )
            )
        elif is_looser(plan.side, plan.stop, structural):
            reasons.append(
                Reason(
                    Code.STOP_LOOSENED,
                    "Working stop is wider than the named structural stop.",
                )
            )
        else:
            reasons.append(
                Reason(Code.STOP_MISMATCH, "Working stop does not match the structural stop.")
            )
    return structural, reasons, notes


def _intraday_stop(
    plan: TradePlan,
    quote: QuoteSnapshot,
    structural: float,
    settings: Settings,
    reasons: list[Reason],
    notes: list[str],
) -> tuple[float | None, list[Reason], list[str]]:
    atr = quote.atr_intraday
    if atr is None or atr <= 0:
        reasons.append(
            Reason(
                Code.INTRADAY_ATR_REQUIRED,
                "Intraday stop is the tighter of the structural stop and 0.5× intraday ATR.",
            )
        )
        return None, reasons, notes

    if long_side(plan.side):
        atr_stop = plan.entry - settings.intraday_atr_fraction * atr
        if atr_stop >= plan.entry - PRICE_TOL:
            reasons.append(Reason(Code.STOP_GEOMETRY, "ATR stop is not below entry."))
            return None, reasons, notes
        mandated = max(structural, atr_stop)
        if mandated >= plan.entry - PRICE_TOL:
            reasons.append(Reason(Code.STOP_GEOMETRY, "Intraday stop crosses entry."))
            return None, reasons, notes
        if plan.stop > mandated + PRICE_TOL:
            reasons.append(
                Reason(
                    Code.STOP_TIGHTENED_FOR_GATE,
                    "Stop is tighter than both the structural stop and 0.5× ATR.",
                )
            )
        if plan.structural_stop is not None and plan.stop < structural - PRICE_TOL:
            reasons.append(
                Reason(Code.STOP_LOOSENED, "Stop is wider than the named structural stop.")
            )
    else:
        atr_stop = plan.entry + settings.intraday_atr_fraction * atr
        if atr_stop <= plan.entry + PRICE_TOL:
            reasons.append(Reason(Code.STOP_GEOMETRY, "ATR stop is not above entry."))
            return None, reasons, notes
        mandated = min(structural, atr_stop)
        if mandated <= plan.entry + PRICE_TOL:
            reasons.append(Reason(Code.STOP_GEOMETRY, "Intraday stop crosses entry."))
            return None, reasons, notes
        if plan.stop < mandated - PRICE_TOL:
            reasons.append(
                Reason(
                    Code.STOP_TIGHTENED_FOR_GATE,
                    "Stop is tighter than both the structural stop and 0.5× ATR.",
                )
            )
        if plan.structural_stop is not None and plan.stop > structural + PRICE_TOL:
            reasons.append(
                Reason(Code.STOP_LOOSENED, "Stop is wider than the named structural stop.")
            )

    if abs(mandated - structural) > PRICE_TOL:
        notes.append("intraday_stop_tighter_of_structure_and_half_atr")
    return mandated, reasons, notes


def evaluate_setup(
    plan: TradePlan,
    quote: QuoteSnapshot,
    duration: Duration | None,
    settings: Settings,
) -> SetupGate:
    reasons: list[Reason] = []
    notes: list[str] = []
    if not plan.thesis or not str(plan.thesis).strip():
        reasons.append(Reason(Code.THESIS_MISSING, "Thesis is required."))

    effective, stop_reasons, stop_notes = resolve_stop(plan, quote, duration, settings)
    reasons.extend(stop_reasons)
    notes.extend(stop_notes)

    rr: float | None = None
    if effective is not None and plan.side in (Side.BUY, Side.SHORT):
        rr = measure_rr(plan.side, plan.entry, effective, plan.target)
    if effective is not None and rr is None:
        reasons.append(
            Reason(
                Code.GEOMETRY,
                "Entry, stop, and target do not form a positive-risk trade.",
            )
        )
    elif rr is not None and rr < settings.rr_min - 1e-9:
        reasons.append(
            Reason(
                Code.RR_BELOW_MIN,
                f"R:R {rr:.2f} is below {settings.rr_min:.1f}.",
            )
        )
    elif effective is None and not reasons:
        reasons.append(
            Reason(
                Code.GEOMETRY,
                "Entry, stop, and target do not form a positive-risk trade.",
            )
        )

    ok = not reasons and rr is not None and rr >= settings.rr_min - 1e-9
    return SetupGate(ok, rr, effective, reasons, notes)
