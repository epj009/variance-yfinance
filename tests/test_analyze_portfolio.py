from variance import analyze_portfolio
from variance.portfolio_parser import PortfolioParser
from variance.strategy_detector import identify_strategy


# Mocking leg data helpers
def make_leg(otype, qty, strike):
    return {
        "Type": "Option",
        "Call/Put": otype,
        "Quantity": str(qty),
        "Strike Price": str(strike),
        "Exp Date": "2025-01-17",
        "DTE": "45",
    }


def make_stock_leg(qty):
    return {
        "Type": "Stock",
        "Call/Put": "",
        "Quantity": str(qty),
        "Strike Price": "",
        "Exp Date": "",
        "DTE": "",
    }


def make_config_bundle(trading_rules):
    return {
        "trading_rules": trading_rules,
        "market_config": {},
        "system_config": {},
        "screener_profiles": {},
        "strategies": {},
    }


# --- Strategy Identification Tests ---


def test_identify_short_strangle():
    legs = [make_leg("Call", -1, 110), make_leg("Put", -1, 90)]
    assert identify_strategy(legs) == "Short Strangle"


def test_identify_iron_condor():
    legs = [
        make_leg("Call", -1, 110),
        make_leg("Call", 1, 120),
        make_leg("Put", -1, 90),
        make_leg("Put", 1, 80),
    ]
    assert identify_strategy(legs) == "Iron Condor"


def test_identify_iron_butterfly():
    legs = [
        make_leg("Call", -1, 100),
        make_leg("Put", -1, 100),
        make_leg("Call", 1, 110),
        make_leg("Put", 1, 90),
    ]
    assert identify_strategy(legs) == "Iron Fly"


def test_identify_vertical_call_spread():
    legs = [make_leg("Call", -1, 100), make_leg("Call", 1, 110)]
    assert identify_strategy(legs) == "Vertical Spread (Call)"


def test_identify_covered_call():
    legs = [make_stock_leg(100), make_leg("Call", -1, 110)]
    assert identify_strategy(legs) == "Covered Call"


def test_identify_jade_lizard():
    # Short Put + Short Call Spread
    legs = [make_leg("Put", -1, 90), make_leg("Call", -1, 110), make_leg("Call", 1, 120)]
    assert identify_strategy(legs) == "Jade Lizard"


def test_identify_single_long_call():
    legs = [make_leg("Call", 1, 100)]
    assert identify_strategy(legs) == "Long Call"


def test_identify_unknown_combo():
    # Just a random mix that doesn't fit standard definitions
    legs = [make_leg("Call", 1, 100), make_leg("Put", 1, 90), make_leg("Call", -1, 120)]
    # Should result in Custom/Combo since it doesn't match strict 2, 3, 4 leg templates perfectly
    # Actually, let's trace logic: 3 legs.
    # Twisted Sister: Short Call + Put Credit Spread (1 Short Call, 1 Short Put, 1 Long Put)
    # Jade Lizard: Short Put + Call Credit Spread (1 Short Put, 1 Short Call, 1 Long Call)
    # This mock: 1 Long Call, 1 Long Put, 1 Short Call.
    # It likely falls through to "Custom/Combo"
    assert identify_strategy(legs) == "Custom/Combo"


# --- Parser Normalization Tests ---


def test_normalize_row_tasty_style():
    row = {
        "Symbol": "XYZ",
        "Type": "Option",
        "Call/Put": "CALL",
        "Strike Price": "100",
        "Quantity": "-1",
        "Exp Date": "1/17/25",
        "DTE": "45",
    }
    normalized = PortfolioParser.normalize_row(row)
    assert normalized["Symbol"] == "XYZ"
    assert normalized["Type"] == "Option"
    assert normalized["Call/Put"] == "Call"
    assert normalized["Quantity"] == "-1"


def test_normalize_row_put_lowercase():
    row = {
        "Symbol": "ABC",
        "Type": "Option",
        "Call/Put": "put",
        "Strike Price": "50",
        "Quantity": "1",
        "Exp Date": "1/17/25",
        "DTE": "45",
    }
    normalized = PortfolioParser.normalize_row(row)
    assert normalized["Call/Put"] == "Put"


# --- Integration-style logic tests with stubbed market data (no network) ---

from variance.get_market_data import MarketDataFactory


