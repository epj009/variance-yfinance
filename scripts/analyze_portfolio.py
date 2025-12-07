import csv
import sys
import json
import argparse # Import argparse
from collections import defaultdict
from datetime import datetime
from get_market_data import get_market_data

# Warn when running outside a venv to improve portability/setup guidance
def warn_if_not_venv():
    if sys.prefix == getattr(sys, "base_prefix", sys.prefix):
        print("Warning: not running in a virtual environment. Create one with `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`.", file=sys.stderr)

# Baseline trading rules so triage still runs if config is missing/malformed
RULES_DEFAULT = {
    "vol_bias_threshold": 0.85,
    "dead_money_vol_bias_threshold": 0.80,
    "dead_money_pl_pct_low": -0.10,
    "dead_money_pl_pct_high": 0.10,
    "low_ivr_threshold": 20,
    "gamma_dte_threshold": 21,
    "profit_harvest_pct": 0.50,
    "earnings_days_threshold": 5,
    "portfolio_delta_long_threshold": 75,
    "portfolio_delta_short_threshold": -50,
    "concentration_risk_pct": 0.25,
    "net_liquidity": 50000,
    "beta_weighted_symbol": "SPY"
}

# Load Trading Rules
try:
    with open('config/trading_rules.json', 'r') as f:
        RULES = {**RULES_DEFAULT, **json.load(f)}
except FileNotFoundError:
    print("Warning: config/trading_rules.json not found. Using defaults.", file=sys.stderr)
    RULES = RULES_DEFAULT.copy()

# Load Market Config (for Asset Class Map)
MARKET_CONFIG = {}
try:
    with open('config/market_config.json', 'r') as f:
        MARKET_CONFIG = json.load(f)
except FileNotFoundError:
    print("Warning: config/market_config.json not found. Asset Mix calculation will be limited.", file=sys.stderr)

# Build reverse lookup: sector -> asset class
SECTOR_TO_ASSET_CLASS = {}
if 'ASSET_CLASS_MAP' in MARKET_CONFIG:
    for asset_class, sectors in MARKET_CONFIG['ASSET_CLASS_MAP'].items():
        for sector in sectors:
            SECTOR_TO_ASSET_CLASS[sector] = asset_class

def map_sector_to_asset_class(sector):
    """
    Maps a sector string to its asset class.

    Args:
        sector (str): Sector name (e.g., "Technology", "Energy")

    Returns:
        str: Asset class (e.g., "Equity", "Commodity", "Fixed Income", "FX", "Index")
    """
    return SECTOR_TO_ASSET_CLASS.get(sector, "Equity")  # Default to Equity if unknown

class PortfolioParser:
    """
    Normalizes CSV headers from various broker exports to a standard internal format.
    """
    # Internal Key : [Possible CSV Headers]
    MAPPING = {
        'Symbol': ['Symbol', 'Sym', 'Ticker'],
        'Type': ['Type', 'Asset Class'], 
        'Quantity': ['Quantity', 'Qty', 'Position', 'Size'],
        'Exp Date': ['Exp Date', 'Expiration', 'Expiry'],
        'DTE': ['DTE', 'Days To Expiration', 'Days to Exp'],
        'Strike Price': ['Strike Price', 'Strike'],
        # FIX: Removed 'Type' from Call/Put to avoid collision with Asset Class
        'Call/Put': ['Call/Put', 'Side', 'C/P'], 
        'Underlying Last Price': ['Underlying Last Price', 'Underlying Price', 'Current Price'],
        'P/L Open': ['P/L Open', 'P/L Day', 'Unrealized P/L'],
        'Cost': ['Cost', 'Cost Basis', 'Trade Price'],
        'IV Rank': ['IV Rank', 'IVR', 'IV Percentile'],
        'beta_delta': ['β Delta', 'Beta Delta', 'Delta Beta', 'Weighted Delta'],
        'Theta': ['Theta', 'Theta Daily', 'Daily Theta']
    }

    @staticmethod
    def normalize_row(row):
        """
        Convert a raw CSV row into a normalized dictionary using MAPPING.
        
        Args:
            row (dict): A single row from the CSV reader.
            
        Returns:
            dict: A dictionary with standard keys (Symbol, Type, etc.) and normalized values.
        """
        normalized = {}
        for internal_key, aliases in PortfolioParser.MAPPING.items():
            found = False
            for alias in aliases:
                if alias in row:
                    val = row[alias]
                    # Canonicalize option side to keep strategy detection stable across casing
                    if internal_key == 'Call/Put' and val:
                        upper_val = str(val).strip().upper()
                        if upper_val == 'CALL':
                            val = 'Call'
                        elif upper_val == 'PUT':
                            val = 'Put'
                    normalized[internal_key] = val
                    found = True
                    break
            if not found:
                normalized[internal_key] = ""
        return normalized

    @staticmethod
    def parse(file_path):
        """
        Read and parse the CSV file at the given path.
        
        Args:
            file_path (str): Path to the CSV file.
            
        Returns:
            list[dict]: A list of normalized position rows.
        """
        positions = []
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    positions.append(PortfolioParser.normalize_row(row))
        except Exception as e:
            print(f"Error reading CSV: {e}")
        return positions

def parse_currency(value):
    """Clean and convert currency strings (e.g., '$1,234.56') to floats."""
    if not value:
        return 0.0
    clean = value.replace(',', '').replace('$', '').replace('%', '').strip()
    if clean == '--':
        return 0.0
    try:
        return float(clean)
    except ValueError:
        return 0.0

def parse_dte(value):
    """Clean and convert DTE strings (e.g., '45d') to integers."""
    if not value:
        return 0
    clean = value.replace('d', '').strip()
    try:
        return int(clean)
    except ValueError:
        return 0

def get_root_symbol(raw_symbol):
    """Extract the root symbol from a ticker, handling futures (e.g., /ESZ4 -> /ES)."""
    # Normalize multi-space and single-space separated symbols
    token = raw_symbol.strip().split()[0] if raw_symbol else ""

    # Handle Futures: ./CLG6 LOG6 ... -> /CL
    if token.startswith('./'):
        token = token.replace('./', '/')

    # Futures roots like /ESZ4 -> /ES
    if token.startswith('/') and len(token) >= 3:
        return token[:3]

    return token

def is_stock_type(type_str):
    """Determine if a position leg is underlying stock/equity."""
    if not type_str:
        return False
    normalized = type_str.strip().lower()
    return normalized in {"stock", "equity", "equities", "equity stock"}

