"""Decision order: tape context, risk budget, instrument, setup gate, life tags.

Sector rank never flips a PASS to a FAIL. A locked intraday request is not
silently rewritten into a swing tag.
"""

from __future__ import annotations

from datetime import datetime

from may_trade.codes import RISK_CODES, VETO_CODES, Code
from may_trade.config import Settings
from may_trade.duration import ET, resolve_duration, in_et
from may_trade.gate import evaluate_setup
from may_trade.intents import build_open_intents
from may_trade.models import (
    AccountState,
    Book,
    Decision,
    Evaluation,
    IntradayUnlock,
    QuoteSnapshot,
    Reason,
    ScanResult,
    Side,
    TradePlan,
)
from may_trade.money import long_side
from may_trade.risk import assess_risk, chain_occupancy
from may_trade.universe import instrument_allowed, is_mag7
from may_trade.vetoes import automatic_vetoes, estimate_round_trip_cost, round_trip_veto


def evaluate(
    plan: TradePlan,
    quote: QuoteSnapshot,
    account: AccountState,
    *,
    unlock: IntradayUnlock | None = None,
    as_of: datetime | None = None,
    settings: Settings | None = None,
) -> Evaluation:
    settings = settings or Settings()
    unlock = unlock or IntradayUnlock(explicit=False)
    moment = in_et(as_of) if as_of is not None else datetime.now(ET)

    if plan.book != Book.SLEEVE:
        return _evaluation(
            plan,
            quote,
            Decision.FAIL,
            None,
            None,
            [
                Reason(
                    Code.LONG_BOOK_FIREWALL,
                    "Long-book ideas do not enter the sleeve gate or its order path.",
                )
            ],
            None,
            ["long_book_firewall"],
        )

    reasons: list[Reason] = []
    notes: list[str] = []
    if plan.side not in (Side.BUY, Side.SHORT):
        reasons.append(Reason(Code.INVALID_SIDE, "Sleeve entries are buy or short."))
    if not plan.chain:
        reasons.append(Reason(Code.CHAIN_MISSING, "An industry chain id is required."))

    banned = instrument_allowed(plan.symbol, plan.instrument)
    if banned is not None:
        reasons.append(banned)

    duration = resolve_duration(
        plan.duration,
        unlock,
        as_of=moment,
        session=quote.session,
        high_vol=quote.high_vol,
        up_structure=quote.up_structure,
        consecutive_stops=account.consecutive_stop_losses,
        settings=settings,
    )
    reasons.extend(duration.reasons)

    active_duration = duration.duration if duration.ok else None
    setup = evaluate_setup(plan, quote, active_duration, settings)
    reasons.extend(setup.reasons)
    notes.extend(setup.notes)
    reasons.extend(automatic_vetoes(plan, quote, settings))

    risk = None
    if (
        duration.ok
        and active_duration is not None
        and setup.effective_stop is not None
        and setup.rr is not None
        and plan.side in (Side.BUY, Side.SHORT)
    ):
        risk = assess_risk(
            plan,
            quote,
            account,
            duration=active_duration,
            effective_stop=setup.effective_stop,
            settings=settings,
        )
        reasons.extend(risk.reasons)
        if risk.shares >= 1 and setup.rr is not None:
            profit = abs(plan.target - plan.entry) * risk.shares
            cost = estimate_round_trip_cost(quote, plan.entry, risk.shares)
            cost_veto = round_trip_veto(cost, profit, settings)
            if cost_veto is not None:
                reasons.append(cost_veto)
                risk.allowed = False

    reasons = _dedupe(reasons)
    if quote.sector_lagging:
        notes.append("lagging_sector_did_not_change_the_gate")
    if quote.soft_tape:
        notes.append("soft_tape_downweights_size_and_sorts_laggards_last")
    if account.cash < 0:
        notes.append("negative_cash_is_not_a_veto")

    tagged = active_duration if duration.ok and Code.INTRADAY_LOCKED not in {r.code for r in reasons} else None
    if reasons or risk is None or not risk.allowed or tagged is None or setup.effective_stop is None or setup.rr is None:
        return _evaluation(plan, quote, Decision.FAIL, setup.rr, tagged if duration.ok else None, reasons, risk, notes)

    wait = _waiting_for_pullback(plan, quote)
    decision = Decision.WAIT_PULLBACK if wait else Decision.PASS
    ack = is_mag7(plan.symbol) and plan.symbol not in account.mag7_approved and not plan.mag7_approved
    if ack:
        notes.append("mag7_report_then_wait")
    intents = build_open_intents(
        plan,
        duration=tagged,
        shares=risk.shares,
        effective_stop=setup.effective_stop,
        rr=setup.rr,
        session=quote.session,
        routable=not ack,
        requires_user_ack=ack,
        ytd_loser=plan.symbol in account.realized_loss_symbols_ytd,
    )
    return _evaluation(plan, quote, decision, setup.rr, tagged, [], risk, notes, intents)