def test_analyze_portfolio_harvest_action(monkeypatch, tmp_path, mock_market_provider):
    # Stub market data
    fake_data = {
        "ABC": {
            "price": 100.0,
            "is_stale": False,
            "vrp_structural": 1.2,
            "earnings_date": None,
            "sector": "Technology",
        },
        "SPY": {
            "price": 450.0,
            "is_stale": False,
            "vrp_structural": 1.1,
            "iv": 15.0,
            "earnings_date": None,
            "sector": "Index",
        },
    }

    mock_provider = mock_market_provider(fake_data)
    monkeypatch.setattr(MarketDataFactory, "get_provider", lambda type="yfinance": mock_provider)

    # Create dummy CSV
    csv_path = tmp_path / "positions.csv"
    csv_path.write_text(
        "Symbol,Type,Quantity,Exp Date,DTE,Strike Price,Call/Put,Underlying Last Price,P/L Open,Cost,Beta Delta,Theta\n"
        "ABC,Option,-1,2025-01-17,45,100,Put,100,50,-100,-10,5\n"
    )

    result = analyze_portfolio.analyze_portfolio(str(csv_path))

    # Check for HARVEST action (Profit 50% on cost -100 is +50)
    assert len(result["triage_actions"]) == 1
    assert result["triage_actions"][0]["action_code"] == "HARVEST"


def test_asset_mix_calculation_equity_heavy(tmp_path, monkeypatch, mock_market_provider):
    """Test that asset mix correctly identifies equity-heavy portfolios."""
    # Stub market data: AAPL, TSLA, NVDA (Technology = Equity), GLD (Metals = Commodity)
    fake_data = {
        "AAPL": {
            "price": 150.0,
            "sector": "Technology",
            "iv30": 30.0,
            "hv252": 40.0,
            "vrp_structural": 0.75,
        },
        "TSLA": {
            "price": 200.0,
            "sector": "Technology",
            "iv30": 50.0,
            "hv252": 60.0,
            "vrp_structural": 0.83,
        },
        "NVDA": {
            "price": 450.0,
            "sector": "Technology",
            "iv30": 45.0,
            "hv252": 50.0,
            "vrp_structural": 0.90,
        },
        "AMZN": {
            "price": 140.0,
            "sector": "Consumer Cyclical",
            "iv30": 35.0,
            "hv252": 40.0,
            "vrp_structural": 0.88,
        },
        "GLD": {
            "price": 180.0,
            "sector": "Metals",
            "iv30": 20.0,
            "hv252": 15.0,
            "vrp_structural": 1.33,
        },
        "SPY": {
            "price": 450.0,
            "sector": "Index",
            "iv": 15.0,
            "hv252": 14.0,
            "vrp_structural": 1.07,
        },
    }

    mock_provider = mock_market_provider(fake_data)
    monkeypatch.setattr(MarketDataFactory, "get_provider", lambda type="yfinance": mock_provider)
    config_bundle = make_config_bundle(
        {
            "vrp_structural_threshold": 0.85,
            "dead_money_vrp_structural_threshold": 0.80,
            "dead_money_pl_pct_low": -0.10,
            "dead_money_pl_pct_high": 0.10,
            "gamma_dte_threshold": 21,
            "profit_harvest_pct": 0.50,
            "earnings_days_threshold": 5,
            "portfolio_delta_long_threshold": 75,
            "portfolio_delta_short_threshold": -50,
            "concentration_risk_pct": 0.25,
            "net_liquidity": 100000,
            "beta_weighted_symbol": "SPY",
            "global_staleness_threshold": 0.50,
            "data_integrity_min_theta": 0.50,
            "asset_mix_equity_threshold": 0.80,
            "concentration_limit_pct": 0.05,
            "max_strategies_per_symbol": 3,
            "theta_efficiency_low": 0.1,
            "theta_efficiency_high": 0.5,
            "stress_scenarios": [
                {"label": "Crash (-5%)", "move_pct": -0.05},
                {"label": "Flat", "move_pct": 0.0},
                {"label": "Rally (+5%)", "move_pct": 0.05},
            ],
            "hedge_rules": {"enabled": False},
        }
    )

    csv_path = tmp_path / "positions.csv"
    csv_path.write_text(
        "Symbol,Type,Quantity,Exp Date,DTE,Strike Price,Call/Put,Underlying Last Price,P/L Open,Cost,Beta Delta,Theta\n"
        "AAPL,Option,-1,2025-01-17,30,150,Put,150,10,-50,5,1\n"
        "TSLA,Option,-1,2025-01-17,30,200,Call,200,10,-50,5,1\n"
        "NVDA,Option,-1,2025-01-17,30,450,Put,450,10,-50,5,1\n"
        "AMZN,Option,-1,2025-01-17,30,140,Put,140,10,-50,5,1\n"
        "GLD,Option,-1,2025-01-17,30,180,Put,180,10,-50,5,1\n"
    )

    report = analyze_portfolio.analyze_portfolio(str(csv_path), config=config_bundle)
    assert not report.get("error")

    # Check asset mix exists
    assert "asset_mix" in report
    assert len(report["asset_mix"]) > 0

    # Find Equity percentage (4 out of 5 positions = 80%)
    equity_item = next(
        (item for item in report["asset_mix"] if item["asset_class"] == "Equity"), None
    )
    assert equity_item is not None
    assert equity_item["count"] == 4
    assert equity_item["percentage"] == 0.8

    # Check warning is triggered (> 80%)
    assert not report["asset_mix_warning"]["risk"]  # Exactly 80%, not > 80%


