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
    # Handle Futures: ./CLG6 LOG6 ... -> /CL
    if raw_symbol.startswith('./'):
        parts = raw_symbol.split(' ')
        base = parts[0]
        base = base.replace('./', '/')
        return base[:3] 
    
    parts = raw_symbol.split('  ')
    return parts[0].strip()

def cluster_strategies(positions):
    # 1. Group by Root Symbol
    by_root = defaultdict(list)
    for row in positions:
        root = get_root_symbol(row['Symbol'])
        by_root[root].append(row)

    clusters = [] 

    for root, legs in by_root.items():
        by_exp = defaultdict(list)
        for leg in legs:
            by_exp[leg['Exp Date']].append(leg)
        
        fragments = []
        
        for exp, exp_legs in by_exp.items():
            strat_name = identify_strategy(exp_legs)
            if strat_name not in ["Single Option", "Stock"]:
                 clusters.append(exp_legs)
            else:
                fragments.extend(exp_legs)

        used_indices = set()
        long_calls = []
        short_calls = []
        long_puts = []
        short_puts = []
        
        for i, leg in enumerate(fragments):
            qty = parse_currency(leg['Quantity'])
            otype = leg['Call/Put']
            # Improved check: Ensure it is actually stock
            if leg['Type'] == 'STOCK':
                clusters.append([leg])
                used_indices.add(i)
                continue

            if otype == 'Call':
                if qty > 0: long_calls.append((i, leg))
                else: short_calls.append((i, leg))
            elif otype == 'Put':
                if qty > 0: long_puts.append((i, leg))
                else: short_puts.append((i, leg))

        # Match Time Spreads (Call)
        for si, s_leg in short_calls:
            if si in used_indices: continue
            s_strike = parse_currency(s_leg['Strike Price'])
            best_match = -1
            for li, l_leg in long_calls:
                if li in used_indices: continue
                l_strike = parse_currency(l_leg['Strike Price'])
                if s_strike == l_strike and s_leg['Exp Date'] != l_leg['Exp Date']:
                    best_match = li
                    break
            
            if best_match != -1:
                used_indices.add(si)
                used_indices.add(best_match)
                clusters.append([s_leg, fragments[best_match]])
            else:
                # Try Diagonals
                for li, l_leg in long_calls:
                    if li in used_indices: continue
                    if s_leg['Exp Date'] != l_leg['Exp Date']:
                         best_match = li
                         break
                if best_match != -1:
                    used_indices.add(si)
                    used_indices.add(best_match)
                    clusters.append([s_leg, fragments[best_match]])

        # Match Time Spreads (Put)
        for si, s_leg in short_puts:
            if si in used_indices: continue
            s_strike = parse_currency(s_leg['Strike Price'])
            best_match = -1
            for li, l_leg in long_puts:
                if li in used_indices: continue
                l_strike = parse_currency(l_leg['Strike Price'])
                if s_strike == l_strike and s_leg['Exp Date'] != l_leg['Exp Date']:
                    best_match = li
                    break
            
            if best_match != -1:
                used_indices.add(si)
                used_indices.add(best_match)
                clusters.append([s_leg, fragments[best_match]])
            else:
                # Try Diagonals
                for li, l_leg in long_puts:
                    if li in used_indices: continue
                    if s_leg['Exp Date'] != l_leg['Exp Date']:
                         best_match = li
                         break
                if best_match != -1:
                    used_indices.add(si)
                    used_indices.add(best_match)
                    clusters.append([s_leg, fragments[best_match]])

        for i, leg in enumerate(fragments):
            if i not in used_indices:
                clusters.append([leg])

    return clusters

