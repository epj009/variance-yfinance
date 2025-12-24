"""
Enrichment Strategy Base

Defines the contract for pluggable candidate enrichment.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..pipeline import ScreeningContext


class EnrichmentStrategy(ABC):
    """Abstract base for candidate data enrichment."""

    @abstractmethod
    def enrich(self, candidate: dict[str, Any], ctx: "ScreeningContext") -> None:
        """
        Enrich candidate in-place with calculated metrics.
        """
        pass