def test_asset_mix_calculation_equity_warning(tmp_path, monkeypatch, mock_market_provider):
    """Test that asset mix warning triggers when equity > 80%."""
    fake_data = {
        "AAPL": {
            "price": 150.0,
            "sector": "Technology",
            "iv30": 30.0,
            "hv252": 40.0,
            "vrp_structural": 0.75,
        },
        "TSLA": {
            "price": 200.0,
            "sector": "Technology",
            "iv30": 50.0,
            "hv252": 60.0,
            "vrp_structural": 0.83,
        },
        "NVDA": {
            "price": 450.0,
            "sector": "Technology",
            "iv30": 45.0,
            "hv252": 50.0,
            "vrp_structural": 0.90,
        },
        "AMZN": {
            "price": 140.0,
            "sector": "Healthcare",
            "iv30": 35.0,
            "hv252": 40.0,
            "vrp_structural": 0.88,
        },
        "MSFT": {
            "price": 380.0,
            "sector": "Technology",
            "iv30": 32.0,
            "hv252": 38.0,
            "vrp_structural": 0.84,
        },
        "GLD": {
            "price": 180.0,
            "sector": "Metals",
            "iv30": 20.0,
            "hv252": 15.0,
            "vrp_structural": 1.33,
        },
        "SPY": {
            "price": 450.0,
            "sector": "Index",
            "iv": 15.0,
            "hv252": 14.0,
            "vrp_structural": 1.07,
        },
    }

    mock_provider = mock_market_provider(fake_data)
    monkeypatch.setattr(MarketDataFactory, "get_provider", lambda type="yfinance": mock_provider)
    config_bundle = make_config_bundle(
        {
            "vrp_structural_threshold": 0.85,
            "dead_money_vrp_structural_threshold": 0.80,
            "dead_money_pl_pct_low": -0.10,
            "dead_money_pl_pct_high": 0.10,
            "gamma_dte_threshold": 21,
            "profit_harvest_pct": 0.50,
            "earnings_days_threshold": 5,
            "portfolio_delta_long_threshold": 75,
            "portfolio_delta_short_threshold": -50,
            "concentration_risk_pct": 0.25,
            "net_liquidity": 100000,
            "beta_weighted_symbol": "SPY",
            "global_staleness_threshold": 0.50,
            "data_integrity_min_theta": 0.50,
            "asset_mix_equity_threshold": 0.80,
            "concentration_limit_pct": 0.05,
            "max_strategies_per_symbol": 3,
            "theta_efficiency_low": 0.1,
            "theta_efficiency_high": 0.5,
            "stress_scenarios": [
                {"label": "Crash (-5%)", "move_pct": -0.05},
                {"label": "Flat", "move_pct": 0.0},
                {"label": "Rally (+5%)", "move_pct": 0.05},
            ],
            "hedge_rules": {"enabled": False},
        }
    )

    csv_path = tmp_path / "positions.csv"
    csv_path.write_text(
        "Symbol,Type,Quantity,Exp Date,DTE,Strike Price,Call/Put,Underlying Last Price,P/L Open,Cost,Beta Delta,Theta\n"
        "AAPL,Option,-1,2025-01-17,30,150,Put,150,10,-50,5,1\n"
        "TSLA,Option,-1,2025-01-17,30,200,Call,200,10,-50,5,1\n"
        "NVDA,Option,-1,2025-01-17,30,450,Put,450,10,-50,5,1\n"
        "AMZN,Option,-1,2025-01-17,30,140,Put,140,10,-50,5,1\n"
        "MSFT,Option,-1,2025-01-17,30,380,Put,380,10,-50,5,1\n"
        "GLD,Option,-1,2025-01-17,30,180,Put,180,10,-50,5,1\n"
    )

    report = analyze_portfolio.analyze_portfolio(str(csv_path), config=config_bundle)
    assert not report.get("error")

    # 5 Equity out of 6 = 83.33% > 80%
    equity_item = next(
        (item for item in report["asset_mix"] if item["asset_class"] == "Equity"), None
    )
    assert equity_item is not None
    assert equity_item["count"] == 5
    assert equity_item["percentage"] > 0.80

    # Check warning is triggered
    assert report["asset_mix_warning"]["risk"]
    assert (
        "83%" in report["asset_mix_warning"]["details"]
        or "Equity" in report["asset_mix_warning"]["details"]
    )


