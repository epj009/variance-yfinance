"""
Centralized configuration loading for Variance.
"""

import copy
import json
import os
import sys
import warnings
from pathlib import Path
from typing import Any, Optional, TypedDict, cast

# Safe import for strategy_loader to satisfy static analysis
try:
    from . import strategy_loader
except ImportError:
    strategy_loader = None  # type: ignore

CONFIG_DIR_ENV = "VARIANCE_CONFIG_DIR"
STRICT_ENV = "VARIANCE_STRICT_CONFIG"
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
RUNTIME_CONFIG_FILE = "runtime_config.json"


class ConfigBundle(TypedDict):
    trading_rules: dict[str, Any]
    market_config: dict[str, Any]
    system_config: dict[str, Any]
    screener_profiles: dict[str, Any]
    strategies: dict[str, dict[str, Any]]


_BUNDLE_CACHE: dict[tuple[str, bool], ConfigBundle] = {}


def _resolve_config_dir(config_dir: Optional[str]) -> Path:
    if config_dir:
        return Path(config_dir)
    env_dir = os.getenv(CONFIG_DIR_ENV)
    if env_dir:
        return Path(env_dir)
    return DEFAULT_CONFIG_DIR


def _resolve_strict(strict: Optional[bool]) -> bool:
    if strict is not None:
        return strict
    env = os.getenv(STRICT_ENV, "")
    return env.lower() in {"1", "true", "yes", "on"}


def _load_json(path: Path, *, strict: bool) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as exc:
        if strict:
            raise FileNotFoundError(f"Missing config file: {path}") from exc
        print(f"Warning: {path} not found.", file=sys.stderr)
        return {}
    except json.JSONDecodeError as exc:
        if strict:
            raise ValueError(f"Malformed config file: {path} ({exc})") from exc
        print(f"Warning: {path} is malformed ({exc}).", file=sys.stderr)
        return {}


def _ensure_dict(payload: Any, *, name: str, strict: bool) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    msg = f"Expected {name} to be an object."
    if strict:
        raise ValueError(msg)
    print(f"Warning: {msg}", file=sys.stderr)
    return {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_runtime_config(
    *, config_dir: Optional[str] = None, strict: Optional[bool] = None
) -> dict[str, Any]:
    config_path = _resolve_config_dir(config_dir) / RUNTIME_CONFIG_FILE
    payload = _load_json(config_path, strict=_resolve_strict(strict))
    return _ensure_dict(payload, name=RUNTIME_CONFIG_FILE, strict=_resolve_strict(strict))


def _extract_section(runtime_config: dict[str, Any], key: str, *, strict: bool) -> dict[str, Any]:
    if not runtime_config:
        return {}
    if key not in runtime_config:
        msg = f"Missing '{key}' section in {RUNTIME_CONFIG_FILE}."
        if strict:
            raise ValueError(msg)
        print(f"Warning: {msg}", file=sys.stderr)
        return {}
    section = runtime_config.get(key)
    if isinstance(section, dict):
        return section
    msg = f"Expected {RUNTIME_CONFIG_FILE}.{key} to be an object."
    if strict:
        raise ValueError(msg)
    print(f"Warning: {msg}", file=sys.stderr)
    return {}


def load_trading_rules(
    *, config_dir: Optional[str] = None, strict: Optional[bool] = None
) -> dict[str, Any]:
    config_path = _resolve_config_dir(config_dir) / "trading_rules.json"
    payload = _load_json(config_path, strict=_resolve_strict(strict))
    rules = _ensure_dict(payload, name="trading_rules.json", strict=_resolve_strict(strict))

    # Deprecation warning for redundant parameter
    if "tastytrade_iv_percentile_floor" in rules:
        warnings.warn(
            "Config parameter 'tastytrade_iv_percentile_floor' is deprecated and will be "
            "removed in Variance v2.0. Use 'min_iv_percentile' instead. "
            "The two parameters are functionally identical.",
            DeprecationWarning,
            stacklevel=2,
        )

    return rules


def load_market_config(
    *, config_dir: Optional[str] = None, strict: Optional[bool] = None
) -> dict[str, Any]:
    strict_flag = _resolve_strict(strict)
    runtime_config = load_runtime_config(config_dir=config_dir, strict=strict_flag)
    return _extract_section(runtime_config, "market", strict=strict_flag)


def load_system_config(
    *, config_dir: Optional[str] = None, strict: Optional[bool] = None
) -> dict[str, Any]:
    strict_flag = _resolve_strict(strict)
    runtime_config = load_runtime_config(config_dir=config_dir, strict=strict_flag)
    return _extract_section(runtime_config, "system", strict=strict_flag)


def load_strategies(
    *, config_dir: Optional[str] = None, strict: Optional[bool] = None
) -> dict[str, dict[str, Any]]:
    config_path = _resolve_config_dir(config_dir) / "strategies.json"
    if strategy_loader and hasattr(strategy_loader, "load_strategies"):
        return strategy_loader.load_strategies(str(config_path), strict=_resolve_strict(strict))

    # Fallback if strategy_loader is missing (should not happen in prod)
    payload = _load_json(config_path, strict=_resolve_strict(strict))
    return _ensure_dict(payload, name="strategies.json", strict=_resolve_strict(strict))


def load_config_bundle(
    *,
    config_dir: Optional[str] = None,
    strict: Optional[bool] = None,
    overrides: Optional[dict[str, Any]] = None,
) -> ConfigBundle:
    strict_flag = _resolve_strict(strict)
    config_path = _resolve_config_dir(config_dir)
    cache_key = (str(config_path), strict_flag)
    if overrides is None and cache_key in _BUNDLE_CACHE:
        return copy.deepcopy(_BUNDLE_CACHE[cache_key])

    runtime_config = load_runtime_config(config_dir=str(config_path), strict=strict_flag)

    bundle: ConfigBundle = {
        "trading_rules": load_trading_rules(config_dir=str(config_path), strict=strict_flag),
        "market_config": _extract_section(runtime_config, "market", strict=strict_flag),
        "system_config": _extract_section(runtime_config, "system", strict=strict_flag),
        "screener_profiles": _extract_section(
            runtime_config, "screener_profiles", strict=strict_flag
        ),
        "strategies": load_strategies(config_dir=str(config_path), strict=strict_flag),
    }

    if overrides:
        # Cast bundle to dict for deep_merge, then back to ConfigBundle
        merged_dict = _deep_merge(cast(dict[str, Any], bundle), overrides)
        bundle = cast(ConfigBundle, merged_dict)

    if overrides is None:
        _BUNDLE_CACHE[cache_key] = copy.deepcopy(bundle)

    return bundle
