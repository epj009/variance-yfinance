#!/usr/bin/env python3
import argparse
import json
import os
import sys

# Allow importing from src without installation (for dev convenience)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from variance.analyze_portfolio import analyze_portfolio
from variance.common import warn_if_not_venv

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analyze current portfolio positions and generate a triage report."
    )
    parser.add_argument("file_path", type=str, help="Path to the portfolio CSV file.")

    args = parser.parse_args()

    warn_if_not_venv()
    report_data = analyze_portfolio(args.file_path)

    if "error" in report_data:
        print(json.dumps(report_data, indent=2), file=sys.stderr)
        sys.exit(1)

    print(json.dumps(report_data, indent=2))