def test_asset_mix_diversified(tmp_path, monkeypatch, mock_market_provider):
    """Test that diversified portfolios don't trigger warnings."""
    fake_data = {
        "AAPL": {
            "price": 150.0,
            "sector": "Technology",
            "iv30": 30.0,
            "hv252": 40.0,
            "vrp_structural": 0.75,
        },
        "GLD": {
            "price": 180.0,
            "sector": "Metals",
            "iv30": 20.0,
            "hv252": 15.0,
            "vrp_structural": 1.33,
        },
        "/CL": {
            "price": 70.0,
            "sector": "Energy",
            "iv30": 40.0,
            "hv252": 35.0,
            "vrp_structural": 1.14,
        },
        "/6E": {
            "price": 1.1,
            "sector": "Currencies",
            "iv30": 10.0,
            "hv252": 8.0,
            "vrp_structural": 1.25,
        },
        "TLT": {
            "price": 95.0,
            "sector": "Fixed Income",
            "iv30": 12.0,
            "hv252": 10.0,
            "vrp_structural": 1.20,
        },
        "SPY": {
            "price": 450.0,
            "sector": "Index",
            "iv": 15.0,
            "hv252": 14.0,
            "vrp_structural": 1.07,
        },
    }

    mock_provider = mock_market_provider(fake_data)
    monkeypatch.setattr(MarketDataFactory, "get_provider", lambda type="yfinance": mock_provider)
    config_bundle = make_config_bundle(
        {
            "vrp_structural_threshold": 0.85,
            "dead_money_vrp_structural_threshold": 0.80,
            "dead_money_pl_pct_low": -0.10,
            "dead_money_pl_pct_high": 0.10,
            "gamma_dte_threshold": 21,
            "profit_harvest_pct": 0.50,
            "earnings_days_threshold": 5,
            "portfolio_delta_long_threshold": 75,
            "portfolio_delta_short_threshold": -50,
            "concentration_risk_pct": 0.25,
            "net_liquidity": 100000,
            "beta_weighted_symbol": "SPY",
            "global_staleness_threshold": 0.50,
            "data_integrity_min_theta": 0.50,
            "asset_mix_equity_threshold": 0.80,
            "concentration_limit_pct": 0.05,
            "max_strategies_per_symbol": 3,
            "theta_efficiency_low": 0.1,
            "theta_efficiency_high": 0.5,
            "stress_scenarios": [
                {"label": "Crash (-5%)", "move_pct": -0.05},
                {"label": "Flat", "move_pct": 0.0},
                {"label": "Rally (+5%)", "move_pct": 0.05},
            ],
            "hedge_rules": {"enabled": False},
        }
    )

    csv_path = tmp_path / "positions.csv"
    csv_path.write_text(
        "Symbol,Type,Quantity,Exp Date,DTE,Strike Price,Call/Put,Underlying Last Price,P/L Open,Cost,Beta Delta,Theta\n"
        "AAPL,Option,-1,2025-01-17,30,150,Put,150,10,-50,5,1\n"
        "GLD,Option,-1,2025-01-17,30,180,Put,180,10,-50,5,1\n"
        "/CL,Option,-1,2025-01-17,30,70,Call,70,10,-50,5,1\n"
        "/6E,Option,-1,2025-01-17,30,1.1,Put,1.1,10,-50,5,1\n"
        "TLT,Option,-1,2025-01-17,30,95,Put,95,10,-50,5,1\n"
    )

    report = analyze_portfolio.analyze_portfolio(str(csv_path), config=config_bundle)
    assert not report.get("error")

    # Should have 4 asset classes (Equity, Commodity x2, FX, Fixed Income)
    # Note: GLD (Metals) and /CL (Energy) both map to Commodity
    assert len(report["asset_mix"]) == 4

    # Find each asset class
    asset_classes_found = {item["asset_class"] for item in report["asset_mix"]}
    assert "Equity" in asset_classes_found
    assert "Commodity" in asset_classes_found
    assert "FX" in asset_classes_found
    assert "Fixed Income" in asset_classes_found

    # No single asset class should be > 80%
    for item in report["asset_mix"]:
        assert item["percentage"] <= 0.80

    # Commodity should be 40% (2 out of 5 positions)
    commodity_item = next(
        (item for item in report["asset_mix"] if item["asset_class"] == "Commodity"), None
    )
    assert commodity_item is not None
    assert commodity_item["count"] == 2
    assert commodity_item["percentage"] == 0.4

    # Warning should NOT be triggered
    assert not report["asset_mix_warning"]["risk"]