def identify_strategy(legs):
    """
    Identify the option strategy based on a list of position legs.
    
    Analyzes the combination of Calls/Puts, Long/Short quantities, and strike prices
    to name the complex strategy (e.g., 'Iron Condor', 'Strangle', 'Covered Call').
    
    Args:
        legs (list[dict]): A list of normalized position legs belonging to one symbol group.
        
    Returns:
        str: The name of the strategy.
    """
    # This function now expects a list of legs that are already grouped as a potential strategy.
    # It will also be called with stock legs included for Covered strategies.

    if not legs: return "Empty"

    stock_legs = [l for l in legs if is_stock_type(l['Type'])]
    option_legs = [l for l in legs if not is_stock_type(l['Type'])]
    total_opt_legs = len(option_legs)

    if len(legs) == 1:
        leg = legs[0]
        if is_stock_type(leg['Type']): return "Stock"
        
        # Specific identification for single options
        qty = parse_currency(leg['Quantity'])
        otype = leg['Call/Put']
        if otype == 'Call':
            if qty > 0: return "Long Call"
            else: return "Short Call"
        elif otype == 'Put':
            if qty > 0: return "Long Put"
            else: return "Short Put"
        return "Single Option (Unknown Type)" # Fallback, should not happen if Call/Put is present

    # Metrics for option legs only
    expirations = set(l['Exp Date'] for l in option_legs)
    is_multi_exp = len(expirations) > 1

    long_calls = sum(1 for l in option_legs if l['Call/Put'] == 'Call' and parse_currency(l['Quantity']) > 0)
    short_calls = sum(1 for l in option_legs if l['Call/Put'] == 'Call' and parse_currency(l['Quantity']) < 0)
    long_puts = sum(1 for l in option_legs if l['Call/Put'] == 'Put' and parse_currency(l['Quantity']) > 0)
    short_puts = sum(1 for l in option_legs if l['Call/Put'] == 'Put' and parse_currency(l['Quantity']) < 0)
    
    long_call_qty = sum(abs(parse_currency(l['Quantity'])) for l in option_legs if l['Call/Put'] == 'Call' and parse_currency(l['Quantity']) > 0)
    short_call_qty = sum(abs(parse_currency(l['Quantity'])) for l in option_legs if l['Call/Put'] == 'Call' and parse_currency(l['Quantity']) < 0)
    long_put_qty = sum(abs(parse_currency(l['Quantity'])) for l in option_legs if l['Call/Put'] == 'Put' and parse_currency(l['Quantity']) > 0)
    short_put_qty = sum(abs(parse_currency(l['Quantity'])) for l in option_legs if l['Call/Put'] == 'Put' and parse_currency(l['Quantity']) < 0)
    
    short_call_strikes = sorted([parse_currency(l['Strike Price']) for l in option_legs if l['Call/Put'] == 'Call' and parse_currency(l['Quantity']) < 0])
    short_put_strikes = sorted([parse_currency(l['Strike Price']) for l in option_legs if l['Call/Put'] == 'Put' and parse_currency(l['Quantity']) < 0])
    long_call_strikes = sorted([parse_currency(l['Strike Price']) for l in option_legs if l['Call/Put'] == 'Call' and parse_currency(l['Quantity']) > 0])
    long_put_strikes = sorted([parse_currency(l['Strike Price']) for l in option_legs if l['Call/Put'] == 'Put' and parse_currency(l['Quantity']) > 0])

    # --- Stock-Option Combinations ---
    if stock_legs:
        if len(stock_legs) == 1:
            if total_opt_legs == 1:
                if short_calls == 1: return "Covered Call"
                if short_puts == 1: return "Covered Put" # This is usually a Cash-Secured Put, not a Covered Put
            if total_opt_legs == 2:
                if short_calls == 1 and short_puts == 1: return "Covered Strangle"
                if short_calls == 1 and long_puts == 1: return "Collar" # Assumes short call to offset long put
        # Add more complex stock-option combos here if needed
        return "Custom/Combo (Stock)" # Fallback for complex stock options

    # --- Pure Option Strategies ---
    if is_multi_exp:
        if total_opt_legs == 2:
            if short_calls == 1 and long_calls == 1:
                # Same strike = Calendar, Different strike = Diagonal
                if short_call_strikes and short_call_strikes[0] == long_call_strikes[0]:
                    return "Calendar Spread (Call)"
                return "Diagonal Spread (Call)"
            if short_puts == 1 and long_puts == 1:
                if short_put_strikes and short_put_strikes[0] == long_put_strikes[0]:
                    return "Calendar Spread (Put)"
                return "Diagonal Spread (Put)"
        if total_opt_legs == 4:
             return "Double Diagonal / Calendar"
        return "Custom/Combo (Multi-Exp)"

    if total_opt_legs == 4:
        # Standard 4-leg defined risk strategies
        if short_calls == 1 and long_calls == 1 and short_puts == 1 and long_puts == 1:
            if short_call_strikes and short_put_strikes and short_call_strikes[0] == short_put_strikes[0]:
                 return "Iron Butterfly" # Shorts share the same strike (ATM)
            return "Iron Condor" # Shorts are at different strikes (OTM)
    
    if total_opt_legs == 3:
        # 3-Leg strategies: Jade Lizard, Twisted Sister, Butterflies
        if short_puts >= 1 and short_calls >= 1 and long_calls >= 1 and long_puts == 0:
            return "Jade Lizard" # Short Put + Short Call Spread
        if short_calls >= 1 and short_puts >= 1 and long_puts >= 1 and long_calls == 0:
            return "Twisted Sister" # Short Call + Short Put Spread
        if long_calls == 2 and short_calls == 1 and long_call_qty == abs(short_call_qty): return "Long Call Butterfly"
        if long_puts == 2 and short_puts == 1 and long_put_qty == abs(short_put_qty): return "Long Put Butterfly"

    if total_opt_legs == 2:
        # Standard 2-leg strategies
        if short_calls >= 1 and short_puts >= 1: return "Strangle" # Short Call + Short Put
        if (long_calls >= 1 and short_calls >= 1):
            if long_call_qty != short_call_qty: return "Ratio Spread (Call)" # Uneven quantity
            return "Vertical Spread (Call)" # 1 Long, 1 Short
        if (long_puts >= 1 and short_puts >= 1):
            if long_put_qty != short_put_qty: return "Ratio Spread (Put)"
            return "Vertical Spread (Put)"

    return "Custom/Combo"

