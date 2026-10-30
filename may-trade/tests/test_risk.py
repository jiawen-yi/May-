import pytest

from may_trade import evaluate
from may_trade.codes import Code
from may_trade.config import Settings
from may_trade.errors import ConfigError
from may_trade.models import Decision, Duration, Position, Session

from tests.conftest import AS_OF, make_account, make_plan, make_quote, reason_codes


def _run(plan=None, quote=None, account=None, settings=None):
    return evaluate(
        plan or make_plan(),
        quote or make_quote(),
        account or make_account(),
        as_of=AS_OF,
        settings=settings,
    )


def _memory_lot() -> Position:
    return Position(
        symbol="MU",
        shares=100,
        cost=50,
        stop=25,
        target=80,
        chain="memory",
    )


def test_stack_risk_above_3pct_rejects_and_exactly_3pct_passes():
    # Open risk is $2,500. A 100-share add risks $500 and lands on 3%.
    # 101 shares push the stack through 3%.
    at_cap = _run(make_plan(shares=100), account=make_account(positions=[_memory_lot()]))
    assert at_cap.decision == Decision.PASS
    assert Code.STACK_RISK not in reason_codes(at_cap)
    assert at_cap.risk is not None
    assert at_cap.risk.stack_risk == 3000

    over = _run(make_plan(shares=101), account=make_account(positions=[_memory_lot()]))
    assert over.decision == Decision.FAIL
    assert Code.STACK_RISK in reason_codes(over)
    assert over.intents == []


def test_daily_loss_halt_at_1_5pct():
    halted = _run(account=make_account(day_pnl=-1500))
    assert halted.decision == Decision.FAIL
    assert Code.DAILY_LOSS_HALT in reason_codes(halted)

    still_open = _run(account=make_account(day_pnl=-1499))
    assert still_open.decision == Decision.PASS


def test_negative_cash_does_not_veto():
    result = _run(account=make_account(cash=-500))
    assert result.decision == Decision.PASS
    assert "negative_cash_is_not_a_veto" in result.notes


def test_same_day_stop_cooldown_and_ytd_loser_rebuy():
    cooled = _run(account=make_account(stopped_today={"ANET"}))
    assert Code.STOP_COOLDOWN in reason_codes(cooled)

    # A realized loss this year is not a 30-day ban. Size is the small rebuy cap.
    rebuy = _run(
        make_plan(shares=1),
        account=make_account(
            realized_loss_symbols_ytd={"ANET"},
            prior_sleeve_shares={"ANET": 10},
        ),
    )
    assert rebuy.decision == Decision.PASS

    too_big = _run(
        make_plan(shares=2),
        account=make_account(
            realized_loss_symbols_ytd={"ANET"},
            prior_sleeve_shares={"ANET": 10},
        ),
    )
    assert Code.WASH_REBUY_SIZE in reason_codes(too_big)


def test_chain_limit_is_two_names():
    full = make_account(
        positions=[
            Position("CIEN", 10, 80, 75, 100, "optics"),
            Position("COHR", 10, 70, 65, 90, "optics"),
        ]
    )
    blocked = _run(account=full)
    assert Code.CHAIN_FULL in reason_codes(blocked)

    add = _run(make_plan(symbol="CIEN", shares=5, is_add=True), account=full)
    assert add.decision == Decision.PASS
    assert Code.CHAIN_FULL not in reason_codes(add)


def test_two_consecutive_stops_pause_new_entries():
    result = _run(account=make_account(consecutive_stop_losses=2))
    assert Code.LOSS_BRAKE in reason_codes(result)
    assert result.intents == []


def test_soft_tape_shrinks_auto_size_and_does_not_fail_the_gate():
    sized = _run(make_plan(shares=None), make_quote(soft_tape=True))
    assert sized.decision == Decision.PASS
    assert sized.intents[0].quantity == 225

    full = _run(make_plan(shares=None))
    assert full.intents[0].quantity == 300


def test_extended_session_uses_half_size_when_the_spread_is_tight():
    result = _run(
        make_plan(shares=50),
        make_quote(session=Session.EXTENDED, spread_pct=0.004),
    )
    assert result.decision == Decision.PASS
    assert result.intents[0].metadata["session_tag"] == "非正规时段"

    too_big = _run(
        make_plan(shares=200),
        make_quote(session=Session.EXTENDED, spread_pct=0.004),
    )
    assert too_big.decision == Decision.FAIL
    assert Code.PER_TRADE_RISK in reason_codes(too_big)


def test_name_concentration_above_40pct_rejects():
    # Tight structural stop so the 2% risk budget is not the binding cap.
    over = _run(make_plan(entry=100, stop=99.5, target=101, shares=401))
    assert Code.CONCENTRATION in reason_codes(over)
    at_cap = _run(make_plan(entry=100, stop=99.5, target=101, shares=400))
    assert at_cap.decision == Decision.PASS


def test_config_cannot_loosen_principles():
    with pytest.raises(ConfigError):
        Settings(rr_min=1.5)
    with pytest.raises(ConfigError):
        Settings(rr_min=2.5)
    with pytest.raises(ConfigError):
        Settings(stack_risk_max_pct=0.04)
    tighter = Settings(stack_risk_max_pct=0.02)
    assert tighter.stack_risk_max_pct == 0.02


def test_loss_brake_day_still_blocks_an_otherwise_clean_plan():
    result = _run(account=make_account(pause_new_entries=True))
    assert result.decision == Decision.FAIL
    assert Code.LOSS_BRAKE in reason_codes(result)
    assert result.duration == Duration.SWING_1_2