def test_friction_horizon_calculation(tmp_path, monkeypatch, mock_market_provider):
    """Test Friction Horizon (Phi) calculation with standard multiplier."""
    # Stub market data
    fake_data = {
        "SPY": {
            "price": 450.0,
            "sector": "Index",
            "iv": 15.0,
            "hv252": 14.0,
            "vrp_structural": 1.07,
        }
    }

    mock_provider = mock_market_provider(fake_data)
    monkeypatch.setattr(MarketDataFactory, "get_provider", lambda type="yfinance": mock_provider)
    config_bundle = make_config_bundle(
        {
            "vrp_structural_threshold": 0.85,
            "dead_money_vrp_structural_threshold": 0.80,
            "dead_money_pl_pct_low": -0.10,
            "dead_money_pl_pct_high": 0.10,
            "gamma_dte_threshold": 21,
            "profit_harvest_pct": 0.50,
            "earnings_days_threshold": 5,
            "portfolio_delta_long_threshold": 75,
            "portfolio_delta_short_threshold": -50,
            "concentration_risk_pct": 0.25,
            "net_liquidity": 100000,
            "beta_weighted_symbol": "SPY",
            "global_staleness_threshold": 0.50,
            "data_integrity_min_theta": 0.50,
            "asset_mix_equity_threshold": 0.80,
            "concentration_limit_pct": 0.05,
            "max_strategies_per_symbol": 3,
            "theta_efficiency_low": 0.1,
            "theta_efficiency_high": 0.5,
            "stress_scenarios": [
                {"label": "Crash (-5%)", "move_pct": -0.05},
                {"label": "Flat", "move_pct": 0.0},
                {"label": "Rally (+5%)", "move_pct": 0.05},
            ],
            "hedge_rules": {"enabled": False},
        }
    )

    csv_path = tmp_path / "positions.csv"
    # Pos A: Spread 0.10, Qty 1 -> Cost $10. Theta 5.
    # Pos B: Spread 0.20, Qty 1 -> Cost $20. Theta 10.
    # Total Cost $30. Total Theta 15. Phi = 2.0 days.
    csv_path.write_text(
        "Symbol,Type,Quantity,Exp Date,DTE,Strike Price,Call/Put,Underlying Last Price,P/L Open,Cost,Beta Delta,Theta,Bid,Ask\n"
        "XYZ,Option,-1,2025-01-17,30,100,Put,100,0,-100,0,5,1.00,1.10\n"
        "ABC,Option,-1,2025-01-17,30,100,Call,100,0,-100,0,10,2.00,2.20\n"
    )

    report = analyze_portfolio.analyze_portfolio(str(csv_path), config=config_bundle)
    assert not report.get("error")

    summary = report["portfolio_summary"]
    phi = summary["friction_horizon_days"]

    # Check Math: 30 / 15 = 2.0
    assert abs(phi - 2.0) < 0.01
    # REMOVED: friction_status is not in current output schema
