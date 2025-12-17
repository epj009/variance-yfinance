# Variance (yfinance Legacy Version)

This is the **preserved yfinance version** of Variance, maintained as a stable, authentication-free alternative to the Tastytrade API version.

## About This Version

**Last Updated**: December 17, 2025
**Commit**: 27b0830 - "docs: update README with Variance Score, Asset Lineage, and Tactical Bias definitions"

This version uses **yfinance** for market data - a free, open-source library that doesn't require authentication.

## Key Differences from Tastytrade Version

### Advantages ✅
- **No authentication required** - works out of the box
- **Free** - no API credentials or subscriptions needed
- **Simpler setup** - fewer dependencies
- **Stable** - proven architecture with no breaking changes

### Limitations ⚠️
- **15-minute delayed data** - not real-time
- **Rate limits** - ~2000 calls/hour
- **No account integration** - cannot fetch positions from broker
- **Manual position entry** - must use CSV files

## Features (Preserved)

All features from the stable yfinance version:

- ✅ **Vol Screener** - Identify high IV Rank opportunities
- ✅ **Portfolio Analyzer** - Analyze positions from CSV
- ✅ **HV Rank** - Historical volatility percentile tracking
- ✅ **Asset Lineage** - Sector concentration risk detection
- ✅ **Variance Score** - Composite opportunity ranking (0-100)
- ✅ **Triage Engine** - Rule-based position management
- ✅ **TUI Renderer** - Terminal UI for portfolio visualization

## Setup

```bash
# 1. Clone this repository
git clone <your-new-repo-url> variance-yfinance
cd variance-yfinance

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies (yfinance-based)
pip install -r requirements.txt

# 4. Run vol screener
python3 scripts/vol_screener.py

# 5. Analyze portfolio (from CSV)
python3 scripts/analyze_portfolio.py positions/your_positions.csv
```

## When to Use This Version

**Use yfinance version if**:
- You don't have a Tastytrade account
- You want a simple, no-authentication setup
- 15-minute delayed data is acceptable
- You're learning options trading concepts

**Use Tastytrade version if**:
- You have a Tastytrade account
- You need real-time market data
- You want automatic position fetching
- You need account balance integration

## Migration Path

If you want to upgrade to the Tastytrade API version later:
1. Visit the main [variance-cli](https://github.com/epj009/variance-cli) repository
2. Follow the Tastytrade setup guide
3. Your trading rules and configuration files are compatible

## License

Same as main Variance project.

## Support

This is a **legacy version** - active development happens in the main Tastytrade-based repository. However, this version remains stable and fully functional for users who prefer the simpler yfinance approach.

---

**Note**: This repository was created as a preservation fork to maintain the yfinance implementation after the main project migrated to Tastytrade API.
