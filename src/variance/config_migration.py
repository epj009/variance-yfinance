"""
Config Migration Layer for Backward Compatibility

Handles migration of deprecated config keys to new keys with warnings.
Part of ADR-0014 (Compression Ratio → Volatility Trend Ratio rename).
"""

import warnings
from typing import Any

# Config key mappings: old_key -> new_key
CONFIG_KEY_MIGRATIONS = {
    "compression_coiled_threshold": "vtr_coiled_threshold",
    "vol_trap_compression_threshold": "vol_trap_vtr_threshold",
}


def migrate_config_keys(config: dict[str, Any]) -> dict[str, Any]:
    """
    Migrate old config keys to new ones with deprecation warnings.

    Creates a new dict with updated keys. Original dict is not modified.

    Args:
        config: Original config dictionary

    Returns:
        New config dict with migrated keys
    """
    migrated = dict(config)

    for old_key, new_key in CONFIG_KEY_MIGRATIONS.items():
        if old_key in migrated:
            # Only warn if the new key doesn't already exist
            if new_key not in migrated:
                warnings.warn(
                    f"Config key '{old_key}' is deprecated. "
                    f"Use '{new_key}' instead. "
                    f"Support for '{old_key}' will be removed in v2.0.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                migrated[new_key] = migrated[old_key]

    return migrated


def get_config_value(
    config: dict[str, Any], new_key: str, old_key: str, default: Any = None
) -> Any:
    """
    Get config value, preferring new key, falling back to old key with warning.

    Retrieval priority:
    1. New key (no warning)
    2. Old key (with deprecation warning)
    3. Default value

    Args:
        config: Config dictionary
        new_key: New/preferred config key
        old_key: Deprecated config key
        default: Default value if neither key exists

    Returns:
        Config value or default
    """
    # Prefer new key (no warning)
    if new_key in config:
        return config[new_key]

    # Fall back to old key with warning
    if old_key in config:
        warnings.warn(
            f"Config key '{old_key}' is deprecated. "
            f"Use '{new_key}' instead. "
            f"Support for '{old_key}' will be removed in v2.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        return config[old_key]

    # Neither key exists, return default
    return default
