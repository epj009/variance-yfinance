import json

import pytest

from variance import vol_screener


def make_bundle():
    return {
        "trading_rules": {"min_variance_score": 10.0, "vrp_structural_threshold": 0.85},
        "system_config": {},
        "market_config": {},
        "screener_profiles": {
            "balanced": {
                "min_vrp_structural": 0.9,
                "min_variance_score": 12.0,
                "min_iv_percentile": 5.0,
                "allow_illiquid": False,
            }
        },
        "strategies": {},
    }


def test_main_exits_on_unknown_profile(monkeypatch, capsys):
    bundle = make_bundle()
    bundle["screener_profiles"] = {}

    monkeypatch.setattr(vol_screener, "warn_if_not_venv", lambda: None)
    monkeypatch.setattr(
        vol_screener, "load_config_bundle", lambda config_dir=None, strict=None: bundle
    )
    monkeypatch.setattr(vol_screener.sys, "argv", ["vol_screener", "--profile", "missing"])

    with pytest.raises(SystemExit) as exc:
        vol_screener.main()

    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "Unknown profile" in captured.err


def test_main_parses_cli_lists(monkeypatch, capsys):
    bundle = make_bundle()
    captured = {}

    def fake_screen_volatility(config, config_bundle=None, **_kwargs):
        captured["config"] = config
        return {"candidates": [], "summary": {}}

    monkeypatch.setattr(vol_screener, "warn_if_not_venv", lambda: None)
    monkeypatch.setattr(
        vol_screener, "load_config_bundle", lambda config_dir=None, strict=None: bundle
    )
    monkeypatch.setattr(vol_screener, "screen_volatility", fake_screen_volatility)
    monkeypatch.setattr(
        vol_screener.sys,
        "argv",
        [
            "vol_screener",
            "5",
            "--profile",
            "balanced",
            "--exclude-sectors",
            "Energy,Tech",
            "--include-asset-classes",
            "Commodity,FX",
            "--exclude-asset-classes",
            "Equity",
            "--exclude-symbols",
            "NVDA, TSLA",
            "--held-symbols",
            "AAPL, MSFT",
        ],
    )

    vol_screener.main()

    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert parsed["candidates"] == []
    assert parsed["summary"] == {}

    config = captured["config"]
    assert config.limit == 5
    assert config.exclude_sectors == ["Energy", "Tech"]
    assert config.include_asset_classes == ["Commodity", "FX"]
    assert config.exclude_asset_classes == ["Equity"]
    assert config.exclude_symbols == ["NVDA", "TSLA"]
    assert config.held_symbols == ["AAPL", "MSFT"]


def test_main_exits_on_screen_error(monkeypatch, capsys):
    bundle = make_bundle()

    monkeypatch.setattr(vol_screener, "warn_if_not_venv", lambda: None)
    monkeypatch.setattr(
        vol_screener, "load_config_bundle", lambda config_dir=None, strict=None: bundle
    )
    monkeypatch.setattr(
        vol_screener,
        "screen_volatility",
        lambda *_args, **_kwargs: {"error": "boom"},
    )
    monkeypatch.setattr(vol_screener.sys, "argv", ["vol_screener", "--profile", "balanced"])

    with pytest.raises(SystemExit) as exc:
        vol_screener.main()

    assert exc.value.code == 1
    output = capsys.readouterr().err
    assert "boom" in output
