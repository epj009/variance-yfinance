"""
Correlation Diagnostic Tool (RFC 013)

Provides clinical visibility into the portfolio correlation logic.
"""

import sys
import argparse
import numpy as np
from datetime import datetime
from rich.console import Console
from rich.table import Table

from variance.portfolio_parser import PortfolioParser, get_root_symbol
from variance.get_market_data import MarketDataFactory
from variance.models.correlation import CorrelationEngine
from variance.config_loader import load_config_bundle

def diagnose(portfolio_path: str, check_symbols: list[str]):
    console = Console()
    console.print(f"[bold cyan]🔬 Correlation Diagnostic - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold cyan]")

    # 1. Load Portfolio
    parser = PortfolioParser()
    positions = parser.parse(portfolio_path)
    # Aggressively extract clean roots
    roots = list(set(get_root_symbol(p.get("Symbol", "")) for p in positions if p.get("Symbol")))
    # Filter out empty or None
    roots = [r for r in roots if r]
    
    # 2. Fetch Data
    console.print(f"   Fetching historical returns for {len(roots)} portfolio roots...")
    provider = MarketDataFactory.get_provider()
    market_data = provider.get_market_data(roots + check_symbols)
    
    # 3. Build Portfolio Proxy
    portfolio_returns = []
    for root in roots:
        data = market_data.get(root, {})
        ret = data.get("returns")
        if ret:
            portfolio_returns.append(np.array(ret))
            console.print(f"   [dim]• Added {root} ({len(ret)} days of returns)[/dim]")
    
    if not portfolio_returns:
        console.print("[bold red]❌ ERROR: No return data found for portfolio positions. Verification failed.[/bold red]")
        return

    proxy = CorrelationEngine.get_portfolio_proxy_returns(portfolio_returns)
    console.print(f"   [bold green]✅ Synthetic Portfolio Proxy built ({len(proxy)} days aligned).[/bold green]")

    # 4. Check Candidates
    table = Table(title="Correlation Audit (Target: < 0.70)")
    table.add_column("Symbol", style="cyan")
    table.add_column("Correlation", justify="right")
    table.add_column("Status", justify="center")
    table.add_column("Decision", style="dim")

    for sym in check_symbols:
        data = market_data.get(sym, {})
        ret = data.get("returns")
        
        if not ret:
            table.add_row(sym, "N/A", "❓", "Insufficient Data")
            continue
            
        corr = CorrelationEngine.calculate_correlation(proxy, np.array(ret))
        
        status = "✅" if corr < 0.70 else "❌"
        color = "green" if corr < 0.70 else "red"
        decision = "PASS" if corr < 0.70 else "REJECT (Macro Trap)"
        
        table.add_row(
            sym, 
            f"[{color}]{corr:.3f}[/{color}]", 
            status, 
            decision
        )

    console.print(table)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Diagnose portfolio correlation risk.")
    parser.add_argument("portfolio", help="Path to portfolio CSV")
    parser.add_argument("--check", nargs="+", default=["SPY", "QQQ", "IWM", "GLD", "TLT", "/ES"], help="Symbols to test against portfolio")
    
    args = parser.parse_args()
    diagnose(args.portfolio, args.check)
