"""
TUI Tag Renderer

Transforms triage tags into formatted Rich text badges.
"""

import re
from typing import Any, Optional

from rich.text import Text


class TagRenderer:
    """Renders triage tags as colored badges for the terminal."""

    TAG_ICONS = {
        "EXPIRING": "⏳",
        "HARVEST": "💰",
        "SIZE_THREAT": "🐳",
        "DEFENSE": "🛡️",
        "GAMMA": "☢️",
        "HEDGE_CHECK": "🌳",
        "TOXIC": "💀",
        "EARNINGS_WARNING": "📅",
        "SCALABLE": "➕",
        "SLOW_THETA": "🐌",
        "WILD_PL": "🎢",
    }

    TAG_COLORS = {
        "EXPIRING": "bold yellow",
        "HARVEST": "bold green",
        "SIZE_THREAT": "bold red",
        "DEFENSE": "bold red",
        "GAMMA": "bold magenta",
        "HEDGE_CHECK": "green",
        "TOXIC": "bold red",
        "EARNINGS_WARNING": "bold yellow",
        "SCALABLE": "bold cyan",
        "SLOW_THETA": "dim yellow",
        "WILD_PL": "dim magenta",
    }

    def __init__(self, display_rules: Optional[dict[str, Any]] = None):
        self.rules = display_rules or {}
        self.max_secondary = self.rules.get("max_secondary_tags", 3)

    def render_tags(self, tags: list[dict[str, Any]]) -> Text:
        """Renders a list of tag dictionaries into a single Rich Text object."""
        if not tags:
            return Text()

        # Sort by priority
        sorted_tags = sorted(tags, key=lambda x: x.get("priority", 999))

        result = Text()

        # Primary Tag (First) - Always Bracketed
        primary = sorted_tags[0]
        result.append(" [", style="white")
        result.append(self._render_badge(primary, is_primary=True))
        result.append("]", style="white")

        # Secondary Tags
        for tag in sorted_tags[1 : self.max_secondary + 1]:
            result.append(" ")
            result.append(self._render_badge(tag, is_primary=False))

        return result

    def _render_badge(self, tag: dict[str, Any], is_primary: bool) -> Text:
        tag_type = tag.get("type", "UNKNOWN")
        icon = self.TAG_ICONS.get(tag_type, "•")
        color = self.TAG_COLORS.get(tag_type, "white")

        if is_primary:
            # Extract specific values (e.g. "60.0%") from logic for the badge
            val = self._extract_value(tag.get("logic", ""))
            label = f"{icon} {tag_type}"
            if val:
                label += f" {val}"
            return Text(label, style=color)
        else:
            # Compact secondary badge
            abbrev = self._abbreviate(tag_type)
            return Text(f"[{abbrev}]", style=f"dim {color.replace('bold ', '')}")

    def _extract_value(self, logic: str) -> Optional[str]:
        match = re.search(r"(\d+\.?\d*%)", logic)
        return match.group(1) if match else None

    def _abbreviate(self, tag_type: str) -> str:
        abbrevs = {
            "GAMMA": "γ",
            "EARNINGS_WARNING": "ERN",
            "SIZE_THREAT": "SIZE",
            "HEDGE_CHECK": "HDG",
            "SLOW_THETA": "θ↓",
            "WILD_PL": "P/L~",
        }
        return abbrevs.get(tag_type, tag_type[:3])