def identify_strategy(legs):
    if len(legs) == 1:
        leg = legs[0]
        if leg['Type'] == 'STOCK': return "Stock"
        return "Single Option"
    
    expirations = set(l['Exp Date'] for l in legs if l['Type'] != 'STOCK')
    is_multi_exp = len(expirations) > 1

    long_calls = 0
    short_calls = 0
    long_puts = 0
    short_puts = 0
    
    long_call_qty = 0
    short_call_qty = 0
    long_put_qty = 0
    short_put_qty = 0
    
    stock_legs = 0
    
    short_call_strikes = []
    short_put_strikes = []
    long_call_strikes = []
    long_put_strikes = []

    for leg in legs:
        try:
            qty = parse_currency(leg['Quantity'])
        except ValueError:
            qty = 0
        
        if leg['Type'] == 'STOCK':
            stock_legs += 1
            continue

        otype = leg['Call/Put']
        strike = parse_currency(leg.get('Strike Price', '0'))

        if otype == 'Call':
            if qty > 0: 
                long_calls += 1
                long_call_qty += abs(qty)
                long_call_strikes.append(strike)
            else: 
                short_calls += 1
                short_call_qty += abs(qty)
                short_call_strikes.append(strike)
        elif otype == 'Put':
            if qty > 0: 
                long_puts += 1
                long_put_qty += abs(qty)
                long_put_strikes.append(strike)
            else: 
                short_puts += 1
                short_put_qty += abs(qty)
                short_put_strikes.append(strike)
            
    total_opt_legs = len([l for l in legs if l['Type'] != 'STOCK'])
    
    if is_multi_exp:
        if total_opt_legs == 2:
            if short_calls == 1 and long_calls == 1:
                if short_call_strikes and long_call_strikes and short_call_strikes[0] == long_call_strikes[0]:
                    return "Calendar Spread (Call)"
                return "Diagonal Spread (Call)"
            if short_puts == 1 and long_puts == 1:
                if short_put_strikes and long_put_strikes and short_put_strikes[0] == long_put_strikes[0]:
                    return "Calendar Spread (Put)"
                return "Diagonal Spread (Put)"
        if total_opt_legs == 4:
             return "Double Diagonal / Calendar"
        return "Custom/Combo (Multi-Exp)"

    if total_opt_legs == 4:
        if short_calls > 0 and short_puts > 0 and long_calls > 0 and long_puts > 0:
            if short_call_strikes and short_put_strikes and short_call_strikes[0] == short_put_strikes[0]:
                 return "Iron Butterfly"
            return "Iron Condor"
    
    if total_opt_legs == 3:
        if short_puts >= 1 and short_calls >= 1 and long_calls >= 1 and long_puts == 0:
            return "Jade Lizard"
        if short_calls >= 1 and short_puts >= 1 and long_puts >= 1 and long_calls == 0:
            return "Twisted Sister"
        if long_calls == 2 and short_calls == 1: return "Long Call Butterfly"
        if long_puts == 2 and short_puts == 1: return "Long Put Butterfly"

    if total_opt_legs == 2 and stock_legs == 0:
        if short_calls >= 1 and short_puts >= 1: return "Strangle"
        if (long_calls >= 1 and short_calls >= 1):
            if long_call_qty != short_call_qty: return "Ratio Spread (Call)"
            return "Vertical Spread (Call)"
        if (long_puts >= 1 and short_puts >= 1):
            if long_put_qty != short_put_qty: return "Ratio Spread (Put)"
            return "Vertical Spread (Put)"

    if stock_legs > 0:
        if total_opt_legs == 1:
            if short_calls > 0: return "Covered Call"
            if short_puts > 0: return "Covered Put"
        if total_opt_legs == 2:
            if short_calls > 0 and short_puts > 0: return "Covered Strangle"
            if long_puts > 0 and short_calls > 0: return "Collar"

    if total_opt_legs == 0 and stock_legs > 0:
        return "Stock Position"

    return "Custom/Combo"

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
    
    for legs in clusters:
        root = get_root_symbol(legs[0]['Symbol'])
        dtes = [parse_dte(l['DTE']) for l in legs]
        min_dte = min(dtes) if dtes else 0
        
        strategy_name = identify_strategy(legs)
        net_pl = sum(parse_currency(l['P/L Open']) for l in legs)
        
        for l in legs:
            total_beta_delta += parse_currency(l['beta_delta'])

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
        if earnings_date:
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

if __name__ == "__main__":
    file_path = "sample_positions.csv"
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    analyze_portfolio(file_path)