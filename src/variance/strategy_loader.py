import json
import sys
from typing import Any


def validate_strategy(strategy: dict[str, Any]) -> bool:
    """
    Validate a strategy object has required fields and correct types.
    Returns True if valid, False otherwise.
    """
    # 1. Check required top-level fields
    required_fields = ["id", "name", "type", "setup", "management"]
    for field in required_fields:
        if field not in strategy:
            return False

    # 2. Check Type constraint
    if strategy["type"] not in ["defined_risk", "undefined_risk"]:
        return False

    # 3. Check Management fields
    mgmt = strategy.get("management", {})
    if "profit_target_pct" not in mgmt:
        return False

    pt = mgmt["profit_target_pct"]
    # Ensure profit target is a float between 10% and 100%
    if not isinstance(pt, (float, int)) or not (0.1 <= pt <= 1.0):
        return False

    # 4. Check Metadata fields
    meta = strategy.get("metadata", {})
    if "gamma_trigger_dte" not in meta:
        return False

    gamma_dte = meta["gamma_trigger_dte"]
    # Ensure gamma trigger is a positive integer
    return not (not isinstance(gamma_dte, int) or gamma_dte <= 0)


def load_strategies(
    filepath: str = "config/strategies.json", *, strict: bool = False
) -> dict[str, dict[str, Any]]:
    """
    Load strategy configurations from config/strategies.json.
    Returns a dict keyed by strategy_id for fast lookup.
    """
    strategies = {}
    try:
        with open(filepath) as f:
            data = json.load(f)

        for strat in data:
            if validate_strategy(strat):
                strategies[strat["id"]] = strat
            else:
                # Log invalid strategy but continue loading others
                print(
                    f"Warning: Skipping invalid strategy config: {strat.get('id', 'unknown')}",
                    file=sys.stderr,
                )

    except FileNotFoundError:
        message = f"{filepath} not found. Strategy specific parameters will be unavailable."
        if strict:
            raise FileNotFoundError(message)
        print(f"Warning: {message}", file=sys.stderr)
    except json.JSONDecodeError:
        message = f"Failed to parse {filepath}. Check JSON format."
        if strict:
            raise ValueError(message)
        print(f"Error: {message}", file=sys.stderr)
    except Exception as e:
        if strict:
            raise
        print(f"Error loading strategies: {e}", file=sys.stderr)

    return strategies
