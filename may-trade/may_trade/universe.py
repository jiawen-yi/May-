"""Instrument filter and sort-only sector helpers.

Allowed: common stock and unlevered ETFs. Banned: options, leveraged or
inverse ETFs, and a denylist of well-known 2x/3x products. Sector leadership
never grants or removes buy authority.
"""

from __future__ import annotations

from may_trade.codes import Code
from may_trade.models import InstrumentKind, Reason

# Common geared products. The instrument kind is the real filter; this list
# catches a mis-labeled ticker. It is not a complete exchange directory.
LEVERAGED_SYMBOLS = frozenset(
    {
        "TQQQ",
        "SQQQ",
        "UPRO",
        "SPXU",
        "SPXL",
        "SOXL",
        "SOXS",
        "TECL",
        "TECS",
        "FAS",
        "FAZ",
        "TNA",
        "TZA",
        "QLD",
        "QID",
        "SSO",
        "SDS",
        "UDOW",
        "SDOW",
        "LABU",
        "LABD",
        "NUGT",
        "DUST",
        "JNUG",
        "JDST",
        "BOIL",
        "KOLD",
        "UVXY",
        "SVXY",
        "TMF",
        "TMV",
        "BULZ",
        "FNGU",
        "FNGD",
        "NAIL",
        "DRIP",
        "GUSH",
        "CWEB",
        "YINN",
        "YANG",
        "EDC",
        "EDZ",
        "INDL",
        "BRZU",
        "MEXX",
        "WEBL",
        "WEBS",
        "BITX",
        "CONL",
    }
)

CASH_PARK_SYMBOLS = frozenset({"BOXX", "SGOV"})

# Report-first names. A pass still needs an explicit ack before routing.
MAG7 = frozenset({"AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA"})

_ALLOWED = frozenset({InstrumentKind.COMMON_STOCK, InstrumentKind.UNLEVERED_ETF})


def instrument_allowed(symbol: str, kind: InstrumentKind) -> Reason | None:
    ticker = symbol.upper().strip()
    if kind not in _ALLOWED or ticker in LEVERAGED_SYMBOLS:
        return Reason(
            Code.INSTRUMENT_BANNED,
            "Sleeve orders allow common stock and unlevered ETFs only. "
            "Options and leveraged or inverse products are banned.",
        )
    return None


def is_mag7(symbol: str) -> bool:
    return symbol.upper().strip() in MAG7
