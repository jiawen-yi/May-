"""Load mock quotes and plans from JSON fixtures. No market-data calls."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from may_trade.errors import FixtureError
from may_trade.models import (
    AccountState,
    Book,
    Duration,
    InstrumentKind,
    IntradayUnlock,
    Position,
    QuoteSnapshot,
    Session,
    Side,
    TradePlan,
)

_PLAN_KEYS = {
    "symbol",
    "side",
    "entry",
    "stop",
    "target",
    "thesis",
    "chain",
    "instrument",
    "duration",
    "shares",
    "stop_basis",
    "stop_is_structural",
    "structural_stop",
    "entry_low",
    "entry_high",
    "is_add",
    "event_planned",
    "book",
    "mag7_approved",
}
_QUOTE_KEYS = {
    "last",
    "day_change_pct",
    "session",
    "ma10",
    "rsi6",
    "high_52w",
    "spread_pct",
    "atr_intraday",
    "has_new_catalyst",
    "benchmark_break_same_direction",
    "sector",
    "sector_lagging",
    "sector_score",
    "soft_tape",
    "high_vol",
    "up_structure",
    "event_in_hold_window",
    "round_trip_cost",
    "round_trip_cost_per_share",
}
_ACCOUNT_KEYS = {
    "equity",
    "cash",
    "day_pnl",
    "consecutive_stop_losses",
    "pause_new_entries",
    "hard_pause",
    "day_trades_rolling_5",
    "intraday_opens_today",
    "realized_loss_symbols_ytd",
    "stopped_today",
    "prior_sleeve_shares",
    "positions",
    "mag7_approved",
}
_POSITION_KEYS = {
    "symbol",
    "shares",
    "cost",
    "stop",
    "target",
    "chain",
    "side",
    "duration",
    "sleeve",
    "book",
    "oco_id",
    "has_oco",
    "ladder_stage",
    "trading_days_held",
    "ytd_loser",
    "mark",
    "no_second_overnight",
}
_UNLOCK_KEYS = {"explicit", "phrase"}


def load_evaluation_fixture(
    path: str | Path,
) -> tuple[TradePlan, QuoteSnapshot, AccountState, IntradayUnlock, datetime]:
    data = _read(path)
    _unknown(data, {"plan", "quote", "account", "unlock", "as_of"}, "fixture")
    if "plan" not in data or "quote" not in data or "as_of" not in data:
        raise FixtureError("Fixture needs plan, quote, and as_of.")
    return (
        _plan(data["plan"]),
        _quote(data["quote"]),
        _account(data.get("account") or {}),
        _unlock(data.get("unlock") or {}),
        _time(data["as_of"]),
    )


def load_scan_fixture(
    path: str | Path,
) -> tuple[list[tuple[TradePlan, QuoteSnapshot]], AccountState, IntradayUnlock, datetime]:
    data = _read(path)
    _unknown(data, {"candidates", "account", "unlock", "as_of"}, "scan fixture")
    if "candidates" not in data or "as_of" not in data:
        raise FixtureError("Scan fixture needs candidates and as_of.")
    if not isinstance(data["candidates"], list) or not data["candidates"]:
        raise FixtureError("Scan fixture candidates must be a non-empty list.")
    pairs: list[tuple[TradePlan, QuoteSnapshot]] = []
    for index, row in enumerate(data["candidates"]):
        if not isinstance(row, dict):
            raise FixtureError(f"Candidate {index} must be an object.")
        _unknown(row, {"plan", "quote"}, f"candidate {index}")
        pairs.append((_plan(row.get("plan")), _quote(row.get("quote"))))
    return pairs, _account(data.get("account") or {}), _unlock(data.get("unlock") or {}), _time(data["as_of"])


def _read(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.is_file():
        raise FixtureError(f"Fixture not found: {file_path}")
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FixtureError(f"Invalid JSON in {file_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise FixtureError("Fixture root must be an object.")
    return data


def _plan(raw: Any) -> TradePlan:
    data = _object(raw, "plan")
    _unknown(data, _PLAN_KEYS, "plan")
    for key in ("symbol", "side", "entry", "stop", "target", "thesis", "chain", "instrument"):
        if key not in data:
            raise FixtureError(f"plan.{key} is required.")
    shares = data.get("shares", None)
    return TradePlan(
        symbol=str(data["symbol"]),
        side=_enum(Side, data["side"], "plan.side"),
        entry=_number(data["entry"], "plan.entry"),
        stop=_number(data["stop"], "plan.stop"),
        target=_number(data["target"], "plan.target"),
        thesis=str(data["thesis"]),
        chain=str(data["chain"]),
        instrument=_enum(InstrumentKind, data["instrument"], "plan.instrument"),
        duration=_enum(Duration, data.get("duration", Duration.SWING_1_2.value), "plan.duration"),
        shares=None if shares is None else _int(shares, "plan.shares"),
        stop_basis=str(data.get("stop_basis", "")),
        stop_is_structural=_bool(data.get("stop_is_structural", True), "plan.stop_is_structural"),
        structural_stop=_optional_number(data.get("structural_stop"), "plan.structural_stop"),
        entry_low=_optional_number(data.get("entry_low"), "plan.entry_low"),
        entry_high=_optional_number(data.get("entry_high"), "plan.entry_high"),
        is_add=_bool(data.get("is_add", False), "plan.is_add"),
        event_planned=_bool(data.get("event_planned", False), "plan.event_planned"),
        book=_enum(Book, data.get("book", Book.SLEEVE.value), "plan.book"),
        mag7_approved=_bool(data.get("mag7_approved", False), "plan.mag7_approved"),
    )


def _quote(raw: Any) -> QuoteSnapshot:
    data = _object(raw, "quote")
    _unknown(data, _QUOTE_KEYS, "quote")
    for key in ("last", "day_change_pct"):
        if key not in data:
            raise FixtureError(f"quote.{key} is required.")
    return QuoteSnapshot(
        last=_number(data["last"], "quote.last"),
        day_change_pct=_number(data["day_change_pct"], "quote.day_change_pct"),
        session=_enum(Session, data.get("session", Session.REGULAR.value), "quote.session"),
        ma10=_optional_number(data.get("ma10"), "quote.ma10"),
        rsi6=_optional_number(data.get("rsi6"), "quote.rsi6"),
        high_52w=_optional_number(data.get("high_52w"), "quote.high_52w"),
        spread_pct=_optional_number(data.get("spread_pct"), "quote.spread_pct"),
        atr_intraday=_optional_number(data.get("atr_intraday"), "quote.atr_intraday"),
        has_new_catalyst=_bool(data.get("has_new_catalyst", False), "quote.has_new_catalyst"),
        benchmark_break_same_direction=_bool(
            data.get("benchmark_break_same_direction", False),
            "quote.benchmark_break_same_direction",
        ),
        sector=None if data.get("sector") is None else str(data["sector"]),
        sector_lagging=_bool(data.get("sector_lagging", False), "quote.sector_lagging"),
        sector_score=_number(data.get("sector_score", 0), "quote.sector_score"),
        soft_tape=_bool(data.get("soft_tape", False), "quote.soft_tape"),
        high_vol=_bool(data.get("high_vol", False), "quote.high_vol"),
        up_structure=_bool(data.get("up_structure", True), "quote.up_structure"),
        event_in_hold_window=_bool(data.get("event_in_hold_window", False), "quote.event_in_hold_window"),
        round_trip_cost=_optional_number(data.get("round_trip_cost"), "quote.round_trip_cost"),
        round_trip_cost_per_share=_optional_number(
            data.get("round_trip_cost_per_share"), "quote.round_trip_cost_per_share"
        ),
    )


def _account(raw: Any) -> AccountState:
    data = _object(raw, "account")
    _unknown(data, _ACCOUNT_KEYS, "account")
    if "equity" not in data:
        raise FixtureError("account.equity is required.")
    positions_raw = data.get("positions") or []
    if not isinstance(positions_raw, list):
        raise FixtureError("account.positions must be a list.")
    prior = data.get("prior_sleeve_shares") or {}
    if not isinstance(prior, dict):
        raise FixtureError("account.prior_sleeve_shares must be an object.")
    return AccountState(
        equity=_number(data["equity"], "account.equity"),
        cash=_number(data.get("cash", 0), "account.cash"),
        day_pnl=_number(data.get("day_pnl", 0), "account.day_pnl"),
        consecutive_stop_losses=_int(data.get("consecutive_stop_losses", 0), "account.consecutive_stop_losses"),
        pause_new_entries=_bool(data.get("pause_new_entries", False), "account.pause_new_entries"),
        hard_pause=_bool(data.get("hard_pause", False), "account.hard_pause"),
        day_trades_rolling_5=_int(data.get("day_trades_rolling_5", 0), "account.day_trades_rolling_5"),
        intraday_opens_today=_int(data.get("intraday_opens_today", 0), "account.intraday_opens_today"),
        realized_loss_symbols_ytd={str(item).upper() for item in _list(data, "realized_loss_symbols_ytd")},
        stopped_today={str(item).upper() for item in _list(data, "stopped_today")},
        prior_sleeve_shares={str(key).upper(): _int(value, "prior_sleeve_shares") for key, value in prior.items()},
        positions=[_position(item) for item in positions_raw],
        mag7_approved={str(item).upper() for item in _list(data, "mag7_approved")},
    )


def _position(raw: Any) -> Position:
    data = _object(raw, "position")
    _unknown(data, _POSITION_KEYS, "position")
    for key in ("symbol", "shares", "cost", "stop", "target", "chain"):
        if key not in data:
            raise FixtureError(f"position.{key} is required.")
    return Position(
        symbol=str(data["symbol"]),
        shares=_int(data["shares"], "position.shares"),
        cost=_number(data["cost"], "position.cost"),
        stop=_number(data["stop"], "position.stop"),
        target=_number(data["target"], "position.target"),
        chain=str(data["chain"]),
        side=_enum(Side, data.get("side", Side.BUY.value), "position.side"),
        duration=_enum(Duration, data.get("duration", Duration.SWING_1_2.value), "position.duration"),
        sleeve=_bool(data.get("sleeve", True), "position.sleeve"),
        book=_enum(Book, data.get("book", Book.SLEEVE.value), "position.book"),
        oco_id=None if data.get("oco_id") is None else str(data["oco_id"]),
        has_oco=_bool(data.get("has_oco", True), "position.has_oco"),
        ladder_stage=_int(data.get("ladder_stage", 0), "position.ladder_stage"),
        trading_days_held=_int(data.get("trading_days_held", 0), "position.trading_days_held"),
        ytd_loser=_bool(data.get("ytd_loser", False), "position.ytd_loser"),
        mark=_optional_number(data.get("mark"), "position.mark"),
        no_second_overnight=_bool(data.get("no_second_overnight", False), "position.no_second_overnight"),
    )


def _unlock(raw: Any) -> IntradayUnlock:
    data = _object(raw, "unlock")
    _unknown(data, _UNLOCK_KEYS, "unlock")
    phrase = data.get("phrase")
    return IntradayUnlock(
        explicit=_bool(data.get("explicit", False), "unlock.explicit"),
        phrase=None if phrase is None else str(phrase),
    )


def _time(raw: Any) -> datetime:
    if not isinstance(raw, str) or not raw.strip():
        raise FixtureError("as_of must be an ISO timestamp.")
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise FixtureError(f"as_of is not an ISO timestamp: {raw}") from exc


def _object(raw: Any, label: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise FixtureError(f"{label} must be an object.")
    return raw


def _unknown(data: dict[str, Any], allowed: set[str], label: str) -> None:
    extra = set(data) - allowed
    if extra:
        raise FixtureError(f"Unknown {label} keys: {sorted(extra)}")


def _list(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key) or []
    if not isinstance(value, list):
        raise FixtureError(f"{key} must be a list.")
    return value


def _enum(kind: type, raw: Any, label: str):
    try:
        return kind(str(raw))
    except ValueError as exc:
        raise FixtureError(f"{label} has an unknown value {raw!r}.") from exc


def _number(raw: Any, label: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise FixtureError(f"{label} must be a number.")
    return float(raw)


def _optional_number(raw: Any, label: str) -> float | None:
    if raw is None:
        return None
    return _number(raw, label)


def _int(raw: Any, label: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise FixtureError(f"{label} must be an integer.")
    return raw


def _bool(raw: Any, label: str) -> bool:
    if not isinstance(raw, bool):
        raise FixtureError(f"{label} must be a boolean.")
    return raw
