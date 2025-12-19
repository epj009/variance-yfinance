
import json
import os
import numpy as np
from collections import defaultdict

def run_research_lab():
    report_path = 'reports/variance_analysis.json'
    if not os.path.exists(report_path):
        print("Error: analysis report not found. Run ./variance first.")
        return

    with open(report_path, 'r') as f:
        data = json.load(f)

    candidates = data.get('opportunities', {}).get('candidates', [])
    portfolio = data.get('portfolio_overview', []) + data.get('triage_actions', [])
    
    # --- 1. SECTOR ANALYSIS (Relative Value) ---
    sector_data = defaultdict(list)
    for c in candidates:
        if c['NVRP'] is not None:
            sector_data[c['Sector']].append(c['NVRP'])
    
    sector_stats = {}
    for sector, nvrps in sector_data.items():
        sector_stats[sector] = {
            'mean': np.mean(nvrps),
            'std': np.max([np.std(nvrps), 0.05]) # Floor at 5% to avoid div zero
        }

    # --- 2. THE QUANT DESK REPORT (Candidates) ---
    print("\n" + "="*95)
    print(" QUANT DESK: VOLATILITY DIVERGENCE & RELATIVE VALUE")
    print("="*95)
    print(f"{ 'Symbol':<8} | { 'Sector':<12} | { 'NVRP(T)':>8} | { 'Bias(S)':>8} | { 'Div':>8} | { 'Z-Score':>8} | {'Action'}")
    print("-" * 95)

        for c in candidates[:15]:

            sym = c['Symbol']

            sector = c['Sector'][:12]

            nvrp_t = c['NVRP']

            bias_s = c['VRP Structural']

            

            # Structural Markup (Normalized to 0.0 baseline like NVRP)

            markup_s = bias_s - 1.0

            

            # Divergence: How much "hotter" is the tactical move than the structural trend?

            div = nvrp_t - markup_s

            

            # Sector Z-Score: How abnormal is this symbol within its own sector?

            stats = sector_stats.get(c['Sector'], {'mean': 0, 'std': 1})

            z_score = (nvrp_t - stats['mean']) / stats['std']

    

            # Logic Tag

            if nvrp_t > 0.20 and markup_s > 0.15: tag = "CONVICTION SELL"

            elif nvrp_t < -0.10 and markup_s < 0.0: tag = "CONVICTION BUY"

            elif div > 0.40: tag = "MEAN REVERSION"

            elif div < -0.40: tag = "COILING"

            else: tag = "FAIR VALUE"

    

            print(f"{sym:<8} | {sector:<12} | {nvrp_t:>8.1%} | {bias_s:>8.2f} | {div:>+7.0%} | {z_score:>8.1f} | {tag}")

    

        # --- 3. PORTFOLIO EXPECTANCY (Adjusted Theta) ---

        print("\n" + "="*95)

        print(" PORTFOLIO EXPECTANCY: VRP-ADJUSTED THETA")

        print("="*95)

        print(f"{'Symbol':<8} | {'Strategy':<18} | {'Raw Theta':>10} | {'VRP(T)':>8} | {'Exp. Alpha':>12} | {'Quality'}")

        print("-" * 95)

    

        total_raw = 0

        total_alpha = 0

    

        for p in portfolio:

            sym = p['symbol']

            strat = p['strategy'][:18]

            # We need to find the theta from the analysis. Since analyze_portfolio aggregates it, 

            # we'll look for matching symbols in the spectrograph or use a mock if missing for this demo.

            # In a real run, we'd grab this from the cluster.

            

            # Fetching raw theta (mocking 
    0/day for demo if not found, usually provided in clusters)

            raw_theta = 10.0 # Placeholder

            nvrp = p.get('vrp_structural', 1.0) - 1.0 # Proxy from structural VRP if tactical not in triage report

            

            # Correcting VRP Tactical from candidate data if available

            for c in candidates:

                if c['Symbol'] == sym:

                    nvrp = c['NVRP']

                    break
        
        if nvrp is None: nvrp = 0.0
        
        # Adjusted Alpha: How much "value" are we capturing per dollar of decay?
        alpha = raw_theta * (1 + nvrp)
        
        quality = "High" if nvrp > 0.10 else "Low" if nvrp < -0.10 else "Fair"
        if p.get('is_hedge'): quality = "Hedge"

        print(f"{sym:<8} | {strat:<18} | {raw_theta:>10.2f} | {nvrp:>8.1%} | {alpha:>12.2f} | {quality}")
        
    print("-" * 95)
    print("Legend: Div = Tactical/Structural Gap | Z-Score = Distance from Sector Mean | Alpha = Value-Adjusted Theta")

if __name__ == "__main__":
    run_research_lab()
