"""
Unit tests for the Action Recommendation (Command) Pattern.
"""

import pytest
from variance.models.actions import ActionFactory, HarvestCommand, ToxicCommand, ActionCommand


def test_action_factory_creation():
    # Valid types
    harvest = ActionFactory.create("HARVEST", "AAPL", "Profit target hit")
    assert isinstance(harvest, HarvestCommand)
    assert harvest.symbol == "AAPL"
    assert harvest.action_code == "HARVEST"
    assert harvest.logic == "Profit target hit"
    
    toxic = ActionFactory.create("TOXIC", "TSLA", "Theta leakage")
    assert isinstance(toxic, ToxicCommand)
    assert toxic.action_code == "TOXIC"

def test_action_factory_case_insensitivity():
    cmd = ActionFactory.create("harvest", "NVDA", "logic")
    assert isinstance(cmd, HarvestCommand)

def test_action_factory_invalid_code():
    assert ActionFactory.create("INVALID_CODE", "X", "Y") is None
    assert ActionFactory.create(None, "X", "Y") is None

def test_action_command_serialization():
    cmd = ActionFactory.create("HARVEST", "GLD", "50% reached")
    assert cmd is not None
    data = cmd.to_dict()
    
    assert data["action_code"] == "HARVEST"
    assert data["logic"] == "50% reached"

def test_action_command_immutability():
    cmd = ActionFactory.create("HARVEST", "GLD", "logic")
    assert cmd is not None
    with pytest.raises(AttributeError):
        # Frozen dataclass should prevent modification
        cmd.symbol = "NEW_SYM" # type: ignore
