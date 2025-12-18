import json
import sys

def main():
    try:
        with open('/tmp/full_vol_scan.json', 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading JSON: {e}")
        return

    candidates = data.get('candidates', [])
    
    print(f"## 🔍 Deep Dive Audit: {len(candidates)} Opportunities Identified")
    print("")
    print("| Rank | Symbol | Price | Bias | NVRP | Ratio | Signal | Environment | Score |")
    print("|---|---|---|---|---|---|---|---|---|")
    
    for i, c in enumerate(candidates, 1):
        sym = c.get('Symbol')
        price = c.get('Price')
        bias = c.get('Vol Bias')
        nvrp = c.get('NVRP')
        ratio = c.get('Compression Ratio') # HV20 / HV252
        score = c.get('Score')
        
        signal = c.get('Signal', 'N/A')
        environment = c.get('Environment', 'N/A')
        
        # Formatting
        p_str = f"${price:.2f}" if price else "-"
        b_str = f"{bias:.2f}" if bias else "-"
        
        n_str = "-"
        if nvrp is not None:
            n_str = f"{nvrp*100:+.0f}%"
            
        r_str = f"{ratio:.2f}" if ratio else "-"
        
        # Markdown Row
        print(f"| {i} | **{sym}** | {p_str} | **{b_str}** | **{n_str}** | {r_str} | {signal} | {environment} | {score} |")

if __name__ == "__main__":
    main()