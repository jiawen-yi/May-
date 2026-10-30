"""Hold-length tags, ladders, and the intraday unlock firewall.

Default tag is the 1–2 day swing. A new position is tagged intraday only when
``IntradayUnlock.explicit`` is true. Unlocking the tag does not relax the gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from zoneinfo import ZoneInfo

from may_trade.codes import Code
from may_trade.config import Settings
from may_trade.models import Duration, IntradayUnlock, Reason, Session

ET = ZoneInfo("America/New_York")

# Rungs are fractions of cost. YTD-loser swing-3/5 uses the 1–2 day ladder.
LADDERS: dict[Duration, tuple[float, float, float]] = {
    Duration.INTRADAY: (0.03, 0.06, 0.10),
    Duration.SWING_1_2: (0.04, 0.08, 0.12),
    Duration.SWING_3_5: (0.05, 0.10, 0.15),
}

PLANNED_DAYS = {
    Duration.INTRADAY: 0,
    Duration.SWING_1_2: 2,
    Duration.SWING_3_5: 5,
}

# Regular-session intraday entries wait until 30 minutes after the cash open.
REGULAR_ENTRY_NOT_BEFORE = time(10, 0)
# Stricter than the all-session buy window: no new intraday tag at or after 15:30 ET.
INTRADAY_ENTRY_NOT_AFTER = time(15, 30)
INTRADAY_FLAT_BY = time(15, 55)


def in_et(moment: datetime) -> datetime:
    """Naive timestamps are read as America/New_York, not as UTC."""

    if moment.tzinfo is None:
        return moment.replace(tzinfo=ET)
    return moment.astimezone(ET)


def ladder_for(duration: Duration, *, ytd_loser: bool) -> tuple[float, float, float]:
    if ytd_loser and duration == Duration.SWING_3_5:
        return LADDERS[Duration.SWING_1_2]
    return LADDERS[duration]


def planned_days(duration: Duration) -> int:
    return PLANNED_DAYS[duration]


@dataclass
class DurationResolution:
    ok: bool
    duration: Duration | None
    reasons: list[Reason] = field(default_factory=list)


def resolve_duration(
    requested: Duration | None,
    unlock: IntradayUnlock,
    *,
    as_of: datetime,
    session: Session,
    high_vol: bool,
    up_structure: bool,
    consecutive_stops: int,
    settings: Settings | None = None,
) -> DurationResolution:
    """Pick the tag that may be written on a new position.

    Returns ``duration=None`` when the requested tag is refused, so a locked
    intraday request is never relabeled as a quiet success.
    """

    del settings  # caps live in risk; the tag itself is not a size knob
    reasons: list[Reason] = []
    chosen = requested or Duration.SWING_1_2

    if chosen == Duration.INTRADAY and not unlock.explicit:
        reasons.append(
            Reason(
                Code.INTRADAY_LOCKED,
                "Intraday tag is locked. Pass IntradayUnlock(explicit=True) "
                "from an explicit user instruction. Default remains the 1–2 day swing.",
            )
        )
        return DurationResolution(False, None, reasons)

    if chosen == Duration.SWING_3_5 and (high_vol or consecutive_stops >= 1):
        reasons.append(
            Reason(
                Code.PREFER_SHORTER_HOLD,
                "High vol or a recent stop: new opens stay on the 1–2 day swing "
                "(or intraday, if unlocked), not the 3–5 day swing.",
            )
        )

    if chosen != Duration.INTRADAY and high_vol and not up_structure:
        reasons.append(
            Reason(
                Code.HIGH_VOL_NO_OVERNIGHT,
                "High vol without an upward structure does not stay overnight.",
            )
        )

    if chosen == Duration.INTRADAY:
        clock = in_et(as_of).timetz().replace(tzinfo=None)
        if clock >= INTRADAY_ENTRY_NOT_AFTER:
            reasons.append(
                Reason(
                    Code.INTRADAY_CUTOFF,
                    "No new intraday open at or after 15:30 ET. Flat by 15:55 ET.",
                )
            )
        elif session == Session.REGULAR and clock < REGULAR_ENTRY_NOT_BEFORE:
            reasons.append(
                Reason(
                    Code.INTRADAY_OPEN_DELAY,
                    "Regular-session intraday entries wait until 10:00 ET.",
                )
            )

    if reasons:
        return DurationResolution(False, None, reasons)
    return DurationResolution(True, chosen, [])
