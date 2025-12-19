
import json
import os

def compare_nvrp():
    report_path = 'reports/variance_analysis.json'
    if not os.path.exists(report_path):
        print("Error: analysis report not found.")
        return

    with open(report_path, 'r') as f:
        data = json.load(f)

    candidates = data.get('opportunities', {}).get('candidates', [])
    
    print(f"{'Symbol':<8} | {'IV30':<6} | {'HV20':<6} | {'HV252':<6} | {'VRP (Tact)':<10} | {'VRP (Str)':<10} | {'Delta'}")
    print("-" * 80)

    for c in candidates[:15]:
        sym = c['Symbol']
        iv = c['IV30']
        hv20 = c['HV20']
        hv252 = c['HV252']
        
        # Calculations
        nvrp_20 = (iv - hv20) / hv20 if hv20 > 0 else 0
        vrp_s = c.get('VRP Structural', 0)
        nvrp_252 = vrp_s - 1.0
        diff = nvrp_252 - nvrp_20

        print(f"{sym:<8} | {iv:>6.1f} | {hv20:>6.1f} | {hv252:>6.1f} | {nvrp_20:>10.1%} | {nvrp_252:>10.1%} | {diff:>+6.1%}")

if __name__ == "__main__":
    compare_nvrp()