def cluster_strategies(positions):
    """
    Group individual position legs into logical strategies (e.g., combining a short call and short put into a Strangle).
    
    Logic:
    1. Group all legs by Root Symbol.
    2. Within each Root:
       a. Group options by Expiration Date to find standard vertical/horizontal spreads.
       b. Match Stock legs with remaining Option legs to find Covered Calls/Collars.
       
    Args:
        positions (list[dict]): List of flat position rows.
        
    Returns:
        list[list[dict]]: A list of lists, where each inner list is a group of legs forming a strategy.
    """
    by_root_all_legs = defaultdict(list)
    for row in positions:
        root = get_root_symbol(row['Symbol'])
        if root: # Ensure root is not empty
            by_root_all_legs[root].append(row)

    final_clusters = [] 

    for root, root_legs_original in by_root_all_legs.items():
        # Make a mutable copy for this root's legs
        root_legs = list(root_legs_original)
        
        stock_legs = [l for l in root_legs if is_stock_type(l['Type'])]
        option_legs = [l for l in root_legs if not is_stock_type(l['Type'])]
        
        # Used flags for options within this root to prevent double-counting legs
        option_used_flags = [False] * len(option_legs)
        stock_used_flags = [False] * len(stock_legs) # Keep track of used stocks
        
        # Phase 1: Identify pure option strategies (grouped by expiration)
        # Use a list of lists to build clusters within this root
        
        # Group options by expiration date to find standard spreads first
        by_exp_options = defaultdict(list)
        for i, leg in enumerate(option_legs):
            by_exp_options[leg['Exp Date']].append((i, leg))

        for exp, exp_legs_with_indices in by_exp_options.items():
            current_exp_options = [leg for idx, leg in exp_legs_with_indices if not option_used_flags[idx]] # Only consider unused options
            
            if len(current_exp_options) > 1: # Only look for strategies if > 1 option in this expiration
                # Temporarily create a sub-cluster
                temp_cluster = list(current_exp_options)
                strat_name = identify_strategy(temp_cluster)
                
                # If it's a known multi-leg strategy (not single option or custom/combo or stock)
                # We prioritize finding 'named' strategies over leaving them as loose legs
                if strat_name not in ["Single Option (Unknown Type)", "Custom/Combo", "Stock", "Empty", "Custom/Combo (Stock)"]:
                    final_clusters.append(temp_cluster)
                    # Mark all legs in this temp_cluster as used
                    for leg in temp_cluster:
                        # Find original index for this leg in option_legs and mark as used
                        original_idx = next((j for j, l in enumerate(option_legs) if l == leg), None)
                        if original_idx is not None:
                            option_used_flags[original_idx] = True
        
        # Phase 2: Handle stock-option combinations with remaining options
        unclustered_options_after_phase1 = [leg for i, leg in enumerate(option_legs) if not option_used_flags[i]]
        
        if stock_legs:
            # First, try 3-leg combinations: Covered Strangle, Collar
            
            # Covered Strangle (1 Stock + 1 Short Call + 1 Short Put)
            for s_idx, s_leg in enumerate(stock_legs):
                if stock_used_flags[s_idx]: continue
                
                temp_short_calls = [l for l in unclustered_options_after_phase1 if l['Call/Put'] == 'Call' and parse_currency(l['Quantity']) < 0]
                temp_short_puts = [l for l in unclustered_options_after_phase1 if l['Call/Put'] == 'Put' and parse_currency(l['Quantity']) < 0]
                
                if temp_short_calls and temp_short_puts:
                    # Greedily take the first available
                    current_combo = [s_leg, temp_short_calls[0], temp_short_puts[0]]
                    if identify_strategy(current_combo) == "Covered Strangle":
                        final_clusters.append(current_combo)
                        stock_used_flags[s_idx] = True
                        unclustered_options_after_phase1.remove(temp_short_calls[0])
                        unclustered_options_after_phase1.remove(temp_short_puts[0])
                        break # Break from stock loop, move to next
            
            # Collar (1 Stock + 1 Short Call + 1 Long Put)
            for s_idx, s_leg in enumerate(stock_legs):
                if stock_used_flags[s_idx]: continue
                
                temp_short_calls = [l for l in unclustered_options_after_phase1 if l['Call/Put'] == 'Call' and parse_currency(l['Quantity']) < 0]
                temp_long_puts = [l for l in unclustered_options_after_phase1 if l['Call/Put'] == 'Put' and parse_currency(l['Quantity']) > 0]
                
                if temp_short_calls and temp_long_puts:
                    current_combo = [s_leg, temp_short_calls[0], temp_long_puts[0]]
                    if identify_strategy(current_combo) == "Collar":
                        final_clusters.append(current_combo)
                        stock_used_flags[s_idx] = True
                        unclustered_options_after_phase1.remove(temp_short_calls[0])
                        unclustered_options_after_phase1.remove(temp_long_puts[0])
                        break
            
            # Now, try 2-leg combinations: Covered Call / Covered Put
            for s_idx, s_leg in enumerate(stock_legs):
                if stock_used_flags[s_idx]: continue
                
                for o_idx, o_leg in enumerate(unclustered_options_after_phase1):
                    current_combo = [s_leg, o_leg]
                    strat_name = identify_strategy(current_combo)
                    if strat_name in ["Covered Call", "Covered Put"]:
                        final_clusters.append(current_combo)
                        stock_used_flags[s_idx] = True
                        unclustered_options_after_phase1.remove(o_leg)
                        break # Move to next stock or stop trying for this stock

            # Add any remaining stock legs as single stock positions
            for s_idx, s_leg in enumerate(stock_legs):
                if not stock_used_flags[s_idx]:
                    final_clusters.append([s_leg])
            
            # Add any remaining (truly single) options
            for o_leg in unclustered_options_after_phase1:
                final_clusters.append([o_leg])

        else: # No stock legs, just add all option legs to final clusters
            for leg in unclustered_options_after_phase1: # Use the already processed ones
                final_clusters.append([leg])
            
    return final_clusters

