from datetime import date

import pytest

from may_trade import evaluate
from may_trade.codes import Code
from may_trade.errors import FirewallError
from may_trade.long_book import (
    LongAction,
    LongHolding,
    allocate_realized_profit,
    as_sleeve_plan,
    propose,
    sleeve_candidates,
)
from may_trade.models import Book, Decision, InstrumentKind

from tests.conftest import AS_OF, make_account, make_plan, make_quote


def _proposal(**overrides):
    base = dict(
        symbol="VST",
        action=LongAction.ADD,
        thesis="Owner earnings cover the reinvestment need for several years.",
        red_lines=["leverage above the stated ceiling"],
        valuation_anchor="mid-cycle free cash flow",
        role="core compounder",
        size_pct=0.10,
        sector="power",
        next_review=date(2026, 12, 31),
    )
    base.update(overrides)
    return propose(**base)


def test_proposal_never_becomes_a_sleeve_plan():
    proposal = _proposal()
    assert proposal.accepted
    assert proposal.sleeve_executable is False
    assert proposal.enters_setup_gate is False
    assert proposal.enters_hourly_scan is False
    assert proposal.attach_short_oco is False
    with pytest.raises(FirewallError):
        as_sleeve_plan(proposal)
    with pytest.raises(FirewallError):
        sleeve_candidates([proposal])


def test_long_book_name_and_sector_caps_and_leverage_ban():
    assert _proposal(size_pct=0.16).accepted is False
    crowded = _proposal(
        size_pct=0.10,
        holdings=[LongHolding("CEG", "power", 0.30)],
    )
    assert crowded.accepted is False
    geared = _proposal(symbol="SOXL", instrument=InstrumentKind.LEVERAGED_ETF)
    assert geared.accepted is False


def test_evaluate_refuses_a_long_book_plan():
    result = evaluate(
        make_plan(book=Book.LONG),
        make_quote(),
        make_account(),
        as_of=AS_OF,
    )
    assert result.decision == Decision.FAIL
    assert result.intents == []
    assert Code.LONG_BOOK_FIREWALL in reason_codes(result)


def test_profit_sweep_is_a_long_book_proposal():
    assert allocate_realized_profit(0.03) is None
    sweep = allocate_realized_profit(100)
    assert sweep is not None
    assert sweep.sleeve_executable is False
    assert sweep.oco is False
    weights = [leg["weight"] for leg in sweep.legs]
    assert weights == [0.30, 0.30, 0.40]
    assert [leg["symbol"] for leg in sweep.legs] == ["QQQM", "SPYM", "SCHD"]


def reason_codes(result):
    return [item.code for item in result.reasons]
