from variance.tastytrade import TastytradeClient, TastytradeCredentials


def _client() -> TastytradeClient:
    creds = TastytradeCredentials(
        client_id="test",
        client_secret="test",
        refresh_token="test",
        api_base_url="https://api.tastytrade.com",
    )
    return TastytradeClient(credentials=creds)


def test_find_futures_atm_options_selects_closest_dte_and_strike():
    client = _client()
    chain_items = [
        {
            "symbol": "./ESH6 E2CF6 260114C5900",
            "option-type": "C",
            "strike-price": "5900.0",
            "expiration-date": "2026-01-14",
            "days-to-expiration": 45,
        },
        {
            "symbol": "./ESH6 E2CF6 260114P5900",
            "option-type": "P",
            "strike-price": "5900.0",
            "expiration-date": "2026-01-14",
            "days-to-expiration": 45,
        },
        {
            "symbol": "./ESH6 E2CF6 260114C6000",
            "option-type": "C",
            "strike-price": "6000.0",
            "expiration-date": "2026-01-14",
            "days-to-expiration": 45,
        },
        {
            "symbol": "./ESH6 E2CF6 260114P6000",
            "option-type": "P",
            "strike-price": "6000.0",
            "expiration-date": "2026-01-14",
            "days-to-expiration": 45,
        },
        {
            "symbol": "./ESH6 E2CF6 260114C6100",
            "option-type": "C",
            "strike-price": "6100.0",
            "expiration-date": "2026-01-14",
            "days-to-expiration": 45,
        },
        {
            "symbol": "./ESH6 E2CF6 260114P6100",
            "option-type": "P",
            "strike-price": "6100.0",
            "expiration-date": "2026-01-14",
            "days-to-expiration": 45,
        },
        {
            "symbol": "./ESH6 E3DF6 260115C6000",
            "option-type": "C",
            "strike-price": "6000.0",
            "expiration-date": "2026-01-15",
            "days-to-expiration": 46,
        },
        {
            "symbol": "./ESH6 E3DF6 260115P6000",
            "option-type": "P",
            "strike-price": "6000.0",
            "expiration-date": "2026-01-15",
            "days-to-expiration": 46,
        },
    ]

    selection = client.find_futures_atm_options(
        chain_items, 6010.0, target_dte=45, dte_min=30, dte_max=60
    )

    assert selection == ("./ESH6 E2CF6 260114C6000", "./ESH6 E2CF6 260114P6000")


def test_find_futures_atm_options_requires_call_and_put():
    client = _client()
    chain_items = [
        {
            "symbol": "./ESH6 E2CF6 260114C6000",
            "option-type": "C",
            "strike-price": "6000.0",
            "expiration-date": "2026-01-14",
            "days-to-expiration": 45,
        }
    ]

    selection = client.find_futures_atm_options(chain_items, 6000.0, target_dte=45)

    assert selection is None


def test_find_futures_atm_options_respects_dte_bounds():
    client = _client()
    chain_items = [
        {
            "symbol": "./ESH6 E2CF6 260114C6000",
            "option-type": "C",
            "strike-price": "6000.0",
            "expiration-date": "2026-01-14",
            "days-to-expiration": 15,
        },
        {
            "symbol": "./ESH6 E2CF6 260114P6000",
            "option-type": "P",
            "strike-price": "6000.0",
            "expiration-date": "2026-01-14",
            "days-to-expiration": 15,
        },
        {
            "symbol": "./ESH6 E2CF6 260314C6000",
            "option-type": "C",
            "strike-price": "6000.0",
            "expiration-date": "2026-03-14",
            "days-to-expiration": 90,
        },
        {
            "symbol": "./ESH6 E2CF6 260314P6000",
            "option-type": "P",
            "strike-price": "6000.0",
            "expiration-date": "2026-03-14",
            "days-to-expiration": 90,
        },
    ]

    selection = client.find_futures_atm_options(
        chain_items, 6000.0, target_dte=45, dte_min=30, dte_max=60
    )

    assert selection is None
