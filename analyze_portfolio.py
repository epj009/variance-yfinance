import csv
import sys
from collections import defaultdict
from datetime import datetime
from get_market_data import get_market_data

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
        'beta_delta': ['β Delta', 'Beta Delta', 'Delta Beta', 'Weighted Delta']
    }

    @staticmethod
    def normalize_row(row):
        normalized = {}
        for internal_key, aliases in PortfolioParser.MAPPING.items():
            found = False
            for alias in aliases:
                if alias in row:
                    normalized[internal_key] = row[alias]
                    found = True
                    break
            if not found:
                normalized[internal_key] = ""
        return normalized

    @staticmethod
    def parse(file_path):
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
    if not value:
        return 0
    clean = value.replace('d', '').strip()
    try:
        return int(clean)
    except ValueError:
        return 0

def get_root_symbol(raw_symbol):
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
    normalized = type_str.strip().lower()
    return normalized in {"stock", "equity", "equities", "equity stock"}

def identify_strategy(legs):
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
        if short_calls == 1 and long_calls == 1 and short_puts == 1 and long_puts == 1:
            if short_call_strikes and short_put_strikes and short_call_strikes[0] == short_put_strikes[0]:
                 return "Iron Butterfly"
            return "Iron Condor"
    
    if total_opt_legs == 3:
        if short_puts >= 1 and short_calls >= 1 and long_calls >= 1 and long_puts == 0:
            return "Jade Lizard"
        if short_calls >= 1 and short_puts >= 1 and long_puts >= 1 and long_calls == 0:
            return "Twisted Sister"
        if long_calls == 2 and short_calls == 1 and long_call_qty == abs(short_call_qty): return "Long Call Butterfly"
        if long_puts == 2 and short_puts == 1 and long_put_qty == abs(short_put_qty): return "Long Put Butterfly"

    if total_opt_legs == 2:
        if short_calls >= 1 and short_puts >= 1: return "Strangle"
        if (long_calls >= 1 and short_calls >= 1):
            if long_call_qty != short_call_qty: return "Ratio Spread (Call)"
            return "Vertical Spread (Call)"
        if (long_puts >= 1 and short_puts >= 1):
            if long_put_qty != short_put_qty: return "Ratio Spread (Put)"
            return "Vertical Spread (Put)"

    return "Custom/Combo"

def cluster_strategies(positions):
    """
    Groups positions by Root, then identifies multi-leg strategies,
    including stock-option combinations like Covered Calls.
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
        
        # Used flags for options within this root
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

def analyze_portfolio(file_path):
    # 1. Parse CSV
    positions = PortfolioParser.parse(file_path)
    if not positions:
        return

    # 2. Cluster Strategies
    clusters = cluster_strategies(positions)
    
    # 3. Gather Unique Roots for Live Data
    unique_roots = list(set(get_root_symbol(l['Symbol']) for l in positions))
    # Filter out empty roots
    unique_roots = [r for r in unique_roots if r]
    
    print(f"Fetching live market data for {len(unique_roots)} symbols...")
    market_data = get_market_data(unique_roots)
        
    # 4. Analysis Loop
    print("\n### Morning Triage Report")
    # Expanded Header
    print("| Symbol | Strat | Price | Vol Bias | Net P/L | P/L % | DTE | Action | Logic |")
    print("|---|---|---|---|---|---|---|---|---|")
    
    total_beta_delta = 0.0
    has_actions = False # Initialize flag
    missing_ivr_legs = 0
    
    for legs in clusters:
        root = get_root_symbol(legs[0]['Symbol'])
        
        # Calculate min_dte only for option legs
        option_legs = [l for l in legs if not is_stock_type(l['Type'])]
        dtes = [parse_dte(l['DTE']) for l in option_legs]
        min_dte = min(dtes) if dtes else 0
        
        strategy_name = identify_strategy(legs)
        net_pl = sum(parse_currency(l['P/L Open']) for l in legs)

        for l in legs:
            total_beta_delta += parse_currency(l['beta_delta'])
            if not str(l['IV Rank']).strip():
                missing_ivr_legs += 1

        net_cost = sum(parse_currency(l['Cost']) for l in legs)
        
        pl_pct = 0.0
        if net_cost < 0: # Credit Trade (Received money)
            max_profit = abs(net_cost)
            if max_profit > 0:
                pl_pct = net_pl / max_profit
        elif net_cost > 0: # Debit Trade (Paid money)
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

        # 1. Harvest (Short Premium only)
        if net_cost < 0 and pl_pct >= 0.50:
            action = "✅ Harvest"
            logic = f"Profit {pl_pct:.1%}"
            is_winner = True
        
        # 2. Defense
        underlying_price = parse_currency(legs[0]['Underlying Last Price'])
        # Use live price if available
        if live_price:
            underlying_price = live_price
            
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
        
        if not is_winner and is_tested and min_dte < 21:
            action = "🛠️ Defense"
            logic = "Tested & < 21 DTE"
            
        # 3. Gamma Zone
        if not is_winner and not is_tested and min_dte < 21 and min_dte > 0:
            action = "☢️ Gamma"
            logic = "< 21 DTE Risk"
            
        # 4. Zombie (Enhanced with Real-time Vol Bias)
        if not is_winner and not is_tested and min_dte > 21:
            if -0.10 <= pl_pct <= 0.10:
                if vol_bias > 0 and vol_bias < 0.80:
                    action = "🗑️ Zombie"
                    logic = f"Bias {vol_bias:.2f} & Flat P/L"
                elif vol_bias == 0 and 'IV Rank' in legs[0] and parse_currency(legs[0]['IV Rank']) < 20:
                     # Fallback if no live data
                     action = "🗑️ Zombie"
                     logic = "Low IVR (Stale) & Flat P/L"

        # 5. Earnings Warning
        if earnings_date and earnings_date != "Unavailable":
            try:
                edate = datetime.fromisoformat(earnings_date).date()
                days_to_earn = (edate - datetime.now().date()).days
                if 0 <= days_to_earn <= 5:
                    action = f"⚠️ Earnings ({days_to_earn}d)" 
                    logic = "Binary Event Risk"
            except:
                pass

        if action:
            price_str = f"${live_price:.2f}" if live_price else "N/A"
            if is_stale:
                price_str += "*"
            bias_str = f"{vol_bias:.2f}" if vol_bias else "N/A"
            print(f"| {root} | {strategy_name} | {price_str} | {bias_str} | ${net_pl:.2f} | {pl_pct:.1%} | {min_dte}d | {action} | {logic} |")
            has_actions = True # Set flag if an action was printed

    if not has_actions:
        print("No specific triage actions triggered for current positions.")

    print("\n")
    print(f"**Total Beta Weighted Delta:** {total_beta_delta:.2f}")
    
    if total_beta_delta > 75:
        print("⚠️ **Status:** Too Long (Delta > 75)")
    elif total_beta_delta < -50:
        print("⚠️ **Status:** Too Short (Delta < -50)")
    else:
        print("✅ **Status:** Delta Neutral-ish")

    if missing_ivr_legs > 0:
        print(f"Note: IV Rank data missing for {missing_ivr_legs} legs; Zombie checks may fall back to live Vol Bias only.")

if __name__ == "__main__":
    file_path = "sample_positions.csv"
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    analyze_portfolio(file_path)
