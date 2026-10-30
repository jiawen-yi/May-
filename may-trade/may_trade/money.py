"""Cent-level comparisons so risk caps are not tripped by binary float dust."""

from __future__ import annotations

PRICE_TOL = 1e-4


def cents(amount: float) -> int:
    return int(round(float(amount) * 100))


def exceeds(amount: float, cap: float) -> bool:
    """True when amount is strictly above cap at cent precision."""

    return cents(amount) > cents(cap)


def long_side(side: object) -> bool:
    value = getattr(side, "value", side)
    return value in ("buy", "long")


def is_tighter(side: object, new: float, old: float) -> bool:
    """A long stop is tighter when it moves up; a short stop when it moves down."""

    if long_side(side):
        return new > old + PRICE_TOL
    return new < old - PRICE_TOL


def is_looser(side: object, new: float, old: float) -> bool:
    if long_side(side):
        return new < old - PRICE_TOL
    return new > old + PRICE_TOL


def ratchet(side: object, old: float, proposed: float) -> float:
    """Return the tighter of the two stops. Never loosens."""

    if long_side(side):
        return max(old, proposed)
    return min(old, proposed)
