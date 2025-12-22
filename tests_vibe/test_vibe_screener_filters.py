import vol_screener


def test_screen_volatility_skips_warning_and_illiquid(tmp_path, monkeypatch):
    watchlist = tmp_path / 'watchlist.csv'
    watchlist.write_text('Symbol\nWARN\nILLQ\nOK\n')
    monkeypatch.setattr(vol_screener, 'WATCHLIST_PATH', str(watchlist))

    def fake_market_data(symbols):
        return {
            'WARN': {
                'price': 100.0,
                'iv': 20.0,
                'hv252': 15.0,
                'hv60': 15.0,
                'hv20': 15.0,
                'vrp_structural': 1.3,
                'vrp_tactical': 1.3,
                'atm_volume': 1000,
                'call_bid': 1.0,
                'call_ask': 1.02,
                'call_vol': 100,
                'put_bid': 1.0,
                'put_ask': 1.02,
                'put_vol': 100,
                'warning': 'partial_data_missing_vol',
                'sector': 'Technology',
            },
            'ILLQ': {
                'price': 100.0,
                'iv': 20.0,
                'hv252': 15.0,
                'hv60': 15.0,
                'hv20': 15.0,
                'vrp_structural': 1.3,
                'vrp_tactical': 1.3,
                'atm_volume': 1000,
                'call_bid': 1.0,
                'call_ask': 1.5,
                'call_vol': 0,
                'put_bid': 1.0,
                'put_ask': 1.5,
                'put_vol': 100,
                'sector': 'Technology',
            },
            'OK': {
                'price': 100.0,
                'iv': 20.0,
                'hv252': 15.0,
                'hv60': 15.0,
                'hv20': 15.0,
                'vrp_structural': 1.3,
                'vrp_tactical': 1.3,
                'atm_volume': 1000,
                'call_bid': 1.0,
                'call_ask': 1.05,
                'call_vol': 200,
                'put_bid': 1.0,
                'put_ask': 1.05,
                'put_vol': 200,
                'sector': 'Technology',
            },
        }

    monkeypatch.setattr(vol_screener, 'get_market_data', fake_market_data)

    config = vol_screener.ScreenerConfig(limit=None, min_vrp_structural=1.0)
    result = vol_screener.screen_volatility(config)

    symbols = [row['Symbol'] for row in result['candidates']]
    assert symbols == ['OK']
    assert result['summary']['data_integrity_skipped_count'] == 1
    assert result['summary']['illiquid_skipped_count'] == 1


def test_screen_volatility_skips_low_vol_trap(tmp_path, monkeypatch):
    watchlist = tmp_path / 'watchlist.csv'
    watchlist.write_text('Symbol\nLOWVOL\n')
    monkeypatch.setattr(vol_screener, 'WATCHLIST_PATH', str(watchlist))

    def fake_market_data(symbols):
        return {
            'LOWVOL': {
                'price': 100.0,
                'iv': 10.0,
                'hv252': 2.0,
                'hv60': 2.0,
                'hv20': 2.0,
                'vrp_structural': 5.0,
                'vrp_tactical': 5.0,
                'atm_volume': 1000,
                'call_bid': 1.0,
                'call_ask': 1.05,
                'call_vol': 200,
                'put_bid': 1.0,
                'put_ask': 1.05,
                'put_vol': 200,
                'sector': 'Technology',
            }
        }

    monkeypatch.setattr(vol_screener, 'get_market_data', fake_market_data)

    config = vol_screener.ScreenerConfig(limit=None, min_vrp_structural=1.0)
    result = vol_screener.screen_volatility(config)

    assert result['candidates'] == []
    assert result['summary']['hv_rank_trap_skipped_count'] == 1
