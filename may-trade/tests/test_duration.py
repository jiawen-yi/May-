from datetime import datetime

from may_trade import evaluate
from may_trade.codes import Code
from may_trade.duration import ET, resolve_duration
from may_trade.models import Decision, Duration, IntradayUnlock, Session

from tests.conftest import AS_OF, make_account, make_plan, make_quote, reason_codes


def test_default_duration_is_the_two_day_swing():
    resolved = resolve_duration(
        None,
        IntradayUnlock(explicit=False),
        as_of=AS_OF,
        session=Session.REGULAR,
        high_vol=False,
        up_structure=True,
        consecutive_stops=0,
    )
    assert resolved.ok
    assert resolved.duration == Duration.SWING_1_2


def test_intraday_unlock_false_cannot_tag_intraday():
    result = evaluate(
        make_plan(duration=Duration.INTRADAY),
        make_quote(),
        make_account(),
        unlock=IntradayUnlock(explicit=False),
        as_of=AS_OF,
    )
    assert result.decision == Decision.FAIL
    assert result.duration is None
    assert result.intents == []
    assert Code.INTRADAY_LOCKED in [item.code for item in result.vetoes]
    payload = result.to_dict()
    assert payload["duration"] is None
    assert payload["duration_label"] is None
    assert payload["intents"] == []


def test_explicit_unlock_tags_intraday_and_uses_half_atr_stop():
    result = evaluate(
        make_plan(duration=Duration.INTRADAY),
        make_quote(atr_intraday=4),
        make_account(),
        unlock=IntradayUnlock(explicit=True, phrase="flat by the close"),
        as_of=AS_OF,
    )
    assert result.decision == Decision.PASS
    assert result.duration == Duration.INTRADAY
    assert result.intents[0].metadata["duration"] == "intraday"
    assert result.intents[0].metadata["duration_label"] == "日内"
    assert result.intents[0].metadata["ladder"] == [0.03, 0.06, 0.1]
    stop = next(leg.stop_price for leg in result.intents[1].legs if leg.kind == "stop")
    # Structural stop is 95; 0.5 × ATR is $2, so the working stop is 98.
    assert stop == 98


def test_intraday_cutoff_and_open_delay():
    unlocked = IntradayUnlock(explicit=True)
    plan = make_plan(duration=Duration.INTRADAY)
    quote = make_quote(atr_intraday=4)

    cutoff = evaluate(
        plan,
        quote,
        make_account(),
        unlock=unlocked,
        as_of=datetime(2026, 10, 23, 15, 30, tzinfo=ET),
    )
    assert cutoff.decision == Decision.FAIL
    assert cutoff.duration is None
    assert Code.INTRADAY_CUTOFF in reason_codes(cutoff)

    early = evaluate(
        plan,
        quote,
        make_account(),
        unlock=unlocked,
        as_of=datetime(2026, 10, 23, 9, 45, tzinfo=ET),
    )
    assert Code.INTRADAY_OPEN_DELAY in reason_codes(early)
    assert early.duration is None


def test_high_vol_without_structure_does_not_stay_overnight():
    result = evaluate(
        make_plan(),
        make_quote(high_vol=True, up_structure=False),
        make_account(),
        as_of=AS_OF,
    )
    assert result.decision == Decision.FAIL
    assert Code.HIGH_VOL_NO_OVERNIGHT in reason_codes(result)


def test_three_to_five_day_swing_is_refused_after_a_stop_or_in_high_vol():
    after_stop = evaluate(
        make_plan(duration=Duration.SWING_3_5),
        make_quote(up_structure=True),
        make_account(consecutive_stop_losses=1),
        as_of=AS_OF,
    )
    assert Code.PREFER_SHORTER_HOLD in reason_codes(after_stop)

    still_short = evaluate(
        make_plan(duration=Duration.SWING_1_2),
        make_quote(),
        make_account(consecutive_stop_losses=1),
        as_of=AS_OF,
    )
    assert still_short.decision == Decision.PASS
