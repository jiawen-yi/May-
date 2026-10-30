from dataclasses import replace
from datetime import datetime

import pytest

from may_trade.duration import ET
from may_trade.errors import PolicyBreach
from may_trade.lifecycle import manage_position, move_stop
from may_trade.models import Book, Duration, Position, Side

from tests.conftest import AS_OF


def lot(**overrides) -> Position:
    base = dict(
        symbol="ANET",
        shares=4,
        cost=100.0,
        stop=90.0,
        target=130.0,
        chain="optics",
        side=Side.BUY,
        duration=Duration.SWING_3_5,
        has_oco=True,
        oco_id="old",
        ladder_stage=0,
        trading_days_held=1,
    )
    base.update(overrides)
    return Position(**base)


def test_long_stop_only_moves_up():
    with pytest.raises(PolicyBreach, match="only move up"):
        move_stop(lot(), 89)
    assert move_stop(lot(), 96).stop == 96


def test_short_stop_only_moves_down():
    position = lot(side=Side.SHORT, stop=110, cost=100, target=80)
    with pytest.raises(PolicyBreach, match="only move down"):
        move_stop(position, 112)
    assert move_stop(position, 105).stop == 105


def test_ladder_sells_one_share_of_a_four_share_lot_and_rearms_oco():
    original = lot()
    result = manage_position(original, 105, AS_OF)
    assert original.shares == 4
    assert result.action == "ladder"
    assert result.position.shares == 3
    assert result.position.stop == 100
    kinds = [item.intent_type for item in result.intents]
    assert kinds == ["cancel", "oco", "trim"]
    assert result.intents[1].quantity == 3
    assert result.intents[2].quantity == 1
    assert result.intents[1].legs[0].stop_price == 100


def test_intraday_flattens_at_1555_et():
    position = lot(duration=Duration.INTRADAY, trading_days_held=0, stop=95)
    flat = manage_position(position, 101, datetime(2026, 10, 23, 15, 55, tzinfo=ET))
    assert flat.action == "flatten"
    assert flat.position.shares == 0
    assert any(item.purpose == "session_flat" for item in flat.intents)

    held = manage_position(position, 100, datetime(2026, 10, 23, 15, 54, tzinfo=ET))
    assert held.action == "hold"


def test_time_stop_ratchets_then_flattens():
    breakeven = manage_position(
        lot(duration=Duration.SWING_1_2, trading_days_held=3),
        100,
        AS_OF,
    )
    assert breakeven.action == "time_stop_breakeven"
    assert breakeven.position.stop == 100

    flattened = manage_position(
        lot(duration=Duration.SWING_1_2, trading_days_held=4),
        100,
        AS_OF,
    )
    assert flattened.action == "flatten"


def test_ytd_loser_uses_the_earlier_ladder_and_a_shallow_gain_goes_to_cost():
    earlier = manage_position(lot(ytd_loser=True), 104.5, AS_OF)
    assert earlier.action == "ladder"

    shallow = manage_position(
        lot(duration=Duration.SWING_1_2, ytd_loser=True),
        103.5,
        AS_OF,
    )
    assert shallow.action == "loser_breakeven"
    assert shallow.position.stop == 100
    assert all(item.intent_type != "trim" for item in shallow.intents)


def test_missing_oco_is_replaced_before_anything_else():
    result = manage_position(lot(has_oco=False, oco_id=None), 100, AS_OF)
    assert result.action == "protect"
    assert result.intents[0].intent_type == "oco"
    assert result.position.has_oco is True


def test_retag_from_an_overnight_intraday_cannot_stay_a_second_night():
    retag = manage_position(
        lot(duration=Duration.INTRADAY, trading_days_held=1, stop=97, target=110),
        101,
        AS_OF,
    )
    assert retag.action == "retag"
    assert retag.position.duration == Duration.SWING_1_2
    assert retag.position.no_second_overnight is True
    assert retag.position.target == 104

    flattened = manage_position(replace(retag.position, trading_days_held=2), 101, AS_OF)
    assert flattened.action == "flatten"
    assert any(item.purpose == "second_overnight" for item in flattened.intents)


def test_long_book_lot_is_not_run_through_the_sleeve_ladder():
    result = manage_position(lot(book=Book.LONG, sleeve=False), 130, AS_OF)
    assert result.action == "skip"
    assert result.intents == []
