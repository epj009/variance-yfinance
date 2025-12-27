#!/usr/bin/env python3
import argparse
import json
import os
import sys
from typing import Any

# Allow importing from src without installation (for dev convenience)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from variance.analyze_portfolio import analyze_portfolio
from variance.common import warn_if_not_venv
from variance.errors import error_lines


def build_diagnostics_footer(report_data: dict[str, Any]) -> dict[str, Any]:
    market_diag = report_data.get("market_data_diagnostics", {})
    triage_diag = report_data.get("triage_diagnostics", {})
    opportunities = report_data.get("opportunities", {})
    summary = opportunities.get("summary", {})

    return {
        "market_data": {
            "symbols_total": market_diag.get("symbols_total", 0),
            "stale_count": market_diag.get("stale_count", 0),
            "errors": market_diag.get("market_data_error_count", 0),
            "missing_iv": market_diag.get("iv_unavailable_count", 0),
            "missing_history": market_diag.get("history_unavailable_count", 0),
        },
        "triage": {
            "positions_total": triage_diag.get("positions_total", 0),
            "positions_with_tags": triage_diag.get("positions_with_tags", 0),
            "missing_market_data": triage_diag.get("missing_market_data_count", 0),
            "missing_vrp_tactical": triage_diag.get("missing_vrp_tactical_count", 0),
        },
        "screener": {
            "scanned": summary.get("scanned_symbols_count", 0),
            "candidates": summary.get("candidates_count", 0),
            "missing_tactical": summary.get("tactical_skipped_count", 0),
            "high_correlation": summary.get("correlation_skipped_count", 0),
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analyze current portfolio positions and generate a triage report."
    )
    parser.add_argument("file_path", type=str, help="Path to the portfolio CSV file.")
    parser.add_argument(
        "--diag",
        "--debug",
        action="store_true",
        dest="show_diagnostics",
        help="Include diagnostics footer in JSON output",
    )

    args = parser.parse_args()

    warn_if_not_venv()
    report_data = analyze_portfolio(args.file_path)

    if "error" in report_data:
        for line in error_lines(report_data):
            print(line, file=sys.stderr)
        print(json.dumps(report_data, indent=2), file=sys.stderr)
        sys.exit(1)

    if args.show_diagnostics:
        report_data["diagnostics_footer"] = build_diagnostics_footer(report_data)

    print(json.dumps(report_data, indent=2))
