import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Any

from get_market_data import get_market_data

# Import common utilities
try:
    from .common import map_sector_to_asset_class, warn_if_not_venv
except ImportError:
    # Fallback for direct script execution
    from common import map_sector_to_asset_class, warn_if_not_venv

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
        'Call/Put': ['Call/Put', 'Side', 'C/P'],
        'Underlying Last Price': ['Underlying Last Price', 'Underlying Price', 'Current Price'],
        'P/L Open': ['P/L Open', 'P/L Day', 'Unrealized P/L'],
        'Cost': ['Cost', 'Cost Basis', 'Trade Price'],
        'IV Rank': ['IV Rank', 'IVR', 'IV Percentile'],
        'beta_delta': ['β Delta', 'Beta Delta', 'Delta Beta', 'Weighted Delta'],
        'Theta': ['Theta', 'Theta Daily', 'Daily Theta'],
        'Bid': ['Bid', 'Bid Price'],
        'Ask': ['Ask', 'Ask Price'],
        'Mark': ['Mark', 'Mark Price', 'Mid']
    }

    @staticmethod
    def normalize_row(row: Dict[str, str]) -> Dict[str, str]:
        """
        Convert a raw CSV row into a normalized dictionary using MAPPING.
        
        Args:
            row: A single row from the CSV reader.
            
        Returns:
            A dictionary with standard keys (Symbol, Type, etc.) and normalized values.
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
    def parse(file_path: str) -> List[Dict[str, str]]:
        """
        Read and parse the CSV file at the given path.
        
        Args:
            file_path: Path to the CSV file.
            
        Returns:
            A list of normalized position rows.
            
        Raises:
            FileNotFoundError: If the file does not exist.
            csv.Error: If there's an error parsing the CSV.
        """
        positions = []
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    positions.append(PortfolioParser.normalize_row(row))
        except FileNotFoundError:
            print(f"Error: File not found: {file_path}", file=sys.stderr)
            raise
        except csv.Error as e:
            print(f"Error parsing CSV: {e}", file=sys.stderr)
            raise
        except Exception as e:
            print(f"Error reading CSV: {e}", file=sys.stderr)
            raise
        return positions

def parse_currency(value: Optional[str]) -> float:
    """
    Clean and convert currency strings (e.g., '$1,234.56') to floats.
    
    Args:
        value: Currency string that may contain $, commas, or % symbols.
        
    Returns:
        Float value, or 0.0 if parsing fails.
    """
    if not value:
        return 0.0
    clean = value.replace(',', '').replace('$', '').replace('%', '').strip()
    if clean == '--':
        return 0.0
    try:
        return float(clean)
    except ValueError:
        return 0.0

def parse_dte(value: Optional[str]) -> int:
    """
    Clean and convert DTE strings (e.g., '45d') to integers.
    
    Args:
        value: DTE string that may contain 'd' suffix.
        
    Returns:
        Integer value, or 0 if parsing fails.
    """
    if not value:
        return 0
    clean = value.replace('d', '').strip()
    try:
        return int(clean)
    except ValueError:
        return 0

def get_root_symbol(raw_symbol: Optional[str]) -> str:
    """
    Extract the root symbol from a ticker, handling futures (e.g., /ESZ4 -> /ES).
    
    Args:
        raw_symbol: Raw symbol string that may include expiration codes.
        
    Returns:
        Root symbol string.
    """
    if not raw_symbol:
        return ""
    # Normalize multi-space and single-space separated symbols
    token = raw_symbol.strip().split()[0] if raw_symbol else ""

    # Handle Futures: ./CLG6 LOG6 ... -> /CL
    if token.startswith('./'):
        token = token.replace('./', '/')

    # Futures roots like /ESZ4 -> /ES
    if token.startswith('/') and len(token) >= 3:
        return token[:3]

    return token

def is_stock_type(type_str: Optional[str]) -> bool:
    """
    Determine if a position leg is underlying stock/equity.
    
    Args:
        type_str: Type string from the position data.
        
    Returns:
        True if the type represents stock/equity, False otherwise.
    """
    if not type_str:
        return False
    normalized = type_str.strip().lower()
    return normalized in {"stock", "equity", "equities", "equity stock"}

def identify_strategy(legs: List[Dict[str, Any]]) -> str:
    """
    Identify the option strategy based on a list of position legs.
    
    Analyzes the combination of Calls/Puts, Long/Short quantities, and strike prices
    to name the complex strategy (e.g., 'Iron Condor', 'Strangle', 'Covered Call').
    
    Args:
        legs: A list of normalized position legs belonging to one symbol group.
        
    Returns:
        The name of the strategy.
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

def calculate_slippage_status(bid: float, ask: float) -> str:
    """
    Determine slippage status based on bid/ask spread.
    Returns 'TIGHT' when spread <= 0.05, 'WIDE' when spread > 0.05 and spread/midpoint > 0.10, otherwise 'NORMAL'.
    """
    spread = ask - bid
    if spread <= 0.05:
        return "TIGHT"

    midpoint = (ask + bid) / 2
    relative_spread = spread / midpoint if midpoint != 0 else float("inf")

    if relative_spread > 0.10:
        return "WIDE"
    return "NORMAL"