def analyze_portfolio(file_path, output_json=False):
    """
    Main entry point for Portfolio Analysis (Morning Triage).
    
    1. Parses the input CSV.
    2. Groups positions into Strategies.
    3. Fetches live market data (Price, Volatility).
    4. Applies Triage Rules (Harvest, Defense, Gamma, etc.) based on RULES config.
    5. Prints a formatted report to stdout.
    
    Args:
        file_path (str): Path to the portfolio CSV file.
        output_json (bool): If True, suppresses markdown output and returns structured data.
    """
    # Output handler (suppresses prints for JSON mode)
    out = print if not output_json else (lambda *args, **kwargs: None)

    # 1. Parse CSV
    positions = PortfolioParser.parse(file_path)
    if not positions:
        return {} if output_json else None

    # 2. Cluster Strategies
    clusters = cluster_strategies(positions)
    
    # 3. Gather Unique Roots for Live Data
    unique_roots = list(set(get_root_symbol(l['Symbol']) for l in positions))
    # Filter out empty roots
    unique_roots = [r for r in unique_roots if r]
    
    out(f"Fetching live market data for {len(unique_roots)} symbols...")
    market_data = get_market_data(unique_roots)
    
    # --- Data Freshness Check ---
    # We'll infer freshness from the newest 'price' timestamp or just current time vs warning
    # Since get_market_data doesn't return explicit timestamps per symbol, we rely on general execution time
    # BUT, we can check if 'is_stale' is prevalent.
    # Better yet, let's just print the current execution time so the user knows WHEN this ran.
    
    now = datetime.now()
    analysis_time = now.strftime('%Y-%m-%d %H:%M:%S')
    out(f"\n**Analysis Time:** {analysis_time}")
    
    # Check for widespread staleness (if > 50% of symbols are stale)
    stale_count = sum(1 for d in market_data.values() if d.get('is_stale', False))
    if len(market_data) > 0 and (stale_count / len(market_data)) > 0.5:
        out("🚨 **WARNING:** > 50% of data points are marked STALE. Markets may be closed or data delayed.")
        out("   *Verify prices before executing trades.*")
    stale_warning = len(market_data) > 0 and (stale_count / len(market_data)) > 0.5
        
    all_position_reports = []
    total_beta_delta = 0.0
    total_portfolio_theta = 0.0 # Initialize total portfolio theta
    missing_ivr_legs = 0
    total_option_legs = 0 # Count active option legs for data integrity check

    for legs in clusters:
        root = get_root_symbol(legs[0]['Symbol'])
        
        # Calculate min_dte only for option legs
        option_legs = [l for l in legs if not is_stock_type(l['Type'])]
        total_option_legs += len(option_legs)
        dtes = [parse_dte(l['DTE']) for l in option_legs]
        min_dte = min(dtes) if dtes else 0
        
        strategy_name = identify_strategy(legs)
        net_pl = sum(parse_currency(l['P/L Open']) for l in legs)
        
        strategy_delta = 0.0
        for l in legs:
            b_delta = parse_currency(l['beta_delta'])
            strategy_delta += b_delta
            total_beta_delta += b_delta
            total_portfolio_theta += parse_currency(l['Theta']) # Sum Theta from each leg
            if not str(l['IV Rank']).strip():
                missing_ivr_legs += 1

        net_cost = sum(parse_currency(l['Cost']) for l in legs)
        
        pl_pct = None
        # Treat negatives as credits received, positives as debits paid
        if net_cost < 0:
            max_profit = abs(net_cost)
            if max_profit > 0:
                pl_pct = net_pl / max_profit
        elif net_cost > 0:
            pl_pct = net_pl / net_cost
        
        # Initialize variables
        action = ""
        logic = ""
        is_winner = False
        
        # Retrieve live data
        m_data = market_data.get(root, {})
        vol_bias = m_data.get('vol_bias', 0)
        if vol_bias is None: vol_bias = 0
        
        live_price = m_data.get('price', 0)
        is_stale = m_data.get('is_stale', False)
        earnings_date = m_data.get('earnings_date')
        sector = m_data.get('sector', 'Unknown')
        proxy_note = m_data.get('proxy')

        # 1. Harvest (Short Premium only)
        if net_cost < 0 and pl_pct is not None and pl_pct >= RULES['profit_harvest_pct']:
            action = "🌾 Harvest"
            logic = f"Profit {pl_pct:.1%}"
            is_winner = True
        
        # 2. Defense
        underlying_price = parse_currency(legs[0]['Underlying Last Price'])
        price_used = "static"
        # Use live price if available
        if live_price:
            underlying_price = live_price
            price_used = "live_stale" if is_stale else "live"
            
        is_tested = False
        for l in legs:
            # Only check option legs for "tested" status
            if is_stock_type(l['Type']): continue 
            qty = parse_currency(l['Quantity'])
            otype = l['Call/Put']
            strike = parse_currency(l['Strike Price'])
            if qty < 0:
                if otype == 'Call' and underlying_price > strike: is_tested = True
                elif otype == 'Put' and underlying_price < strike: is_tested = True
        
        if not is_winner and is_tested and min_dte < RULES['gamma_dte_threshold']:
            action = "🛡️ Defense"
            logic = f"Tested & < {RULES['gamma_dte_threshold']} DTE"
            
        # 3. Gamma Zone (apply even if P/L% is unknown)
        if not is_winner and not is_tested and min_dte < RULES['gamma_dte_threshold'] and min_dte > 0:
            action = "☢️ Gamma"
            logic = f"< {RULES['gamma_dte_threshold']} DTE Risk"
            
        # 4. Dead Money (Enhanced with Real-time Vol Bias)
        if not is_winner and not is_tested and min_dte > RULES['gamma_dte_threshold']:
            if pl_pct is not None and RULES['dead_money_pl_pct_low'] <= pl_pct <= RULES['dead_money_pl_pct_high']:
                if vol_bias > 0 and vol_bias < RULES['dead_money_vol_bias_threshold']:
                    action = "🪦 Dead Money"
                    logic = f"Bias {vol_bias:.2f} & Flat P/L"
                elif vol_bias == 0 and 'IV Rank' in legs[0] and parse_currency(legs[0]['IV Rank']) < RULES['low_ivr_threshold']:
                     # Fallback if no live data
                     action = "🪦 Dead Money"
                     logic = "Low IVR (Stale) & Flat P/L"

        # 5. Earnings Warning
        earnings_note = ""
        if earnings_date and earnings_date != "Unavailable":
            try:
                edate = datetime.fromisoformat(earnings_date).date()
                days_to_earn = (edate - datetime.now().date()).days
                if 0 <= days_to_earn <= RULES['earnings_days_threshold']:
                    earnings_note = f"Earnings {days_to_earn}d (Binary Event)"
                    if not action:
                        action = f"⚠️ Earnings ({days_to_earn}d)"
                        logic = "Binary Event Risk"
                    else:
                        logic = f"{logic} | {earnings_note}" if logic else earnings_note
            except:
                pass
        
        price_str = f"${live_price:.2f}" if live_price else "N/A"
        if is_stale:
            price_str += "*"
        bias_str = f"{vol_bias:.2f}" if vol_bias else "N/A"
        if proxy_note:
            bias_str += f" ({proxy_note})"

        if (price_used != "live" or is_stale) and not is_winner and min_dte < 21:
            # If we can't rely fully on tested logic due to stale/absent live price, note it
            note = "Price stale/absent; tested status uncertain"
            if action in ["🛡️ Defense", "☢️ Gamma"]:
                logic = f"{logic} | {note}" if logic else note
            elif not action:
                action = ""
                logic = note

        all_position_reports.append({
            'root': root,
            'strategy_name': strategy_name,
            'price_str': price_str,
            'bias_str': bias_str,
            'net_pl': net_pl,
            'pl_pct': pl_pct,
            'min_dte': min_dte,
            'action': action,
            'logic': logic,
            'sector': sector,
            'delta': strategy_delta
        })

    actionable_reports = [r for r in all_position_reports if r['action']]
    non_actionable_reports = [r for r in all_position_reports if not r['action']]

    # Print Triage Report
    out("\n### Triage Report")
    out("| Symbol | Strat | Price | Vol Bias | Net P/L | P/L % | DTE | Action | Logic |")
    out("|---|---|---|---|---|---|---|---|---|")
    if actionable_reports:
        for r in actionable_reports:
            pl_pct_str = f"{r['pl_pct']:.1%}" if r['pl_pct'] is not None else "N/A"
            out(f"| {r['root']} | {r['strategy_name']} | {r['price_str']} | {r['bias_str']} | ${r['net_pl']:.2f} | {pl_pct_str} | {r['min_dte']}d | {r['action']} | {r['logic']} |")
    else:
        out("No specific triage actions triggered for current positions.")

    # Print Portfolio Overview (Non-Actionable Positions)
    out("\n### Portfolio Overview (Non-Actionable Positions)")
    out("| Symbol | Strat | Price | Vol Bias | Net P/L | P/L % | DTE | Status |")
    out("|---|---|---|---|---|---|---|---|")
    if non_actionable_reports:
        for r in non_actionable_reports:
            pl_pct_str = f"{r['pl_pct']:.1%}" if r['pl_pct'] is not None else "N/A"
            out(f"| {r['root']} | {r['strategy_name']} | {r['price_str']} | {r['bias_str']} | ${r['net_pl']:.2f} | {pl_pct_str} | {r['min_dte']}d | Hold |")
    else:
        out("No non-actionable positions to display.")

    # Data Integrity Guardrail
    # If we have active options but tiny delta/theta sums, likely per-share data error
    if total_option_legs > 0 and abs(total_beta_delta) < 5.0 and total_portfolio_theta < 5.0:
        out("\n🚨 **DATA INTEGRITY WARNING:**")
        out("   Your Delta/Theta totals are suspiciously low. Ensure your CSV contains")
        out("   TOTAL position values (Contract Qty * 100), not per-share Greeks.")
        out("   Risk metrics (Stress Box) may be understated by 100x.")

    out("\n")
    out(f"\n**Total Beta Weighted Delta:** {total_beta_delta:.2f}")
    
    # Display Portfolio Theta and health check
    out(f"**Total Portfolio Theta:** ${total_portfolio_theta:.2f}/day")
    net_liq = RULES['net_liquidity']
    theta_pct_of_nl = None
    theta_status = "N/A"
    theta_pct_of_nl = None
    if net_liq > 0:
        theta_as_pct_of_nl = (total_portfolio_theta / net_liq) * 100
        theta_pct_of_nl = theta_as_pct_of_nl
        out(f"**Theta/Net Liquidity:** {theta_as_pct_of_nl:.2f}%/day")
        if 0.1 <= theta_as_pct_of_nl <= 0.5:
            theta_status = "healthy"
            out("✅ **Theta Status:** Healthy (0.1% - 0.5% of Net Liq/day)")
        elif theta_as_pct_of_nl < 0.1:
            theta_status = "low"
            out("⚠️ **Theta Status:** Low. Consider adding more short premium.")
        else:
            theta_status = "high"
            out("☢️ **Theta Status:** High. Consider reducing overall premium sold or managing gamma risk.")
    
    delta_status = "neutral"
    if total_beta_delta > RULES['portfolio_delta_long_threshold']:
        delta_status = "too_long"
        out(f"⚠️ **Status:** Too Long (Delta > {RULES['portfolio_delta_long_threshold']})")
    elif total_beta_delta < RULES['portfolio_delta_short_threshold']:
        delta_status = "too_short"
        out(f"⚠️ **Status:** Too Short (Delta < {RULES['portfolio_delta_short_threshold']})")
    else:
        out("✅ **Status:** Delta Neutral-ish")

    # Delta Spectrograph
    out("\n### The Delta Spectrograph (Risk Visualization)")
    # Aggregate by root just in case of splits, though typically one root per report entry
    root_deltas = defaultdict(float)
    for r in all_position_reports:
        root_deltas[r['root']] += r['delta']
    
    # Sort by absolute delta influence
    sorted_deltas = sorted(root_deltas.items(), key=lambda x: abs(x[1]), reverse=True)
    
    # Find max absolute delta for scaling
    max_delta = max([abs(d) for r, d in sorted_deltas]) if sorted_deltas else 1.0
    if max_delta == 0: max_delta = 1.0
    
    # Draw bars
    for root, delta in sorted_deltas[:10]: # Top 10 drivers
        # Scale to 20 chars
        bar_len = int((abs(delta) / max_delta) * 20)
        bar = "█" * bar_len
        # Padding
        bar = bar.ljust(20)
        out(f"{root:<6} [{bar}] {delta:+.1f}")

    # Sector Allocation Summary
    sector_counts = defaultdict(int)
    total_positions = len(all_position_reports)
    for r in all_position_reports:
        sector_counts[r['sector']] += 1
    
    out("\n### Sector Balance (Rebalancing Context)")
    sorted_sectors = sorted(sector_counts.items(), key=lambda x: x[1], reverse=True)
    
    # Identify heavy concentrations (>25% of portfolio)
    concentrations = []
    for sec, count in sorted_sectors:
        pct = count / total_positions if total_positions > 0 else 0
        if pct > RULES['concentration_risk_pct']:
            concentrations.append(f"**{sec}** ({count} pos, {pct:.0%})")
            
    if concentrations:
        out(f"⚠️ **Concentration Risk:** High exposure to {', '.join(concentrations)}.")
        out("   *Advice:* Look for new trades in under-represented sectors to reduce correlation.")
    else:
        out(f"✅ **Sector Balance:** Good. No single sector exceeds {RULES['concentration_risk_pct']:.0%} of the portfolio.")

    if missing_ivr_legs > 0:
        out(f"\nNote: IV Rank data missing for {missing_ivr_legs} legs; Dead Money checks may fall back to live Vol Bias only.")
    
    # Caution tape
    caution_items = []
    for r in all_position_reports:
        if "stale" in r['logic'].lower():
            caution_items.append(f"{r['root']}: price stale/absent; tested status uncertain")
        if "Earnings" in r.get('action', "") or "Binary Event" in r.get('logic', ""):
            caution_items.append(f"{r['root']}: earnings soon (see action/logic)")
    if caution_items:
        out("\n### Caution")
        for c in caution_items:
            out(f"- {c}")

    # Stress Box (Scenario Simulator)
    out("\n### 📉 The Stress Box (Scenario Simulator)")
    
    beta_sym = RULES.get('beta_weighted_symbol', 'SPY') # Default to SPY if missing
    
    # Need Beta Symbol price for accurate beta weighting impact
    # We'll try to find it in existing market_data, or fetch it if missing
    beta_price = 0.0
    if beta_sym in market_data:
        beta_price = market_data[beta_sym].get('price', 0.0)
    else:
        # Quick fetch for Beta Symbol if not held
        try:
            beta_data = get_market_data([beta_sym])
            beta_price = beta_data.get(beta_sym, {}).get('price', 0.0)
        except:
            pass
            
    if beta_price > 0:
        out(f"Based on Portfolio Delta (assumed {beta_sym}-weighted) and {beta_sym} Price (${beta_price:.2f}):")
        out(f"| Scenario | Est. {beta_sym} Move | Est. Portfolio P/L |")
        out("|---|---|")
        
        scenarios = [
            ("Crash (-5%)", -0.05),
            ("Dip (-3%)", -0.03),
            ("Flat", 0.0),
            ("Rally (+3%)", 0.03),
            ("Moon (+5%)", 0.05)
        ]
        
        for label, pct in scenarios:
            spy_points = beta_price * pct
            est_pl = total_beta_delta * spy_points
            out(f"| {label:<11} | {spy_points:+.2f} pts | ${est_pl:+.2f} |")
    else:
        out(f"Could not fetch {beta_sym} price for stress testing.")

    if output_json:
        return {
            "analysis_time": analysis_time,
            "actionable_reports": actionable_reports,
            "non_actionable_reports": non_actionable_reports,
            "summary": {
                "total_beta_delta": total_beta_delta,
                "total_portfolio_theta": total_portfolio_theta,
                "theta_pct_of_net_liq": theta_pct_of_nl,
                "theta_status": theta_status,
                "delta_status": delta_status,
                "sector_concentrations": concentrations,
                "stale_warning": stale_warning,
                "caution": caution_items
            }
        }

