import pytest

from may_trade import evaluate
from may_trade.broker import PaperBroker, SchwabWebAdapter, route_open
from may_trade.errors import LiveTradingDisabled, PolicyBreach
from may_trade.intents import cash_park_intent
from may_trade.models import Decision

from tests.conftest import AS_OF, make_account, make_plan, make_quote


def _pass():
    result = evaluate(make_plan(), make_quote(), make_account(), as_of=AS_OF)
    assert result.decision == Decision.PASS
    return result


def test_paper_broker_records_oco_after_buy_intent():
    result = _pass()
    broker = PaperBroker()
    receipts = broker.submit_open(result.intents)
    assert [item.intent_type for item in broker.recorded] == ["entry", "oco"]
    assert broker.recorded[0].side == "buy"
    assert broker.recorded[1].quantity == broker.recorded[0].quantity
    assert receipts[0].status == "accepted"
    assert receipts[1].status == "working"
    assert receipts[0].mode == "paper"
    planned = broker.planned_positions["ANET"]
    assert planned.has_oco is True
    assert planned.stop == 95
    assert planned.target == 112
    assert planned.shares == 50


def test_entry_without_oco_is_rejected():
    result = _pass()
    broker = PaperBroker()
    with pytest.raises(PolicyBreach):
        broker.submit(result.intents[0])
    with pytest.raises(PolicyBreach):
        broker.submit_open(result.intents[:1])


def test_route_stays_dry_unless_both_live_switches_are_on(monkeypatch):
    result = _pass()
    broker = PaperBroker()
    monkeypatch.delenv("MAY_LIVE_TRADING", raising=False)

    dry = route_open(result.intents, broker, live=False)
    assert dry.routed is False
    assert broker.recorded == []

    monkeypatch.setenv("MAY_LIVE_TRADING", "1")
    still_dry = route_open(result.intents, broker, live=False)
    assert still_dry.routed is False
    assert broker.recorded == []

    monkeypatch.delenv("MAY_LIVE_TRADING", raising=False)
    with pytest.raises(LiveTradingDisabled):
        route_open(result.intents, broker, live=True)
    assert broker.recorded == []

    monkeypatch.setenv("MAY_LIVE_TRADING", "1")
    routed = route_open(result.intents, broker, live=True)
    assert routed.routed is True
    assert [item.intent_type for item in broker.recorded] == ["entry", "oco"]
    assert broker.recorded[0].dry_run is False


def test_schwab_adapter_is_a_stub_even_when_live_is_armed(monkeypatch):
    result = _pass()
    monkeypatch.setenv("MAY_LIVE_TRADING", "1")
    adapter = SchwabWebAdapter()
    with pytest.raises(NotImplementedError, match="Schwab web UI"):
        route_open(result.intents, adapter, live=True)
    with pytest.raises(NotImplementedError, match="credentials"):
        adapter.submit(result.intents[1])
    with pytest.raises(NotImplementedError, match="Schwab web UI"):
        adapter.cancel("order-1")

    # The env flag alone does not touch the stub when the route is dry-run.
    dry = route_open(result.intents, adapter, live=False)
    assert dry.routed is False


def test_cash_park_is_not_an_oco_sleeve_trade():
    intent = cash_park_intent("BOXX", 2, 118.5)
    assert intent.intent_type == "cash_park"
    assert intent.metadata["oco"] is False
    broker = PaperBroker()
    broker.submit(intent)
    assert broker.recorded[0].symbol == "BOXX"
    with pytest.raises(PolicyBreach):
        cash_park_intent("NVDA", 1, 100)
