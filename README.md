# May-
交易
may_trade

Dry-run decision and order-intent engine for the May US short-swing sleeve. It turns a plan plus a mock quote into a PASS / FAIL / WAIT_PULLBACK decision and a JSON limit entry with a paired OCO. It does not place live broker orders.

This is a desk aid, not a broker and not investment advice. Numbers below are the coded ceilings from the 2026-10-24 sleeve rules. The playbook prose is not copied into this repo.

Dry-run and live







Path



What happens





evaluate, scan, and route with no flag



Print intents only. Nothing is sent.





route --live without MAY_LIVE_TRADING=1



Refuses.





route --live and MAY_LIVE_TRADING=1 and --broker paper



PaperBroker records the entry, then the OCO, in memory. Still not a live fill.





route --live and MAY_LIVE_TRADING=1 and --broker schwab



SchwabWebAdapter raises NotImplementedError.

Live Schwab execution is out of band. Fills are entered in the Schwab web UI by a person. This package does not store Schwab credentials, scrape a logged-in session, or call a Schwab API.

PaperBroker.submit_open rejects an entry that has no OCO. A lone entry is not a completed open.

Run

python -m pip install -e ".[dev]"
pytest
python -m may_trade.cli evaluate --fixture tests/fixtures/sample_plan.json
python -m may_trade.cli scan --fixture tests/fixtures/sample_universe.json

evaluate prints the decision on the first line, then JSON. A passing plan has intents[0] as a limit entry and intents[1] as the GTC OCO (trigger: on_entry_fill). Exit code 0 means the command ran; FAIL is still exit 0. A bad fixture is exit 1. A live route without the env flag is exit 2. The Schwab stub is exit 3.

Optional tighter parameters (never looser ones):

python -m may_trade.cli evaluate --fixture tests/fixtures/sample_plan.json --config config.example.yaml

What buy authority is

A sleeve buy or short is allowed only when all of these hold:





Setup gate: named structural stop, target, thesis, and R:R ≥ 2.0.



Hard risk: per-trade cap for the hold length (and the 2% ceiling), day-loss halt at 1.5%, stacked open risk ≤ 3%, one name ≤ 40% of equity, one chain ≤ 2 names.



Automatic vetoes: none firing.

Sector leadership only sorts scan. A lagging sector does not veto a name that cleared the gate, and it does not excuse a name that did not.

R:R is measured on the structural stop. Tightening that stop so the ratio clears is a fail. The one exception is an unlocked intraday tag, which must use the tighter of the structural stop and half the intraday ATR — that adjustment is the hold rule, and a stop tighter than both is still refused.

Hold length







Tag



Code



Risk cap



Ladder vs cost



Notes





日内



intraday



1.0%



+3% / +6% / +10%



Locked unless IntradayUnlock(explicit=True). No new tag at or after 15:30 ET. Flat by 15:55 ET.





短波



swing_1_2



1.5%



+4% / +8% / +12%



Default when the plan omits a tag.





波段



swing_3_5



2.0%



+5% / +10% / +15%



Refused in high vol or after a recent stop-out.

IntradayUnlock.explicit is a caller assertion that the user asked for an intraday hold in that instruction. A scan, a soft tape, or a previous day-trade does not set it. If it is false, the engine will not label the result intraday and will not emit an intraday intent.

Other clocks (America/New_York): regular-session intraday entries wait until 10:00. An intraday lot that is still on the next session is retagged to the 1–2 day swing with a nearer target and may not stay a second night.

Other coded limits





Instruments: common stock and unlevered ETFs. Options and leveraged or inverse products (including a denylist of 2×/3× tickers) are rejected.



Down more than 3% on the day: no long. Exactly 3% is not a veto.



More than 8% above MA10 and RSI(6) above 80: no long.



Inside 3% of the 52-week high without a new catalyst: no long.



Extended-hours spread above 0.5%, or a missing spread: no trade. A tight extended session is half size and tagged 非正规时段.



Same-direction open into a QQQ/SOXX break: no trade. Pass benchmark_break_same_direction on the quote when that is true.



Round-trip cost at least one fifth of expected profit: no trade.



Day loss at 1.5% of equity, two consecutive stop-outs, or a same-day stop in that symbol: no new open. Negative cash is not a veto.



A symbol with a realized loss this year can be re-entered (there is no 30-day ban) only at the tighter 1% risk cap, within 3% of MA10, and at the smaller of half the prior share count and a $150 notional cap.



Soft tape (caller sets soft_tape) shrinks size and sorts laggards last. It does not ban a gate pass and it does not loosen stops.



Mag7 names (AAPL MSFT GOOGL GOOG AMZN META NVDA TSLA) can pass the gate but the intent is routable: false until mag7_approved is set. Report, then wait.



Idle cash may be parked only in BOXX or SGOV, without an OCO. That path is cash_park_intent, not the sleeve gate.



Realized sleeve gains above $1 are proposed as a long-book split (QQQM 30 / SPYM 30 / SCHD 40). They are not sleeve orders.

Sleeve gross notional is capped at account equity. The older fixed-dollar sleeve cap is not reintroduced. The 40% name cap and the 3% stack still bind.

Open lots are managed by manage_position: repair a missing OCO, ratchet a stop (longs only up, shorts only down), take the hold-length ladder in whole shares, and flatten on the intraday clock or a blown time stop. Ladder trims are ordered cancel → new OCO on the remainder → limit sale.

Long book firewall

may_trade.long_book only emits research proposals (HOLD / ADD / TRIM / EXIT / WATCH) with a next review date. Caps inside that book are 15% per name and 35% per sector. Proposals cannot be converted into sleeve plans (as_sleeve_plan and sleeve_candidates always raise). evaluate rejects book: long. Long-book lots are not put through the sleeve ladder or a short-term OCO.

Module map







Module



Role





gate.py



Setup gate: entry, structural stop, target, R:R ≥ 2, thesis.





vetoes.py



Automatic no-trade checks. Sector rank is not one of them.





risk.py



Per-trade, day halt, stack, concentration, chain, cooldown, rebuy size.





duration.py



日内 / 短波 / 波段 tags, ladders, 15:30 and 15:55 ET.





lifecycle.py



OCO repair, ladder, ratchet, time stop, intraday flatten.





long_book.py



§14-style research only. Firewall against the sleeve path.





pipeline.py



evaluate and scan.





intents.py



Limit entry + OCO JSON, and the BOXX/SGOV park intent.





broker/paper.py



Paper ledger. Records the OCO after the buy intent.





broker/schwab_stub.py



Interface only. Always raises.





cli.py



evaluate, scan, route.

Fixture shape

tests/fixtures/sample_plan.json is a passing mock. Quotes are caller-supplied; this package does not fetch prices. Required gate inputs include last, day change, MA10, RSI(6), and (for longs) the 52-week high. Missing those fields fails closed.

from may_trade import evaluate
from may_trade.models import IntradayUnlock

result = evaluate(plan, quote, account, unlock=IntradayUnlock(explicit=False), as_of=moment)
result.decision   # PASS, FAIL, or WAIT_PULLBACK
result.to_dict()  # JSON-ready intents
