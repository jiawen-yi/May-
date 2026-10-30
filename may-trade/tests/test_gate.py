from datetime import datetime

from may_trade import evaluate
from may_trade.codes import Code
from may_trade.duration import ET
from may_trade.models import Decision, Duration, IntradayUnlock, InstrumentKind, Side

from tests.conftest import AS_OF, make_account, make_plan, make_quote, reason_codes


def _run(plan=None, quote=None, account=None, unlock=None, as_of=None):
    return evaluate(
        plan or make_plan(),
        quote or make_quote(),
        account or make_account(),
        unlock=unlock or IntradayUnlock(explicit=False),
        as_of=as_of or AS_OF,
    )


def test_rr_at_two_passes_and_below_two_fails():
    passing = _run(make_plan(entry=100, stop=90, target=120, shares=10))
    assert passing.decision == Decision.PASS
    assert passing.rr == 2.0
    assert passing.intents

    failing = _run(make_plan(entry=100, stop=90, target=119.99, shares=10))
    assert failing.decision == Decision.FAIL
    assert Code.RR_BELOW_MIN in reason_codes(failing)
    assert failing.intents == []
    assert failing.vetoes


def test_rr_fail_does_not_emit_an_order():
    result = _run(make_plan(entry=100, stop=90, target=105, shares=10))
    assert result.decision == Decision.FAIL
    assert result.rr == 0.5
    assert result.intents == []


def test_structural_stop_tightened_to_clear_the_gate_is_refused():
    # Honest stop 90 pays 2.0R to 120. The tighter stop 95 would print 4R.
    result = _run(
        make_plan(entry=100, stop=95, structural_stop=90, target=120, shares=10)
    )
    assert result.decision == Decision.FAIL
    assert Code.STOP_TIGHTENED_FOR_GATE in reason_codes(result)
    assert result.rr == 2.0
    assert result.intents == []


def test_pass_emits_limit_entry_then_matching_oco():
    result = _run()
    assert result.decision == Decision.PASS
    assert result.duration == Duration.SWING_1_2
    assert [item.intent_type for item in result.intents] == ["entry", "oco"]
    entry, oco = result.intents
    assert entry.order_type == "limit"
    assert entry.limit_price == 100
    assert entry.quantity == 50
    assert entry.dry_run is True
    assert oco.quantity == entry.quantity
    assert oco.group_id == entry.group_id
    assert oco.trigger == "on_entry_fill"
    assert oco.time_in_force == "gtc"
    legs = {leg.kind: leg for leg in oco.legs}
    assert legs["stop"].stop_price == 95
    assert legs["limit"].limit_price == 112
    assert entry.metadata["duration"] == "swing_1_2"
    assert entry.metadata["duration_label"] == "短波"


def test_missing_thesis_fails():
    result = _run(make_plan(thesis="  "))
    assert result.decision == Decision.FAIL
    assert Code.THESIS_MISSING in reason_codes(result)


def test_options_and_leveraged_products_are_banned():
    option = _run(make_plan(instrument=InstrumentKind.OPTION))
    geared = _run(make_plan(symbol="SOXL", instrument=InstrumentKind.COMMON_STOCK))
    labeled = _run(make_plan(symbol="QQQ", instrument=InstrumentKind.LEVERAGED_ETF))
    for result in (option, geared, labeled):
        assert result.decision == Decision.FAIL
        assert Code.INSTRUMENT_BANNED in reason_codes(result)
        assert result.intents == []


def test_short_passes_on_the_same_rr_floor_and_buys_to_cover():
    result = _run(make_plan(side=Side.SHORT, entry=100, stop=110, target=80, shares=10))
    assert result.decision == Decision.PASS
    assert result.rr == 2.0
    assert [item.side for item in result.intents] == ["short", "buy"]
    assert result.intents[1].legs[0].stop_price == 110


def test_mag7_passes_the_gate_but_is_not_routable_until_acked():
    blocked = _run(make_plan(symbol="NVDA", chain="ai_compute"))
    assert blocked.decision == Decision.PASS
    assert blocked.intents[0].routable is False
    assert blocked.intents[0].requires_user_ack is True
    acked = _run(
        make_plan(symbol="NVDA", chain="ai_compute"),
        account=make_account(mag7_approved={"NVDA"}),
    )
    assert acked.intents[0].routable is True


def test_wait_pullback_rests_a_limit_at_the_zone():
    result = _run(make_plan(entry_high=101), make_quote(last=103))
    assert result.decision == Decision.WAIT_PULLBACK
    assert result.intents[0].limit_price == 100
    assert result.intents[0].order_type == "limit"
