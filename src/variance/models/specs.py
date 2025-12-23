"""
Specification Pattern Implementation

Allows for complex, composable filtering of market candidates.
Used to decouple screening logic from the core execution loop.
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")


class Specification(ABC, Generic[T]):
    """Abstract base class for all specifications."""

    @abstractmethod
    def is_satisfied_by(self, candidate: T) -> bool:
        """Returns True if the candidate satisfies the specification."""
        pass

    def __and__(self, other: "Specification[T]") -> "AndSpecification[T]":
        return AndSpecification(self, other)

    def __or__(self, other: "Specification[T]") -> "OrSpecification[T]":
        return OrSpecification(self, other)

    def __invert__(self) -> "NotSpecification[T]":
        return NotSpecification(self)


class AndSpecification(Specification[T]):
    """Composite specification that requires all child specs to pass."""

    def __init__(self, *specs: Specification[T]):
        self.specs = specs

    def is_satisfied_by(self, candidate: T) -> bool:
        return all(spec.is_satisfied_by(candidate) for spec in self.specs)


class OrSpecification(Specification[T]):
    """Composite specification that requires at least one child spec to pass."""

    def __init__(self, *specs: Specification[T]):
        self.specs = specs

    def is_satisfied_by(self, candidate: T) -> bool:
        return any(spec.is_satisfied_by(candidate) for spec in self.specs)


class NotSpecification(Specification[T]):
    """Negates the result of a child specification."""

    def __init__(self, spec: Specification[T]):
        self.spec = spec

    def is_satisfied_by(self, candidate: T) -> bool:
        return not self.spec.is_satisfied_by(candidate)
