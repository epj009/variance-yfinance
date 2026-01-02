#!/usr/bin/env python3
"""
Analyze Variance log files.

Usage:
    python scripts/analyze_logs.py --errors
    python scripts/analyze_logs.py --slow-api
    python scripts/analyze_logs.py --session abc123
"""

import argparse
import re
from datetime import datetime, timedelta
from pathlib import Path


def find_errors(log_file: Path, since_hours: int = 24) -> None:
    """Extract errors from log file."""
    cutoff = datetime.now() - timedelta(hours=since_hours)

    if not log_file.exists():
        return

    with log_file.open() as handle:
        for line in handle:
            match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
            if match:
                ts = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
                if ts >= cutoff and "ERROR" in line:
                    print(line.strip())


def find_slow_apis(log_file: Path, threshold_ms: int = 1000) -> None:
    """Find API calls slower than threshold."""
    if not log_file.exists():
        return

    with log_file.open() as handle:
        for line in handle:
            if "API" in line and "completed" in line:
                match = re.search(r"(\d+)ms", line)
                if match and int(match.group(1)) > threshold_ms:
                    print(line.strip())


def filter_by_session(log_file: Path, session_id: str) -> None:
    """Show all logs for a specific session."""
    if not log_file.exists():
        return

    with log_file.open() as handle:
        for line in handle:
            if f"session:{session_id}" in line:
                print(line.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Variance logs")
    parser.add_argument("--errors", action="store_true", help="Show recent errors")
    parser.add_argument("--slow-api", action="store_true", help="Find slow API calls")
    parser.add_argument("--session", help="Filter by session ID")
    parser.add_argument("--since-hours", type=int, default=24, help="Look back N hours")

    args = parser.parse_args()

    log_dir = Path("logs")
    log_file = log_dir / "variance.log"
    error_log = log_dir / "variance-error.log"

    if args.errors:
        find_errors(error_log, args.since_hours)
        return
    if args.slow_api:
        find_slow_apis(log_file, threshold_ms=1000)
        return
    if args.session:
        filter_by_session(log_file, args.session)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
