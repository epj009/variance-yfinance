# HV Floor Examples

## Scenario 1: Utility Stock (Low Vol Trap)

```
Ticker: Utility Company (Hypothetical)
IV = 10%
HV90 = 2.5%  ← Very stable, low movement

WITHOUT FLOOR:
VRP = 10 / 2.5 = 4.0  ❌ Looks "Rich"!

WITH FLOOR (5.0%):
VRP = 10 / max(2.5, 5.0) = 10 / 5.0 = 2.0  ✅ Still elevated but realistic

REALITY:
- Stock only moves 2.5% per year
- Options are illiquid (wide spreads)
- Can't size position without massive slippage
- HV Floor prevents this from dominating your screener
```

## Scenario 2: Normal Volatility Stock (Floor Doesn't Trigger)

```
Ticker: AAPL
IV = 18.56%
HV90 = 17.62%  ← Normal volatility range

WITHOUT FLOOR:
VRP = 18.56 / 17.62 = 1.053

WITH FLOOR (5.0%):
VRP = 18.56 / max(17.62, 5.0) = 18.56 / 17.62 = 1.053  ← Same result

REALITY:
- HV90 > 5%, so floor doesn't apply
- VRP calculation is normal
- Floor is transparent when not needed
```

## Scenario 3: Extreme Low Vol (Floor Critical)

```
Ticker: Crypto Stablecoin ETF (Hypothetical)
IV = 6%
HV90 = 0.3%  ← Pegged to dollar, minimal movement

WITHOUT FLOOR:
VRP = 6.0 / 0.3 = 20.0  ❌ EXTREME signal (false positive!)

WITH FLOOR (5.0%):
VRP = 6.0 / max(0.3, 5.0) = 6.0 / 5.0 = 1.2  ✅ Reasonable

REALITY:
- Without floor, this would be #1 on your screener
- With floor, it's filtered out by LowVolTrapSpec (HV < 5%)
- Prevents trading garbage instruments
```

## Why 5.0% Specifically?

The 5% HV floor is based on **retail trading viability**:

1. **Liquidity Floor**: Below 5% annualized vol, most underlyings have:
   - Wide bid/ask spreads (> 5%)
   - Low option volume
   - Poor strike density

2. **Risk/Reward Floor**: 5% represents ~0.3% daily moves:
   - Hard to manage delta with such tiny movements
   - Transaction costs eat into edge
   - Better opportunities exist elsewhere

3. **Noise Floor**: Below 5%, price movements are often just:
   - Bid/ask bounce
   - Market microstructure noise
   - Not true directional signals

## Implementation in Code

### VRP Calculation (get_market_data.py)

```python
# Load floor from config
from variance.config_loader import load_trading_rules
rules = load_trading_rules()
HV_FLOOR_PERCENT = rules.get("hv_floor_percent", 5.0)

# Apply to VRP calculations
if hv90 is not None and hv90 > 0:
    merged_data["vrp_structural"] = iv / max(hv90, hv_floor)
    #                                      ^^^^^^^^^^^^
    #                               Floor prevents low-vol division
```

### Low Vol Trap Filter (market_specs.py)

```python
class LowVolTrapSpec(Specification[dict[str, Any]]):
    """Prevents symbols with extremely low realized vol (noise)."""

    def __init__(self, hv_floor: float):
        self.hv_floor = hv_floor  # Same 5.0% value

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        hv252 = metrics.get("hv252")
        if hv252 is None:
            return True
        return float(hv252) >= self.hv_floor  # Reject if HV < 5%
```

**Two-Layer Defense:**
1. **VRP Floor**: Caps the VRP calculation if HV is low
2. **LowVolTrapSpec**: Hard rejects symbols with HV < 5%

## Tuning the Floor

If you wanted to adjust:

```json
// config/trading_rules.json
{
  "hv_floor_percent": 5.0  ← Change this
}
```

**Conservative (Higher Floor):**
- `"hv_floor_percent": 8.0` - Only trade actively volatile stocks
- Pros: Fewer false positives, better liquidity
- Cons: Miss some opportunities in stable sectors

**Aggressive (Lower Floor):**
- `"hv_floor_percent": 3.0` - Allow lower volatility stocks
- Pros: More candidates
- Cons: Risk trading illiquid instruments

**Tastylive Recommendation:** 5.0% (current setting)
- Balances opportunity set with execution quality
- Aligned with their 45 DTE, 16 delta mechanics

## Test Results

From `tests/test_vrp_priority.py`:

```python
def test_hv_floor_applied():
    merged_data = {"iv": 10.0}
    tt_data = {"hv90": 2.0}  # Below 5% floor

    merged = provider._compute_vrp(merged_data, tt_data, None)

    # Expected: 10.0 / max(2.0, 5.0) = 10.0 / 5.0 = 2.0
    assert merged["vrp_structural"] == 2.0  ✅

    # NOT: 10.0 / 2.0 = 5.0 (without floor)
```

## Summary

| Aspect | Without Floor | With Floor (5%) |
|--------|---------------|-----------------|
| Low Vol Stock (HV=2%) | VRP = 5.0 (false positive) | VRP = 2.0 (filtered) |
| Normal Stock (HV=20%) | VRP = 1.0 | VRP = 1.0 (no change) |
| Division by Zero | Crashes | Safe (uses 5%) |
| Liquidity Quality | Trades garbage | Trades liquid only |

**Bottom Line**: HV Floor is a **safety net** that prevents mathematical anomalies from creating false trading signals in low-volatility instruments.
