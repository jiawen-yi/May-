from may_trade import evaluate
from may_trade.codes import Code
from may_trade.models import Decision, IntradayUnlock, Session

from tests.conftest import AS_OF, make_account, make_plan, make_quote, reason_codes


def _run(**quote_kw):
    return evaluate(
        make_plan(),
        make_quote(**quote_kw),
        make_account(),
        unlock=IntradayUnlock(explicit=False),
        as_of=AS_OF,
    )


def test_day_down_over_3pct_vetoes_and_exactly_3pct_does_not():
    banned = _run(day_change_pct=-0.031)
    assert banned.decision == Decision.FAIL
    assert Code.DAY_DOWN in [item.code for item in banned.vetoes]
    assert banned.intents == []

    allowed = _run(day_change_pct=-0.03)
    assert allowed.decision == Decision.PASS
    assert Code.DAY_DOWN not in reason_codes(allowed)


def test_chase_needs_both_ma10_extension_and_rsi():
    chased = evaluate(
        make_plan(entry=110, stop=100, target=130, shares=10),
        make_quote(last=110, ma10=100, rsi6=85, high_52w=200),
        make_account(),
        as_of=AS_OF,
    )
    assert chased.decision == Decision.FAIL
    assert Code.CHASE_EXTENDED in reason_codes(chased)

    extended_but_rsi_cool = evaluate(
        make_plan(entry=110, stop=100, target=130, shares=10),
        make_quote(last=110, ma10=100, rsi6=70, high_52w=200),
        make_account(),
        as_of=AS_OF,
    )
    assert extended_but_rsi_cool.decision == Decision.PASS


def test_near_52w_high_without_catalyst_vetoes():
    result = evaluate(
        make_plan(entry=98, stop=90, target=114, shares=10),
        make_quote(last=98, ma10=97, rsi6=60, high_52w=100, has_new_catalyst=False),
        make_account(),
        as_of=AS_OF,
    )
    assert Code.NEAR_52W_HIGH in reason_codes(result)

    with_catalyst = evaluate(
        make_plan(entry=98, stop=90, target=114, shares=10),
        make_quote(last=98, ma10=97, rsi6=60, high_52w=100, has_new_catalyst=True),
        make_account(),
        as_of=AS_OF,
    )
    assert with_catalyst.decision == Decision.PASS


def test_extended_spread_above_half_percent_vetoes():
    wide = _run(session=Session.EXTENDED, spread_pct=0.006)
    assert Code.EXTENDED_SPREAD in reason_codes(wide)

    regular = _run(session=Session.REGULAR, spread_pct=0.006)
    assert Code.EXTENDED_SPREAD not in reason_codes(regular)
    assert regular.decision == Decision.PASS


def test_benchmark_break_in_the_same_direction_vetoes():
    result = _run(benchmark_break_same_direction=True)
    assert result.decision == Decision.FAIL
    assert Code.BENCHMARK_SAME_DIRECTION in reason_codes(result)


def test_round_trip_cost_at_one_fifth_of_profit_vetoes():
    # 50 shares, $12 of reward = $600 profit. One fifth is $120.
    banned = _run(round_trip_cost=120)
    assert banned.decision == Decision.FAIL
    assert Code.ROUND_TRIP_COST in reason_codes(banned)

    allowed = _run(round_trip_cost=119)
    assert allowed.decision == Decision.PASS


def test_lagging_sector_does_not_veto_a_pass():
    result = _run(sector_lagging=True, sector_score=0.1)
    assert result.decision == Decision.PASS
    assert result.sector_effect == "sort_only"
    assert "lagging_sector_did_not_change_the_gate" in result.notes


def test_stale_quote_is_not_a_signal():
    result = _run(ma10=None)
    assert result.decision == Decision.FAIL
    assert Code.STALE_QUOTE in reason_codes(result)
