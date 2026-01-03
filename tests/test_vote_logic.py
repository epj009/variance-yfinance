"""
Unit tests for vote calculation logic in report output.
"""

from variance.screening.steps import report


def test_vote_avoid_severe_compression():
    candidate = {
        "score": 75,
        "portfolio_rho": 0.40,
        "Volatility Trend Ratio": 0.52,
    }
    vote = report._determine_vote(candidate, is_held=False)
    assert vote == "AVOID (COILED)"


def test_vote_strong_buy_severe_expansion():
    candidate = {
        "score": 65,
        "portfolio_rho": 0.55,
        "Volatility Trend Ratio": 1.45,
    }
    vote = report._determine_vote(candidate, is_held=False)
    assert vote == "STRONG BUY"


def test_vote_downgrade_mild_compression():
    candidate = {
        "score": 72,
        "portfolio_rho": 0.45,
        "Volatility Trend Ratio": 0.68,
    }
    vote = report._determine_vote(candidate, is_held=False)
    assert vote == "LEAN"