def scan(
    candidates: list[tuple[TradePlan, QuoteSnapshot]],
    account: AccountState,
    *,
    unlock: IntradayUnlock | None = None,
    as_of: datetime | None = None,
    settings: Settings | None = None,
) -> ScanResult:
    """Sort leaders ahead of laggards, then run the same gate on each name.

    A chain that already holds two sleeve names is stood down before the hunt.
    Standing down is the chain limit, not a sector veto.
    """

    settings = settings or Settings()
    occupied = chain_occupancy(account)
    hunt: list[tuple[TradePlan, QuoteSnapshot]] = []
    stood_down: list[dict[str, str]] = []
    for plan, quote in candidates:
        held = occupied.get(plan.chain, set())
        if plan.symbol not in held and len(held) >= settings.chain_max_positions:
            stood_down.append(
                {"symbol": plan.symbol, "chain": plan.chain, "reason": Code.CHAIN_FULL}
            )
            continue
        hunt.append((plan, quote))
    hunt.sort(
        key=lambda item: (
            1 if item[1].sector_lagging else 0,
            -float(item[1].sector_score),
            item[0].symbol,
        )
    )
    ranked = [
        evaluate(plan, quote, account, unlock=unlock, as_of=as_of, settings=settings)
        for plan, quote in hunt
    ]
    return ScanResult(ranked=ranked, stood_down=stood_down)


def _waiting_for_pullback(plan: TradePlan, quote: QuoteSnapshot) -> bool:
    if long_side(plan.side) and plan.entry_high is not None and quote.last > plan.entry_high:
        return True
    if plan.side == Side.SHORT and plan.entry_low is not None and quote.last < plan.entry_low:
        return True
    return False


def _dedupe(reasons: list[Reason]) -> list[Reason]:
    seen: set[str] = set()
    ordered: list[Reason] = []
    for item in reasons:
        if item.code in seen:
            continue
        seen.add(item.code)
        ordered.append(item)
    return ordered


def _evaluation(
    plan: TradePlan,
    quote: QuoteSnapshot,
    decision: Decision,
    rr: float | None,
    duration,
    reasons: list[Reason],
    risk,
    notes: list[str],
    intents=None,
) -> Evaluation:
    codes = {item.code for item in reasons}
    checks = {
        "setup_rr": Code.RR_BELOW_MIN not in codes and Code.GEOMETRY not in codes,
        "structural_stop": Code.STOP_TIGHTENED_FOR_GATE not in codes
        and Code.STOP_NOT_STRUCTURAL not in codes,
        "vetoes_clear": not (codes & VETO_CODES),
        "risk_clear": not (codes & RISK_CODES),
        "duration_ok": Code.INTRADAY_LOCKED not in codes
        and Code.INTRADAY_CUTOFF not in codes
        and Code.HIGH_VOL_NO_OVERNIGHT not in codes
        and Code.PREFER_SHORTER_HOLD not in codes,
        "intraday_tag_allowed": Code.INTRADAY_LOCKED not in codes,
    }
    return Evaluation(
        decision=decision,
        symbol=plan.symbol,
        rr=rr,
        duration=duration,
        reasons=list(reasons),
        vetoes=[item for item in reasons if item.code in VETO_CODES],
        risk=None if risk is None else risk.breakdown(),
        intents=list(intents or []),
        checks=checks,
        sector_lagging=quote.sector_lagging,
        sector_effect="sort_only",
        notes=list(notes),
        dry_run=True,
    )
