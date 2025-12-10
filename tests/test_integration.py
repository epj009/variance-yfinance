"""
Integration tests for the full portfolio analysis pipeline.
"""

import pytest
import sys
import os
import json

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from analyze_portfolio import analyze_portfolio


class TestAnalyzePortfolioIntegration:
    """Test the full portfolio analysis pipeline."""

    def test_analyze_portfolio_with_sample_csv(self):
        """Test that the analyzer runs without errors on sample CSV."""
        csv_path = os.path.join(os.path.dirname(__file__), '..', 'util', 'sample_positions.csv')
        
        # Skip if sample file doesn't exist
        if not os.path.exists(csv_path):
            pytest.skip(f"Sample CSV not found at {csv_path}")
        
        result = analyze_portfolio(csv_path)
        
        # Basic structure validation
        assert isinstance(result, dict)
        assert 'analysis_time' in result
        assert 'triage_actions' in result
        assert 'portfolio_overview' in result
        assert 'portfolio_summary' in result
        
        # Verify no error
        assert 'error' not in result

    def test_analyze_portfolio_returns_valid_json(self):
        """Test that the output can be serialized to JSON."""
        csv_path = os.path.join(os.path.dirname(__file__), '..', 'util', 'sample_positions.csv')
        
        if not os.path.exists(csv_path):
            pytest.skip(f"Sample CSV not found at {csv_path}")
        
        result = analyze_portfolio(csv_path)
        
        # Should be JSON serializable
        try:
            json_str = json.dumps(result, indent=2)
            assert len(json_str) > 0
        except (TypeError, ValueError) as e:
            pytest.fail(f"Result is not JSON serializable: {e}")

    def test_analyze_portfolio_missing_file_raises_exception(self):
        """Test error handling for missing CSV file."""
        from portfolio_parser import PortfolioParser
        
        # Parser should raise FileNotFoundError for missing files
        with pytest.raises(FileNotFoundError):
            PortfolioParser.parse('/nonexistent/file.csv')
