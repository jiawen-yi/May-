"""Stable reason codes. Messages live at the call site; tests bind to these."""


class Code:
    THESIS_MISSING = "thesis_missing"
    STOP_BASIS_MISSING = "stop_basis_missing"
    STOP_NOT_STRUCTURAL = "stop_not_structural"
    STOP_TIGHTENED_FOR_GATE = "stop_tightened_for_gate"
    STOP_LOOSENED = "stop_loosened"
    STOP_MISMATCH = "stop_mismatch"
    STOP_GEOMETRY = "stop_geometry"
    INTRADAY_ATR_REQUIRED = "intraday_atr_required"
    RR_BELOW_MIN = "rr_below_min"
    GEOMETRY = "geometry"
    INVALID_SIDE = "invalid_side"
    LONG_BOOK_FIREWALL = "long_book_firewall"
    CHAIN_MISSING = "chain_missing"

    INTRADAY_LOCKED = "intraday_locked"
    INTRADAY_CUTOFF = "intraday_cutoff"
    INTRADAY_OPEN_DELAY = "intraday_open_delay"
    HIGH_VOL_NO_OVERNIGHT = "high_vol_no_overnight"
    PREFER_SHORTER_HOLD = "prefer_shorter_hold"

    CHASE_EXTENDED = "chase_extended"
    DAY_DOWN = "day_down"
    NEAR_52W_HIGH = "near_52w_high"
    EXTENDED_SPREAD = "extended_spread"
    BENCHMARK_SAME_DIRECTION = "benchmark_same_direction"
    INSTRUMENT_BANNED = "instrument_banned"
    ROUND_TRIP_COST = "round_trip_cost"
    STALE_QUOTE = "stale_quote"

    HARD_PAUSE = "hard_pause"
    LOSS_BRAKE = "loss_brake"
    DAILY_LOSS_HALT = "daily_loss_halt"
    STOP_COOLDOWN = "stop_cooldown"
    CHAIN_FULL = "chain_full"
    PER_TRADE_RISK = "per_trade_risk"
    STACK_RISK = "stack_risk"
    CONCENTRATION = "concentration"
    SLEEVE_CAP = "sleeve_cap"
    SIZE_BELOW_ONE_SHARE = "size_below_one_share"
    WASH_REBUY_SIZE = "wash_rebuy_size"
    LOSER_NOT_PULLED_BACK = "loser_not_pulled_back"
    LOSER_MA10_REQUIRED = "loser_ma10_required"
    PDT_LIMIT = "pdt_limit"
    DESK_INTRADAY_CAP = "desk_intraday_cap"
    UNPLANNED_EVENT = "unplanned_event"
    INVALID_EQUITY = "invalid_equity"


# Automatic no-trade list (playbook vetoes plus the structural-stop ban).
VETO_CODES = frozenset(
    {
        Code.CHASE_EXTENDED,
        Code.DAY_DOWN,
        Code.NEAR_52W_HIGH,
        Code.EXTENDED_SPREAD,
        Code.BENCHMARK_SAME_DIRECTION,
        Code.INTRADAY_LOCKED,
        Code.RR_BELOW_MIN,
        Code.INSTRUMENT_BANNED,
        Code.ROUND_TRIP_COST,
        Code.STALE_QUOTE,
        Code.STOP_TIGHTENED_FOR_GATE,
        Code.STOP_NOT_STRUCTURAL,
    }
)

RISK_CODES = frozenset(
    {
        Code.HARD_PAUSE,
        Code.LOSS_BRAKE,
        Code.DAILY_LOSS_HALT,
        Code.STOP_COOLDOWN,
        Code.CHAIN_FULL,
        Code.PER_TRADE_RISK,
        Code.STACK_RISK,
        Code.CONCENTRATION,
        Code.SLEEVE_CAP,
        Code.SIZE_BELOW_ONE_SHARE,
        Code.WASH_REBUY_SIZE,
        Code.LOSER_NOT_PULLED_BACK,
        Code.LOSER_MA10_REQUIRED,
        Code.PDT_LIMIT,
        Code.DESK_INTRADAY_CAP,
        Code.UNPLANNED_EVENT,
        Code.INVALID_EQUITY,
    }
)
