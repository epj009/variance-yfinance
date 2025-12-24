"""
Diagnostics helpers for consistent, structured counters and error tracking.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

MARKET_DATA_ERROR_COUNTERS: dict[str, int] = {
    "market_data_error_count": 0,
    "price_unavailable_count": 0,
    "history_unavailable_count": 0,
    "iv_unavailable_count": 0,
    "skipped_symbol_count": 0,
    "unknown_error_count": 0,
}

MARKET_DATA_COUNTER_DEFAULTS: dict[str, int] = {
    "symbols_total": 0,
    "symbols_with_errors": 0,
    "stale_count": 0,
}
MARKET_DATA_COUNTER_DEFAULTS.update(MARKET_DATA_ERROR_COUNTERS)


@dataclass
class Diagnostics:
    counters: dict[str, int] = field(default_factory=dict)

    def incr(self, key: str, amount: int = 1) -> None:
        self.counters[key] = int(self.counters.get(key, 0)) + amount

    def get(self, key: str, default: int = 0) -> int:
        return int(self.counters.get(key, default))

    def to_dict(self) -> dict[str, int]:
        return dict(self.counters)

    def record_market_data_error(self, error: Any) -> None:
        self.incr("market_data_error_count")
        if error == "price_unavailable":
            self.incr("price_unavailable_count")
        elif error == "history_unavailable":
            self.incr("history_unavailable_count")
        elif error == "iv_unavailable":
            self.incr("iv_unavailable_count")
        elif error == "skipped_symbol":
            self.incr("skipped_symbol_count")
        else:
            self.incr("unknown_error_count")


SCREENER_COUNTER_DEFAULTS: dict[str, int] = {
    "low_vrp_structural_count": 0,
    "missing_vrp_structural_count": 0,
    "sector_skipped_count": 0,
    "asset_class_skipped_count": 0,
    "illiquid_skipped_count": 0,
    "data_integrity_skipped_count": 0,
    "low_vol_trap_skipped_count": 0,
    "hv_rank_trap_skipped_count": 0,
    "correlation_skipped_count": 0,
    "tactical_skipped_count": 0,
    "bats_efficiency_zone_count": 0,
    "implied_liquidity_count": 0,
    "lean_data_skipped_count": 0,
    "anomalous_data_skipped_count": 0,
}
SCREENER_COUNTER_DEFAULTS.update(MARKET_DATA_ERROR_COUNTERS)


class ScreenerDiagnostics(Diagnostics):
    @classmethod
    def create(cls) -> "ScreenerDiagnostics":
        return cls(counters=dict(SCREENER_COUNTER_DEFAULTS))


class MarketDataDiagnostics(Diagnostics):
    @classmethod
    def from_payload(cls, market_data: dict[str, Any]) -> "MarketDataDiagnostics":
        diag = cls(counters=dict(MARKET_DATA_COUNTER_DEFAULTS))
        diag.incr("symbols_total", len(market_data))

        for _symbol, data in market_data.items():
            if not data:
                diag.incr("symbols_with_errors")
                diag.record_market_data_error("unknown")
                continue

            if data.get("is_stale"):
                diag.incr("stale_count")

            error = data.get("error")
            if error:
                diag.incr("symbols_with_errors")
                diag.record_market_data_error(error)

        return diag


TRIAGE_COUNTER_DEFAULTS: dict[str, int] = {
    "positions_total": 0,
    "positions_with_tags": 0,
    "positions_stale": 0,
    "missing_market_data_count": 0,
    "missing_vrp_tactical_count": 0,
    "missing_vrp_structural_count": 0,
}
TRIAGE_COUNTER_DEFAULTS.update(MARKET_DATA_ERROR_COUNTERS)


class TriageDiagnostics(Diagnostics):
    @classmethod
    def create(cls) -> "TriageDiagnostics":
        return cls(counters=dict(TRIAGE_COUNTER_DEFAULTS))

    def record_position(self, report: Mapping[str, Any], market_data: Mapping[str, Any]) -> None:
        self.incr("positions_total")

        if report.get("is_stale"):
            self.incr("positions_stale")

        tags = report.get("tags") or []
        if tags:
            self.incr("positions_with_tags")
            for tag in tags:
                tag_type = str(tag.get("type", "unknown")).lower()
                safe_tag = "".join(c if c.isalnum() else "_" for c in tag_type).strip("_")
                self.incr(f"tag_{safe_tag}_count")

        root = report.get("root")
        if not root:
            self.incr("missing_market_data_count")
            return

        data = market_data.get(root)
        if not data:
            self.incr("missing_market_data_count")
            return

        if data.get("error"):
            self.record_market_data_error(data.get("error"))

        if data.get("vrp_tactical") is None:
            self.incr("missing_vrp_tactical_count")
        if data.get("vrp_structural") is None:
            self.incr("missing_vrp_structural_count")
