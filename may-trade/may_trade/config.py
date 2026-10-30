"""Desk parameters.

Principles (R:R floor, stacked-risk ceiling, instrument ban, OCO, stop
ratchet) cannot be loosened here. Knobs may only get stricter.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from may_trade.errors import ConfigError

# Fixed. The desk stopped raising this hurdle by hold length or by YTD.
RR_MIN = 2.0

DEFAULT_DURATION_CAPS = {
    "intraday": 0.01,
    "swing_1_2": 0.015,
    "swing_3_5": 0.02,
}

# (bound, limit). "max" means the configured value must be <= limit.
_BOUNDS: dict[str, tuple[str, float]] = {
    "per_trade_hard_cap_pct": ("max", 0.02),
    "day_loss_halt_pct": ("max", 0.015),
    "stack_risk_max_pct": ("max", 0.03),
    "name_concentration_max_pct": ("max", 0.40),
    "day_down_veto_pct": ("max", 0.03),
    "ma10_chase_pct": ("max", 0.08),
    "rsi_chase": ("max", 80.0),
    "extended_spread_max_pct": ("max", 0.005),
    "round_trip_cost_fraction": ("max", 0.20),
    "loser_risk_cap_pct": ("max", 0.01),
    "loser_ma10_max_extension": ("max", 0.03),
    "wash_rebuy_notional_cap": ("max", 150.0),
    "soft_tape_size_multiplier": ("max", 1.0),
    "extended_size_multiplier": ("max", 0.5),
    "long_name_cap_pct": ("max", 0.15),
    "long_sector_cap_pct": ("max", 0.35),
    "high_52w_proximity_pct": ("min", 0.03),
}


@dataclass
class Settings:
    rr_min: float = RR_MIN
    per_trade_hard_cap_pct: float = 0.02
    day_loss_halt_pct: float = 0.015
    stack_risk_max_pct: float = 0.03
    name_concentration_max_pct: float = 0.40
    chain_max_positions: int = 2
    consecutive_stops_to_pause: int = 2
    day_down_veto_pct: float = 0.03
    ma10_chase_pct: float = 0.08
    rsi_chase: float = 80.0
    high_52w_proximity_pct: float = 0.03
    extended_spread_max_pct: float = 0.005
    round_trip_cost_fraction: float = 0.20
    loser_risk_cap_pct: float = 0.01
    loser_ma10_max_extension: float = 0.03
    wash_rebuy_notional_cap: float = 150.0
    soft_tape_size_multiplier: float = 0.75
    extended_size_multiplier: float = 0.5
    max_intraday_per_day: int = 2
    pdt_equity: float = 25_000.0
    pdt_day_trades: int = 3
    min_sweep_dollars: float = 1.0
    long_name_cap_pct: float = 0.15
    long_sector_cap_pct: float = 0.35
    intraday_atr_fraction: float = 0.5
    duration_risk_caps: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_DURATION_CAPS)
    )

    def __post_init__(self) -> None:
        if abs(self.rr_min - RR_MIN) > 1e-12:
            raise ConfigError("R:R minimum is fixed at 2.0 and cannot be raised or lowered.")
        if abs(self.intraday_atr_fraction - 0.5) > 1e-12:
            raise ConfigError("Intraday ATR stop fraction is fixed at 0.5.")
        for name, (bound, limit) in _BOUNDS.items():
            value = float(getattr(self, name))
            if value < 0:
                raise ConfigError(f"{name} cannot be negative.")
            if bound == "max" and value > limit + 1e-12:
                raise ConfigError(f"{name} cannot be loosened above {limit}.")
            if bound == "min" and value < limit - 1e-12:
                raise ConfigError(f"{name} cannot be loosened below {limit}.")
        if not 0 < self.soft_tape_size_multiplier <= 1:
            raise ConfigError("soft_tape_size_multiplier must be in (0, 1].")
        if not 0 < self.extended_size_multiplier <= 0.5:
            raise ConfigError("extended_size_multiplier cannot exceed 1/2.")
        if self.chain_max_positions < 1 or self.chain_max_positions > 2:
            raise ConfigError("chain_max_positions cannot exceed 2.")
        if self.consecutive_stops_to_pause < 1 or self.consecutive_stops_to_pause > 2:
            raise ConfigError("consecutive_stops_to_pause cannot exceed 2.")
        if self.max_intraday_per_day < 1 or self.max_intraday_per_day > 2:
            raise ConfigError("max_intraday_per_day cannot exceed 2.")
        if self.pdt_day_trades < 1 or self.pdt_day_trades > 3:
            raise ConfigError("pdt_day_trades cannot exceed 3.")
        if self.pdt_equity < 25_000:
            raise ConfigError("pdt_equity floor cannot be set below 25000.")
        if self.min_sweep_dollars < 0:
            raise ConfigError("min_sweep_dollars cannot be negative.")
        caps = dict(self.duration_risk_caps)
        unknown = set(caps) - set(DEFAULT_DURATION_CAPS)
        if unknown:
            raise ConfigError(f"Unknown duration risk cap: {sorted(unknown)}")
        for key, ceiling in DEFAULT_DURATION_CAPS.items():
            value = float(caps.get(key, ceiling))
            if value <= 0 or value > ceiling + 1e-12:
                raise ConfigError(f"duration risk cap {key} cannot be loosened above {ceiling}.")
            caps[key] = value
        self.duration_risk_caps = caps

    def duration_cap(self, duration_value: str) -> float:
        return float(self.duration_risk_caps[duration_value])


def load_settings(path: str | Path | None = None) -> Settings:
    if path is None:
        return Settings()
    raw = _read_yaml(Path(path))
    if raw is None:
        return Settings()
    if not isinstance(raw, dict):
        raise ConfigError("Config root must be a mapping.")
    known = {item.name for item in fields(Settings)}
    unknown = set(raw) - known
    if unknown:
        raise ConfigError(f"Unknown config keys: {sorted(unknown)}")
    data: dict[str, Any] = {}
    for key, value in raw.items():
        if key == "duration_risk_caps":
            if not isinstance(value, dict):
                raise ConfigError("duration_risk_caps must be a mapping.")
            merged = dict(DEFAULT_DURATION_CAPS)
            merged.update({str(k): float(v) for k, v in value.items()})
            data[key] = merged
        else:
            data[key] = value
    try:
        return Settings(**data)
    except TypeError as exc:
        raise ConfigError(str(exc)) from exc


def _read_yaml(path: Path) -> Any:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise ConfigError("PyYAML is required to load a config file.") from exc
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)
