"""Decision and order-intent engine for the May US short-swing sleeve.

Default output is a dry-run plan. Nothing in this package submits a live
broker order unless a caller turns on both live switches and passes a broker
adapter. The Schwab web adapter is a stub.
"""

from may_trade.pipeline import evaluate, scan
from may_trade.models import (
    AccountState,
    Decision,
    Duration,
    Evaluation,
    IntradayUnlock,
    OrderIntent,
    Position,
    QuoteSnapshot,
    TradePlan,
)

__version__ = "0.1.0"

__all__ = [
    "AccountState",
    "Decision",
    "Duration",
    "Evaluation",
    "IntradayUnlock",
    "OrderIntent",
    "Position",
    "QuoteSnapshot",
    "TradePlan",
    "evaluate",
    "scan",
    "__version__",
]
