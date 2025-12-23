import json
import os
import subprocess
import sys

import pytest

# Paths to scripts
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), '../scripts')
ANALYZE_SCRIPT = os.path.join(SCRIPTS_DIR, 'analyze_portfolio.py')
SCREENER_SCRIPT = os.path.join(SCRIPTS_DIR, 'vol_screener.py')
PYTHON_EXE = sys.executable

def test_analyze_portfolio_cli_default_json(tmp_path):
    """Test that analyze_portfolio.py defaults to JSON output."""
    # Create dummy CSV
    csv_path = tmp_path / "positions.csv"
    csv_path.write_text(
        "Symbol,Type,Quantity,Exp Date,DTE,Strike Price,Call/Put,Underlying Last Price,P/L Open,Cost,Beta Delta,Theta,Bid,Ask\n"
        "AAPL,Option,-1,2025-01-17,30,150,Put,150,0,-100,0,5,1.00,1.10\n"
    )

    result = subprocess.run(
        [PYTHON_EXE, ANALYZE_SCRIPT, str(csv_path)],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")

    assert result.returncode == 0
    # Output should be parsable JSON
    try:
        data = json.loads(result.stdout)
        assert "triage_actions" in data
        assert "portfolio_summary" in data
    except json.JSONDecodeError:
        pytest.fail(f"Output was not valid JSON: {result.stdout[:200]}...")

def test_vol_screener_cli_default_json():
    """Test that vol_screener.py defaults to JSON output."""
    # We use a small limit to speed it up and reduce network reliance logic (though it will mock network if we mock it,
    # but subprocess runs a new process so mocking is harder.
    # For now, we assume the script handles network errors gracefully or has fallback.)

    # We can pass a limit to avoid hitting the whole watchlist
    result = subprocess.run(
        [PYTHON_EXE, SCREENER_SCRIPT, "1", "--profile", "balanced"],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0
    try:
        data = json.loads(result.stdout)
        assert "candidates" in data
        assert "summary" in data
    except json.JSONDecodeError:
        pytest.fail(f"Output was not valid JSON: {result.stdout[:200]}...")