def analyze_portfolio(file_path):
    """
    Main entry point for Portfolio Analysis (Morning Triage).
    
    1. Parses the input CSV.
    2. Groups positions into Strategies.
    3. Fetches live market data (Price, Volatility).
    4. Applies Triage Rules (Harvest, Defense, Gamma, etc.) based on RULES config.
    5. Returns a structured report (dictionary).
    
    Args:
        file_path (str): Path to the portfolio CSV file.
        
    Returns:
        dict: A dictionary containing the full analysis report.
    """
    # 1. Parse CSV
    positions = PortfolioParser.parse(file_path)
    if not positions:
        return {"error": "No positions found in CSV or error parsing file."}

    # 2. Cluster Strategies
    clusters = cluster_strategies(positions)
    
    # 3. Gather Unique Roots for Live Data
    unique_roots = list(set(get_root_symbol(l['Symbol']) for l in positions))
    # Filter out empty roots
    unique_roots = [r for r in unique_roots if r]
    
    # print(f"Fetching live market data for {len(unique_roots)} symbols...") # Moved to main print

    market_data = get_market_data(unique_roots)
    
    # --- Data Freshness Check ---
    now = datetime.now()
    stale_count = sum(1 for d in market_data.values() if d.get('is_stale', False))
    widespread_staleness = len(market_data) > 0 and (stale_count / len(market_data)) > 0.5
        
    all_position_reports = []
    total_beta_delta = 0.0
    total_portfolio_theta = 0.0 # Initialize total portfolio theta
    missing_ivr_legs = 0
    total_option_legs = 0 # Count active option legs for data integrity check

    for legs in clusters:
        root = get_root_symbol(legs[0]['Symbol'])
        
        # Calculate min_dte only for option legs
        option_legs = [l for l in legs if not is_stock_type(l['Type'])]
        total_option_legs += len(option_legs)
        dtes = [parse_dte(l['DTE']) for l in option_legs]
        min_dte = min(dtes) if dtes else 0
        
        strategy_name = identify_strategy(legs)
        net_pl = sum(parse_currency(l['P/L Open']) for l in legs)
        
        strategy_delta = 0.0
        for l in legs:
            b_delta = parse_currency(l['beta_delta'])
            strategy_delta += b_delta
            total_beta_delta += b_delta
            total_portfolio_theta += parse_currency(l['Theta']) # Sum Theta from each leg
            if not str(l['IV Rank']).strip():
                missing_ivr_legs += 1

        net_cost = sum(parse_currency(l['Cost']) for l in legs)
        
        pl_pct = None
        # Treat negatives as credits received, positives as debits paid
        if net_cost < 0:
            max_profit = abs(net_cost)
            if max_profit > 0:
                pl_pct = net_pl / max_profit
        elif net_cost > 0:
            pl_pct = net_pl / net_cost
        
        # Initialize variables
        action = ""
        logic = ""
        is_winner = False
        
        # Retrieve live data
        m_data = market_data.get(root, {})
        vol_bias = m_data.get('vol_bias', 0)
        if vol_bias is None: vol_bias = 0
        
        live_price = m_data.get('price', 0)
        is_stale = m_data.get('is_stale', False)
        earnings_date = m_data.get('earnings_date')
        sector = m_data.get('sector', 'Unknown')
        proxy_note = m_data.get('proxy')

        # 1. Harvest (Short Premium only)
        if net_cost < 0 and pl_pct is not None and pl_pct >= RULES['profit_harvest_pct']:
            action = "🌾 Harvest"
            logic = f"Profit {pl_pct:.1%}"
            is_winner = True
        
        # 2. Defense
        underlying_price = parse_currency(legs[0]['Underlying Last Price'])
        price_used = "static"
        # Use live price if available
        if live_price:
            underlying_price = live_price
            price_used = "live_stale" if is_stale else "live"
            
        is_tested = False
        for l in legs:
            # Only check option legs for "tested" status
            if is_stock_type(l['Type']): continue 
            qty = parse_currency(l['Quantity'])
            otype = l['Call/Put']
            strike = parse_currency(l['Strike Price'])
            if qty < 0:
                if otype == 'Call' and underlying_price > strike: is_tested = True
                elif otype == 'Put' and underlying_price < strike: is_tested = True
        
        if not is_winner and is_tested and min_dte < RULES['gamma_dte_threshold']:
            action = "🛡️ Defense"
            logic = f"Tested & < {RULES['gamma_dte_threshold']} DTE"
            
        # 3. Gamma Zone (apply even if P/L% is unknown)
        if not is_winner and not is_tested and min_dte < RULES['gamma_dte_threshold'] and min_dte > 0:
            action = "☢️ Gamma"
            logic = f"< {RULES['gamma_dte_threshold']} DTE Risk"
            
        # 4. Dead Money (Enhanced with Real-time Vol Bias)
        if not is_winner and not is_tested and min_dte > RULES['gamma_dte_threshold']:
            if pl_pct is not None and RULES['dead_money_pl_pct_low'] <= pl_pct <= RULES['dead_money_pl_pct_high']:
                if vol_bias > 0 and vol_bias < RULES['dead_money_vol_bias_threshold']:
                    action = "🪦 Dead Money"
                    logic = f"Bias {vol_bias:.2f} & Flat P/L"
                elif vol_bias == 0 and 'IV Rank' in legs[0] and parse_currency(legs[0]['IV Rank']) < RULES['low_ivr_threshold']:
                     # Fallback if no live data
                     action = "🪦 Dead Money"
                     logic = "Low IVR (Stale) & Flat P/L"

        # 5. Earnings Warning
        earnings_note = ""
        if earnings_date and earnings_date != "Unavailable":
            try:
                edate = datetime.fromisoformat(earnings_date).date()
                days_to_earn = (edate - datetime.now().date()).days
                if 0 <= days_to_earn <= RULES['earnings_days_threshold']:
                    earnings_note = f"Earnings {days_to_earn}d (Binary Event)"
                    if not action:
                        action = f"⚠️ Earnings ({days_to_earn}d)"
                        logic = "Binary Event Risk"
                    else:
                        logic = f"{logic} | {earnings_note}" if logic else earnings_note
            except:
                pass
        
        price_str = f"${live_price:.2f}" if live_price else "N/A"
        if is_stale:
            price_str += "*"
        bias_str = f"{vol_bias:.2f}" if vol_bias else "N/A"
        if proxy_note:
            bias_str += f" ({proxy_note})"

        if (price_used != "live" or is_stale) and not is_winner and min_dte < 21:
            # If we can't rely fully on tested logic due to stale/absent live price, note it
            note = "Price stale/absent; tested status uncertain"
            if action in ["🛡️ Defense", "☢️ Gamma"]:
                logic = f"{logic} | {note}" if logic else note
            elif not action:
                action = ""
                logic = note

        all_position_reports.append({
            'root': root,
            'strategy_name': strategy_name,
            'price_str': price_str,
            'bias_str': bias_str,
            'net_pl': net_pl,
            'pl_pct': pl_pct,
            'min_dte': min_dte,
            'action': action,
            'logic': logic,
            'sector': sector,
            'delta': strategy_delta
        })
    
    # --- Generate Structured Report Data ---
    report = {
        "analysis_time": now.strftime('%Y-%m-%d %H:%M:%S'),
        "data_freshness_warning": widespread_staleness,
        "market_data_symbols_count": len(unique_roots),
        "triage_actions": [],
        "portfolio_overview": [],
        "portfolio_summary": {
            "total_beta_delta": total_beta_delta,
            "total_portfolio_theta": total_portfolio_theta,
            "theta_net_liquidity_pct": 0.0,
            "theta_status": "N/A",
            "delta_status": "N/A"
        },
        "data_integrity_warning": {"risk": False, "details": ""},
        "delta_spectrograph": [],
        "sector_balance": [],
        "sector_concentration_warning": {"risk": False},
        "asset_mix": [],
        "asset_mix_warning": {"risk": False, "details": ""},
        "caution_items": [],
        "stress_box": None
    }

    # Populate Triage Actions
    for r in all_position_reports:
        if r['action']:
            report['triage_actions'].append({
                "symbol": r['root'],
                "strategy": r['strategy_name'],
                "price": r['price_str'],
                "vol_bias": r['bias_str'],
                "net_pl": r['net_pl'],
                "pl_pct": f"{r['pl_pct']:.1%}" if r['pl_pct'] is not None else "N/A",
                "dte": f"{r['min_dte']}d",
                "action": r['action'],
                "logic": r['logic']
            })
        else:
            report['portfolio_overview'].append({
                "symbol": r['root'],
                "strategy": r['strategy_name'],
                "price": r['price_str'],
                "vol_bias": r['bias_str'],
                "net_pl": r['net_pl'],
                "pl_pct": f"{r['pl_pct']:.1%}" if r['pl_pct'] is not None else "N/A",
                "dte": f"{r['min_dte']}d",
                "status": "Hold"
            })

    # Populate Portfolio Summary
    net_liq = RULES['net_liquidity']
    if net_liq > 0:
        theta_as_pct_of_nl = (total_portfolio_theta / net_liq) * 100
        report['portfolio_summary']['theta_net_liquidity_pct'] = theta_as_pct_of_nl
        if 0.1 <= theta_as_pct_of_nl <= 0.5:
            report['portfolio_summary']['theta_status'] = "Healthy (0.1% - 0.5% of Net Liq/day)"
        elif theta_as_pct_of_nl < 0.1:
            report['portfolio_summary']['theta_status'] = "Low. Consider adding more short premium."
        else:
            report['portfolio_summary']['theta_status'] = "High. Consider reducing overall premium sold or managing gamma risk."
    
    if total_beta_delta > RULES['portfolio_delta_long_threshold']:
        report['portfolio_summary']['delta_status'] = f"Too Long (Delta > {RULES['portfolio_delta_long_threshold']})"
    elif total_beta_delta < RULES['portfolio_delta_short_threshold']:
        report['portfolio_summary']['delta_status'] = f"Too Short (Delta < {RULES['portfolio_delta_short_threshold']})"
    else:
        report['portfolio_summary']['delta_status'] = "Delta Neutral-ish"

    # Data Integrity Guardrail
    if total_option_legs > 0 and abs(total_beta_delta) < 5.0 and total_portfolio_theta < 5.0:
        report['data_integrity_warning']['risk'] = True
        report['data_integrity_warning']['details'] = "Your Delta/Theta totals are suspiciously low. Ensure your CSV contains TOTAL position values (Contract Qty * 100), not per-share Greeks. Risk metrics (Stress Box) may be understated by 100x."

    # Populate Delta Spectrograph
    root_deltas = defaultdict(float)
    for r in all_position_reports:
        root_deltas[r['root']] += r['delta']
    sorted_deltas = sorted(root_deltas.items(), key=lambda x: abs(x[1]), reverse=True)
    max_delta = max([abs(d) for r, d in sorted_deltas]) if sorted_deltas else 1.0
    if max_delta == 0: max_delta = 1.0
    for root, delta in sorted_deltas[:10]:
        bar_len = int((abs(delta) / max_delta) * 20)
        bar = "█" * bar_len
        report['delta_spectrograph'].append({
            "symbol": root,
            "delta": delta,
            "bar": bar.ljust(20) # Add padding for consistent output
        })

    # Populate Sector Balance
    sector_counts = defaultdict(int)
    for r in all_position_reports:
        sector_counts[r['sector']] += 1
    total_positions = len(all_position_reports)
    sorted_sectors = sorted(sector_counts.items(), key=lambda x: x[1], reverse=True)
    for sec, count in sorted_sectors:
        pct = count / total_positions if total_positions > 0 else 0
        report['sector_balance'].append({
            "sector": sec,
            "count": count,
            "percentage": f"{pct:.0%}"
        })
    
    concentrations = []
    for sec, count in sorted_sectors:
        pct = count / total_positions if total_positions > 0 else 0
        if pct > RULES['concentration_risk_pct']:
            concentrations.append(f"{sec} ({count} pos, {pct:.0%})")
    if concentrations:
        report['sector_concentration_warning'] = {
            "risk": True,
            "details": f"High exposure to {', '.join(concentrations)}."
        }
    else:
        report['sector_concentration_warning'] = {"risk": False}

    # Calculate Asset Mix (Equity, Commodity, Fixed Income, FX, Index)
    asset_class_counts = defaultdict(int)
    for r in all_position_reports:
        asset_class = map_sector_to_asset_class(r['sector'])
        asset_class_counts[asset_class] += 1

    # Build asset_mix dictionary with percentages
    for asset_class, count in asset_class_counts.items():
        pct = count / total_positions if total_positions > 0 else 0
        report['asset_mix'].append({
            "asset_class": asset_class,
            "count": count,
            "percentage": pct  # Store as float for programmatic use
        })

    # Sort by count descending
    report['asset_mix'].sort(key=lambda x: x['count'], reverse=True)

    # Check for Equity Heavy (> 80%)
    equity_pct = 0.0
    for item in report['asset_mix']:
        if item['asset_class'] == 'Equity':
            equity_pct = item['percentage']
            break

    if equity_pct > 0.80:
        report['asset_mix_warning'] = {
            "risk": True,
            "details": f"Equity exposure is {equity_pct:.0%}. Portfolio is correlation-heavy. Consider adding Commodities, FX, or Fixed Income."
        }
    else:
        report['asset_mix_warning'] = {"risk": False}

    # Populate Caution Items
    for r in all_position_reports:
        if "stale" in r['logic'].lower():
            report['caution_items'].append(f"{r['root']}: price stale/absent; tested status uncertain")
        if "Earnings" in r.get('action', "") or "Binary Event" in r.get('logic', ""):
            report['caution_items'].append(f"{r['root']}: earnings soon (see action/logic)")

    # Stress Box (Scenario Simulator)
    beta_sym = RULES.get('beta_weighted_symbol', 'SPY') # Default to SPY if missing
    beta_price = 0.0
    if beta_sym in market_data:
        beta_price = market_data[beta_sym].get('price', 0.0)
    else:
        try:
            beta_data = get_market_data([beta_sym])
            beta_price = beta_data.get(beta_sym, {}).get('price', 0.0)
        except:
            pass
            
    if beta_price > 0:
        scenarios = [
            ("Crash (-5%)", -0.05),
            ("Dip (-3%)", -0.03),
            ("Flat", 0.0),
            ("Rally (+3%)", 0.03),
            ("Moon (+5%)", 0.05)
        ]
        stress_box_scenarios = []
        for label, pct in scenarios:
            spy_points = beta_price * pct
            est_pl = total_beta_delta * spy_points
            stress_box_scenarios.append({
                "label": label,
                "beta_move": spy_points,
                "est_pl": est_pl
            })
        report['stress_box'] = {
            "beta_symbol": beta_sym,
            "beta_price": beta_price,
            "scenarios": stress_box_scenarios
        }

    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Analyze current portfolio positions and generate a triage report.')
    parser.add_argument('file_path', type=str, help='Path to the portfolio CSV file.')
    parser.add_argument('--json', action='store_true', help='Output results in JSON format.')
    
    args = parser.parse_args()
    
    warn_if_not_venv()
    report_data = analyze_portfolio(args.file_path)
    
    if "error" in report_data:
        print(json.dumps(report_data, indent=2), file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(report_data, indent=2))
    else:
        # Markdown output
        print(f"Fetching live market data for {report_data['market_data_symbols_count']} symbols...")
        print(f"\n**Analysis Time:** {report_data['analysis_time']}")
        if report_data['data_freshness_warning']:
            print("🚨 **WARNING:** > 50% of data points are marked STALE. Markets may be closed or data delayed.")
            print("   *Verify prices before executing trades.*")
        
        # Triage Report
        print("\n### Triage Report")
        print("| Symbol | Strat | Price | Vol Bias | Net P/L | P/L % | DTE | Action | Logic |")
        print("|---|---|---|---|---|---|---|---|---|")
        if report_data['triage_actions']:
            for item in report_data['triage_actions']:
                print(f"| {item['symbol']} | {item['strategy']} | {item['price']} | {item['vol_bias']} | ${item['net_pl']:.2f} | {item['pl_pct']} | {item['dte']} | {item['action']} | {item['logic']} |")
        else:
            print("No specific triage actions triggered for current positions.")
        
        # Portfolio Overview
        print("\n### Portfolio Overview (Non-Actionable Positions)")
        print("| Symbol | Strat | Price | Vol Bias | Net P/L | P/L % | DTE | Status |")
        print("|---|---|---|---|---|---|---|---|")
        if report_data['portfolio_overview']:
            for item in report_data['portfolio_overview']:
                print(f"| {item['symbol']} | {item['strategy']} | {item['price']} | {item['vol_bias']} | ${item['net_pl']:.2f} | {item['pl_pct']} | {item['dte']} | {item['status']} |")
        else:
            print("No non-actionable positions to display.")
        
        # Portfolio Summary
        print(f"\n\n**Total Beta Weighted Delta:** {report_data['portfolio_summary']['total_beta_delta']:.2f}")
        print(f"**Total Portfolio Theta:** ${report_data['portfolio_summary']['total_portfolio_theta']:.2f}/day")
        print(f"**Theta/Net Liquidity:** {report_data['portfolio_summary']['theta_net_liquidity_pct']:.2f}%/day")
        # The original print had a hardcoded '⚠️' for theta status, but the new structure provides the status string directly.
        # We'll use the provided status string directly.
        print(f"**Theta Status:** {report_data['portfolio_summary']['theta_status']}")
        print(f"**Status:** {report_data['portfolio_summary']['delta_status']}")

        # Data Integrity Guardrail
        if report_data['data_integrity_warning']['risk']:
            print("\n🚨 **DATA INTEGRITY WARNING:**")
            print(f"   {report_data['data_integrity_warning']['details']}")
            
        # Delta Spectrograph
        print("\n### The Delta Spectrograph (Risk Visualization)")
        if report_data['delta_spectrograph']:
            for item in report_data['delta_spectrograph']:
                print(f"{item['symbol']:<6} [{item['bar']}] {item['delta']:+.1f}")
        
        # Sector Balance
        print("\n### Sector Balance (Rebalancing Context)")
        if report_data['sector_balance']:
            print("| Sector | Count | Percentage |")
            print("|---|---|---|")
            for item in report_data['sector_balance']:
                print(f"| {item['sector']} | {item['count']} | {item['percentage']} |")
        if report_data['sector_concentration_warning']['risk']:
            print(f"⚠️ **Concentration Risk:** {report_data['sector_concentration_warning']['details']}")
            print("   *Advice:* Look for new trades in under-represented sectors to reduce correlation.")
        else:
            print("✅ **Sector Balance:** Good. No significant sector concentration detected.")

        # Asset Mix
        print("\n### Asset Mix (Correlation Defense)")
        if report_data['asset_mix']:
            print("| Asset Class | Count | Percentage |")
            print("|---|---|---|")
            for item in report_data['asset_mix']:
                print(f"| {item['asset_class']} | {item['count']} | {item['percentage']:.0%} |")
        if report_data['asset_mix_warning']['risk']:
            print(f"⚠️ **Equity Heavy:** {report_data['asset_mix_warning']['details']}")
            print("   *Advice:* Use --exclude-sectors to filter Equity sectors from vol_screener.py. Target Commodities (/GC, /CL), FX (/6E, /6J), or Fixed Income (/ZB, /ZN).")
        else:
            print("✅ **Asset Mix:** Diversified. Good correlation defense.")

        # Caution Items
        if report_data['caution_items']:
            print("\n### Caution")
            for item in report_data['caution_items']:
                print(f"- {item}")
        
        # Stress Box
        print("\n### 📉 The Stress Box (Scenario Simulator)")
        if report_data['stress_box']:
            beta_sym = report_data['stress_box']['beta_symbol']
            print(f"Based on Portfolio Delta ({report_data['portfolio_summary']['total_beta_delta']:.2f}) and {beta_sym} Price (${report_data['stress_box']['beta_price']:.2f}):")
            print("| Scenario | Est. {beta_sym} Move | Est. Portfolio P/L |")
            print("|---|---|---|")
            for item in report_data['stress_box']['scenarios']:
                print(f"| {item['label']:<11} | {item['beta_move']:.2f} pts | ${item['est_pl']:.2f} |")
        else:
            print("Could not fetch Beta-Weighted symbol price for stress testing.")
