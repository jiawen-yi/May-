"""Dry-run CLI.

``evaluate`` prints PASS, FAIL, or WAIT_PULLBACK and the JSON intents.
It never routes an order. ``route --live`` still requires MAY_LIVE_TRADING=1,
and the Schwab adapter remains a stub.
"""

from __future__ import annotations

import argparse
import json
import sys

from may_trade.broker import PaperBroker, SchwabWebAdapter, route_open
from may_trade.config import load_settings
from may_trade.errors import (
    ConfigError,
    FirewallError,
    FixtureError,
    LiveTradingDisabled,
    PolicyBreach,
)
from may_trade.fixture import load_evaluation_fixture, load_scan_fixture
from may_trade.models import Decision
from may_trade.pipeline import evaluate, scan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="may_trade")
    sub = parser.add_subparsers(dest="command", required=True)

    evaluate_parser = sub.add_parser("evaluate", help="Dry-run one plan. Prints PASS/FAIL and JSON intents.")
    _add_fixture(evaluate_parser)

    scan_parser = sub.add_parser("scan", help="Dry-run a candidate list. Sector score only sorts.")
    _add_fixture(scan_parser)

    route_parser = sub.add_parser("route", help="Route a passing plan. Dry-run unless --live and the env flag.")
    _add_fixture(route_parser)
    route_parser.add_argument("--live", action="store_true", help="Required, together with MAY_LIVE_TRADING=1.")
    route_parser.add_argument("--broker", choices=("paper", "schwab"), default="paper")

    args = parser.parse_args(argv)
    try:
        if args.command == "evaluate":
            return _evaluate(args)
        if args.command == "scan":
            return _scan(args)
        if args.command == "route":
            return _route(args)
    except FixtureError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    except ConfigError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    except LiveTradingDisabled as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2
    except NotImplementedError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 3
    except (PolicyBreach, FirewallError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    print("ERROR unknown command", file=sys.stderr)
    return 1


def _add_fixture(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--fixture", required=True, help="Path to a JSON plan/quote fixture.")
    parser.add_argument("--config", default=None, help="Optional YAML of tighter parameters.")


def _evaluate(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    plan, quote, account, unlock, as_of = load_evaluation_fixture(args.fixture)
    result = evaluate(plan, quote, account, unlock=unlock, as_of=as_of, settings=settings)
    _print_decision(result)
    return 0


def _scan(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    candidates, account, unlock, as_of = load_scan_fixture(args.fixture)
    result = scan(candidates, account, unlock=unlock, as_of=as_of, settings=settings)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


def _route(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    plan, quote, account, unlock, as_of = load_evaluation_fixture(args.fixture)
    result = evaluate(plan, quote, account, unlock=unlock, as_of=as_of, settings=settings)
    if result.decision == Decision.FAIL or not result.intents:
        _print_decision(result)
        return 0
    if not args.live:
        print("DRY_RUN")
        _print_decision(result)
        return 0
    broker = PaperBroker() if args.broker == "paper" else SchwabWebAdapter()
    routed = route_open(result.intents, broker, live=True)
    print("ROUTED")
    print(json.dumps(routed.to_dict(), indent=2, ensure_ascii=False))
    return 0


def _print_decision(result) -> None:
    print(result.decision.value)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
