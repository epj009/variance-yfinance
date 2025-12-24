"""
Abstract Triage Handler

Defines the contract for individual triage rules in the Chain of Responsibility.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class TriageHandler(ABC):
    """Abstract handler in the Chain of Responsibility."""

    def __init__(self, rules: Dict[str, Any]):
        self.rules = rules
        self._next: Optional["TriageHandler"] = None

    def set_next(self, handler: "TriageHandler") -> "TriageHandler":
        """Sets the next handler in the chain. Returns the next handler for chaining."""
        self._next = handler
        return handler

    @abstractmethod
    def handle(self, request: Any) -> Any:
        """
        Process the request and add tags if conditions match.

        IMPORTANT: This is a COLLECTOR pattern - always pass to next handler.
        Do NOT short-circuit.
        """
        pass

    def _pass_to_next(self, request: Any) -> Any:
        """ALWAYS pass request to next handler (collector pattern)."""
        if self._next:
            return self._next.handle(request)
        return request