def cluster_strategies(positions: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """
    Group individual position legs into logical strategies (e.g., combining a short call and short put into a Strangle).
    
    Logic:
    1. Group all legs by Root Symbol.
    2. Within each Root:
       a. Group options by Expiration Date to find standard vertical/horizontal spreads.
       b. Match Stock legs with remaining Option legs to find Covered Calls/Collars.
       
    Args:
        positions: List of flat position rows.
        
    Returns:
        A list of lists, where each inner list is a group of legs forming a strategy.
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


def analyze_portfolio(file_path: str) -> Dict[str, Any]:
    """
    Main entry point for Portfolio Analysis (Portfolio Triage).
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

    market_data = get_market_data(unique_roots)
    
    # --- Data Freshness Check ---
    now = datetime.now()
    stale_count = sum(1 for d in market_data.values() if d.get('is_stale', False))
    widespread_staleness = len(market_data) > 0 and (stale_count / len(market_data)) > 0.5
        
    all_position_reports = []
    total_beta_delta = 0.0
    total_portfolio_theta = 0.0 # Initialize total portfolio theta
    total_liquidity_cost = 0.0 # Numerator for Friction Horizon (Φ)
    total_abs_theta = 0.0 # Denominator for Friction Horizon (Φ)
    missing_ivr_legs = 0
    total_option_legs = 0 # Count active option legs for data integrity check

    for legs in clusters:
        if not legs:
            continue
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
            
            leg_theta = parse_currency(l['Theta'])
            total_portfolio_theta += leg_theta # Sum Net Theta
            total_abs_theta += abs(leg_theta) # Sum Abs Theta for Friction Engine
            
            # Friction Horizon: Calculate liquidity cost (Ask - Bid) * Qty * Multiplier
            # We must convert Unit Price Spread -> Total Dollar Cost to match Total Dollar Theta.
            bid = parse_currency(l['Bid'])
            ask = parse_currency(l['Ask'])
            qty = abs(parse_currency(l['Quantity']))
            
            if ask > bid and qty > 0:
                spread = ask - bid
                
                # Standard Option Multiplier is 100.
                # For Futures, we attempt a best-effort match, otherwise default to 100.
                multiplier = 100.0
                sym = l['Symbol'].upper()
                if sym.startswith('/'):
                    if '/ES' in sym: multiplier = 50
                    elif '/NQ' in sym: multiplier = 20
                    elif '/CL' in sym: multiplier = 1000
                    elif '/GC' in sym: multiplier = 100
                    elif '/MES' in sym: multiplier = 5
                    elif '/MNQ' in sym: multiplier = 2
                    elif '/ZB' in sym: multiplier = 1000
                    elif '/ZN' in sym: multiplier = 1000
                
                liquidity_cost = spread * qty * multiplier
                total_liquidity_cost += liquidity_cost

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
            action = "✅ Harvest"
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
                    action = "💀 Zombie"
                    logic = f"Bias {vol_bias:.2f} & Flat P/L"
                elif vol_bias == 0 and 'IV Rank' in legs[0] and parse_currency(legs[0]['IV Rank']) < RULES['low_ivr_threshold']:
                     # Fallback if no live data
                     action = "💀 Zombie"
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
            except (ValueError, TypeError):
                pass
        
        price_str = f"${live_price:.2f}" if live_price else "N/A"
        if is_stale:
            price_str += "*"
        bias_str = f"{vol_bias:.2f}" if vol_bias else "N/A"
        if proxy_note:
            bias_str += f" ({proxy_note})"

        if (price_used != "live" or is_stale) and not is_winner and min_dte < RULES['gamma_dte_threshold']:
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
    
    # Calculate Friction Horizon (Φ)
    # How many days of Theta does it take to pay for the Spread?
    friction_horizon_days = 0.0
    if total_abs_theta > 1.0: # Avoid div/0 and noise
        friction_horizon_days = total_liquidity_cost / total_abs_theta
    elif total_liquidity_cost > 0:
        friction_horizon_days = 99.9 # Infinite friction (trapped)
    
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
            "friction_horizon_days": friction_horizon_days,
            "friction_status": "Liquid" if friction_horizon_days < 1.0 else ("Sticky" if friction_horizon_days < 3.0 else "Liquidity Trap"),
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
        "stress_box": None,
        "health_check": {
            "liquidity_warnings": [f'{r["root"]}: Wide spread detected' for r in all_position_reports if r.get('liquidity_status') == 'WIDE']
        }
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
    
    # Delta/Theta Ratio
    if total_portfolio_theta != 0:
        report['portfolio_summary']['delta_theta_ratio'] = total_beta_delta / total_portfolio_theta
    else:
        report['portfolio_summary']['delta_theta_ratio'] = 0.0

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
        except Exception:
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
    
    args = parser.parse_args()
    
    warn_if_not_venv()
    report_data = analyze_portfolio(args.file_path)
    
    if "error" in report_data:
        print(json.dumps(report_data, indent=2), file=sys.stderr)
        sys.exit(1)

    print(json.dumps(report_data, indent=2))
