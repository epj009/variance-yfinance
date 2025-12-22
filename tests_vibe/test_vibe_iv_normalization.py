from get_market_data import normalize_iv


def test_normalize_iv_defaults_to_percent_when_no_context():
    iv, warning = normalize_iv(0.50, hv_context=None)
    assert iv == 50.0
    assert warning is None


def test_normalize_iv_corrects_percent_scale_with_context():
    iv, warning = normalize_iv(40.0, hv_context=20.0)
    assert iv == 40.0
    assert warning == 'iv_scale_corrected_percent'


def test_normalize_iv_flags_implausibly_high_decimal():
    iv, warning = normalize_iv(2.5, hv_context=100.0)
    assert iv == 2.5
    assert warning == 'iv_implausibly_high_assuming_percent'
