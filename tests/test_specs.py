"""
Unit tests for the Specification Pattern implementation.
"""

from variance.models.market_specs import LowVolTrapSpec, SectorExclusionSpec, VrpStructuralSpec
from variance.models.specs import AndSpecification, NotSpecification, OrSpecification


def test_vrp_structural_spec():
    spec = VrpStructuralSpec(1.0)

    # Passing candidate
    assert spec.is_satisfied_by({"vrp_structural": 1.2}) is True
    # Failing candidate
    assert spec.is_satisfied_by({"vrp_structural": 0.8}) is False
    # Missing data
    assert spec.is_satisfied_by({}) is False


def test_low_vol_trap_spec():
    spec = LowVolTrapSpec(5.0)

    assert spec.is_satisfied_by({"hv252": 10.0}) is True
    assert spec.is_satisfied_by({"hv252": 2.0}) is False
    # Missing data should pass (conservative assumption)
    assert spec.is_satisfied_by({}) is True


def test_sector_exclusion_spec():
    spec = SectorExclusionSpec(["Technology", "Energy"])

    assert spec.is_satisfied_by({"sector": "Healthcare"}) is True
    assert spec.is_satisfied_by({"sector": "Technology"}) is False
    assert spec.is_satisfied_by({"sector": "energy"}) is False  # Case insensitive


def test_specification_and_operator():
    spec_a = VrpStructuralSpec(1.0)
    spec_b = LowVolTrapSpec(5.0)

    combined = spec_a & spec_b

    assert isinstance(combined, AndSpecification)
    assert combined.is_satisfied_by({"vrp_structural": 1.2, "hv252": 10.0}) is True
    assert combined.is_satisfied_by({"vrp_structural": 0.8, "hv252": 10.0}) is False
    assert combined.is_satisfied_by({"vrp_structural": 1.2, "hv252": 2.0}) is False


def test_specification_or_operator():
    spec_a = VrpStructuralSpec(1.5)
    spec_b = SectorExclusionSpec(["Technology"])

    combined = spec_a | spec_b

    assert isinstance(combined, OrSpecification)
    # Passes A
    assert combined.is_satisfied_by({"vrp_structural": 2.0, "sector": "Technology"}) is True
    # Passes B
    assert combined.is_satisfied_by({"vrp_structural": 1.0, "sector": "Healthcare"}) is True
    # Fails both
    assert combined.is_satisfied_by({"vrp_structural": 1.0, "sector": "Technology"}) is False


def test_specification_invert_operator():
    spec = VrpStructuralSpec(1.0)
    inverted = ~spec

    assert isinstance(inverted, NotSpecification)
    assert inverted.is_satisfied_by({"vrp_structural": 0.8}) is True
    assert inverted.is_satisfied_by({"vrp_structural": 1.2}) is False
