#!/usr/bin/env python3
"""Format vol_screener JSON output for human-readable terminal display."""

import argparse
import csv
import json
import sys
from datetime import datetime
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

from variance.market_data.clock import is_market_open

# Color theme matching variance TUI
VARIANCE_THEME = Theme(
    {
        "profit": "bold green",
        "loss": "bold red",
        "warning": "yellow",
        "info": "cyan",
        "dim": "dim white",
    }
)

# Initialize console
console = Console(theme=VARIANCE_THEME)


def get_vtr_style(vtr: float) -> str:
    """Return rich style string for VTR value."""
    if vtr < 0.60:
        return "loss"  # Severe compression - AVOID
    elif vtr < 0.75:
        return "warning"  # Mild compression
    elif vtr < 0.85:
        return "dim"  # Contracting
    elif vtr < 1.15:
        return "profit"  # Normal - good for short vol
    elif vtr < 1.30:
        return "warning"  # Expanding mildly
    else:
        return "bold green"  # Severe expansion - STRONG BUY


def get_vote_style(vote: str) -> str:
    """Return rich style string for Vote."""
    vote_upper = vote.upper()
    if "BUY" in vote_upper and "STRONG" not in vote_upper:
        return "profit"
    elif "STRONG BUY" in vote_upper or vote_upper == "SCALE":
        return "bold green"
    elif "LEAN" in vote_upper:
        return "profit"
    elif "WATCH" in vote_upper or "HOLD" in vote_upper:
        return "dim"
    elif "AVOID" in vote_upper or "PASS" in vote_upper:
        return "loss"
    else:
        return "dim"


def get_signal_style(signal: str) -> str:
    """Return rich style string for Signal."""
    signal_upper = signal.upper()
    if "RICH" in signal_upper or "EXPANDING-SEVERE" in signal_upper:
        return "profit"
    elif "EXPANDING" in signal_upper:
        return "warning"
    elif "COILED-SEVERE" in signal_upper or "DISCOUNT" in signal_upper:
        return "loss"
    elif "COILED" in signal_upper or "EVENT" in signal_upper:
        return "warning"
    else:
        return "dim"


# Signal icons mapping
SIGNAL_ICONS = {
    "RICH": "$",
    "EXPANDING-SEVERE": "^^",
    "EXPANDING-MILD": "^",
    "COILED-SEVERE": "!!",
    "COILED-MILD": "!",
    "DISCOUNT": "-",
    "EVENT": "E",
    "FAIR": "·",
    "NORMAL": "·",
}


def format_screener_output(data: dict[str, Any]) -> None:
    """Pretty-print screener results to terminal."""

    summary = data.get("summary", {})
    candidates = data.get("candidates", [])
    meta = data.get("meta", {})

    # Header with rich panel
    profile = meta.get("profile", "unknown")
    scan_time = meta.get("scan_timestamp", "N/A")
    scanned = summary.get("scanned_symbols_count", 0)
    found = summary.get("candidates_count", 0)
    pass_pct = (found / scanned * 100) if scanned > 0 else 0

    header_text = f"Profile: [cyan]{profile.upper()}[/]  |  Scanned: {scanned}  |  Passed: {found} ({pass_pct:.1f}%)  |  {scan_time}"
    console.print()
    console.print(
        Panel(
            "[bold]VARIANCE VOLATILITY SCREENER[/]",
            subtitle=header_text,
            box=box.DOUBLE,
            style="bold cyan",
        )
    )
    console.print()

    # Active constraints
    constraints = summary.get("active_constraints", {})
    if constraints:
        vrp = constraints.get("min_vrp", 0.0)
        ivp = constraints.get("min_ivp", 0.0)
        yld = constraints.get("min_yield", 0.0)
        prc = constraints.get("min_price", 0.0)
        console.print(
            f"Active:  VRP > {vrp:.1f} | IVP > {ivp:.0f}% | Yield > {yld:.1f}% | Price > ${prc:.0f}"
        )
        console.print()

    # Summary stats
    console.print("─" * 80)
    console.print("SUMMARY")
    console.print("─" * 80)
    console.print(f"  Symbols Scanned:  {scanned}")
    console.print(f"  Candidates Found: {found}")

    if found > 0:
        pct = (found / scanned * 100) if scanned > 0 else 0
        console.print(f"  Pass Rate:        {pct:.1f}%")
    console.print()

    # Filter diagnostics
    console.print("─" * 80)
    console.print("FILTER DIAGNOSTICS (symbols can fail multiple filters)")
    console.print("─" * 80)
    filters = [
        ("Low VRP Structural", summary.get("low_vrp_structural_count", 0)),
        ("Low VRP Tactical", summary.get("tactical_skipped_count", 0)),
        ("Low IV Percentile", summary.get("low_iv_percentile_skipped_count", 0)),
        ("Low Vol Momentum", summary.get("vol_momentum_skipped_count", 0)),
        ("Illiquid", summary.get("illiquid_skipped_count", 0)),
        ("Retail Inefficient", summary.get("retail_inefficient_skipped_count", 0)),
        ("High Slippage", summary.get("slippage_skipped_count", 0)),
        ("Low Yield", summary.get("low_yield_skipped_count", 0)),
        ("Correlation", summary.get("correlation_skipped_count", 0)),
        ("Sector Excluded", summary.get("sector_skipped_count", 0)),
    ]

    # Show ALL filters with their counts
    for name, count in filters:
        console.print(f"  {name:<25} {count:>4} symbols")

    # Show unique rejection count
    total_rejections = scanned - found
    console.print(f"  {'─' * 35}")
    console.print(f"  {'Unique Rejections':<25} {total_rejections:>4} symbols")
    console.print(f"  {'Passed All Filters':<25} {found:>4} symbols")
    console.print()

    # Rejection details (debug mode)
    rejections = meta.get("filter_rejections", {})
    if rejections:
        console.print("─" * 80)
        console.print("REJECTION DETAILS")
        console.print("─" * 80)
        for symbol in sorted(rejections):
            console.print(f"  {symbol}: {rejections[symbol]}")
        console.print()

    # Candidates table
    if candidates:
        console.print("─" * 80)
        console.print("[bold]CANDIDATES[/]")
        console.print("─" * 80)
        console.print()

        # Create rich table
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold")

        # Add columns
        table.add_column("Symbol", style="cyan", width=8)
        table.add_column("Asset", width=10)
        table.add_column("Price", justify="right", width=9)
        table.add_column("VRP S", justify="right", width=7)
        table.add_column("VRP T", justify="right", width=7)
        table.add_column("VTR", justify="right", width=6)
        table.add_column("IV%", justify="right", width=5)
        table.add_column("Signal", width=16)
        table.add_column("Score", justify="right", width=6)
        table.add_column("Vote", width=12)

        # Sort by score descending
        sorted_candidates = sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)

        for c in sorted_candidates:
            sym = c.get("Symbol", "N/A")[:7]
            asset = c.get("Asset Class", "N/A")[:9]
            price = c.get("Price", 0)
            vrp_s = c.get("VRP Structural", 0)
            vrp_t = c.get("vrp_tactical", 0)
            vtr = c.get("VTR") or c.get("Volatility Trend Ratio", 1.0)
            iv_pct = c.get("IV Percentile")
            signal = c.get("Signal", "N/A")
            score = c.get("score", 0)
            vote = c.get("Vote", "N/A")

            # Format values
            price_str = (
                f"${price:.2f}" if price and price < 1000 else f"${price:.0f}" if price else "N/A"
            )
            vrp_s_str = f"{vrp_s:.2f}" if vrp_s else "N/A"
            vrp_t_str = f"{vrp_t:.2f}" if vrp_t else "N/A"
            vtr_str = f"{vtr:.2f}" if isinstance(vtr, (int, float)) else "N/A"
            iv_pct_str = f"{iv_pct:.0f}" if iv_pct is not None else "N/A"
            score_str = f"{score:.1f}" if score else "0.0"

            # Add icon to signal
            signal_short = signal[:12]  # Truncate for display
            icon = SIGNAL_ICONS.get(signal, "?")
            signal_display = f"{icon} {signal_short}"

            # Style values
            vtr_style = get_vtr_style(vtr if isinstance(vtr, (int, float)) else 1.0)
            vote_style = get_vote_style(vote)
            signal_style = get_signal_style(signal)

            # Add row with styling
            table.add_row(
                sym,
                asset,
                price_str,
                vrp_s_str,
                vrp_t_str,
                f"[{vtr_style}]{vtr_str}[/]",
                iv_pct_str,
                f"[{signal_style}]{signal_display}[/]",
                score_str,
                f"[{vote_style}]{vote}[/]",
            )

        console.print(table)
        console.print()

        console.print("─" * 80)
        console.print("[dim]Legend:[/]")
        console.print(
            "  [dim]VRP S = Structural (IV/HV90), VRP T = Tactical (IV/HV30), VTR = HV30/HV90[/]"
        )
        console.print(
            "  [dim]VTR:[/] [loss]<0.75 coiled[/] | [dim]0.75-0.85 contracting[/] | [profit]0.85-1.15 normal[/] | [warning]1.15-1.30 expanding[/] | [bold green]>1.30 strong[/]"
        )
        console.print(
            "  [dim]Vote:[/] [bold green]BUY[/] (score>70) | [profit]LEAN[/] (60-70) | [dim]WATCH[/] (50-60) | [loss]AVOID[/]"
        )
        console.print("  [dim]Icons:[/] $ = RICH, ^^ = EXPANDING-SEVERE, ! = COILED, E = EVENT")
        console.print("─" * 80)
    else:
        console.print("─" * 80)
        console.print("NO CANDIDATES FOUND")
        console.print("─" * 80)
        console.print()
        console.print("All symbols were filtered out. Consider:")
        console.print("  • Using --profile broad for lower thresholds")
        console.print("  • Running during market hours for more volatile opportunities")
        console.print("  • Reviewing filter diagnostics above to see what filtered symbols")
        console.print()

    # Market data quality warning
    md = meta.get("market_data_diagnostics", {})
    stale = md.get("stale_count", 0)
    total = md.get("symbols_total", 0)
    errors = md.get("symbols_with_errors", 0)

    # Check actual market hours at scan time
    scan_timestamp = meta.get("scan_timestamp", "")
    market_was_open = True  # Default assumption
    if scan_timestamp:
        try:
            scan_dt = datetime.fromisoformat(scan_timestamp)
            market_was_open = is_market_open(scan_dt)
        except (ValueError, AttributeError):
            pass  # Keep default

    # Check if candidates have rate limiting warnings
    rate_limited_count = 0
    if candidates:
        for c in candidates:
            warning_detail = c.get("warning_detail", {})
            if warning_detail.get("reason") == "price_unavailable" and warning_detail.get("cached"):
                rate_limited_count += 1

    # Display warnings based on ACTUAL conditions
    if rate_limited_count > 0 and market_was_open:
        console.print("\n⚠️  YAHOO FINANCE RATE LIMITING DETECTED")
        console.print("─" * 80)
        console.print(f"  {stale}/{total} symbols using cached price data")
        console.print("  legacy data source returned 429 (Too Many Requests)")
        console.print()
        console.print("  Impact:")
        console.print("    • Price data: cached (from previous fetch)")
        console.print("    • Volatility metrics: FRESH from Tastytrade ✅")
        console.print("    • VRP calculations: accurate (use fresh IV/HV)")
        console.print()
        console.print("  Solutions:")
        console.print("    • Wait 5-10 minutes before running again")
        console.print("    • Use smaller watchlists (<100 symbols)")
        console.print("    • Results are still valid (VRP metrics are fresh)")
        console.print("─" * 80)
    elif not market_was_open:
        console.print("\nℹ️  MARKET STATUS")
        console.print("─" * 80)
        console.print("  Market was closed at scan time")
        console.print("  Using end-of-day data from last market close")
        console.print("─" * 80)
    elif errors > 5:
        console.print("\n⚠️  DATA QUALITY WARNING")
        console.print("─" * 80)
        console.print(f"  {errors} symbols had data fetch errors")
        console.print("  This may indicate API connectivity issues")
        console.print("─" * 80)

    console.print()


def render_detail_view(symbol: str, data: dict[str, Any]) -> None:
    """Show detailed deep dive for a specific symbol."""
    # First, try to find in scanned_symbols (includes ALL symbols, both candidates and rejected)
    scanned_symbols = data.get("scanned_symbols", [])
    candidates = data.get("candidates", [])

    symbol_data = None

    # Search scanned_symbols first (preferred - has filter_results)
    for s in scanned_symbols:
        if s.get("symbol", "").upper() == symbol.upper():
            symbol_data = s
            break

    # Fallback to candidates if not found in scanned_symbols
    if symbol_data is None:
        for c in candidates:
            if c.get("Symbol", "").upper() == symbol.upper():
                # Convert candidate format to scanned_symbols format
                symbol_data = {
                    "symbol": c.get("Symbol"),
                    "price": c.get("Price"),
                    "vrp_structural": c.get("VRP Structural"),
                    "vrp_tactical": c.get("vrp_tactical"),
                    "vtr": c.get("VTR") or c.get("Volatility Trend Ratio"),
                    "iv_percentile": c.get("IV Percentile"),
                    "score": c.get("score"),
                    "signal": c.get("Signal"),
                    "vote": c.get("Vote"),
                    "asset_class": c.get("Asset Class"),
                    "filter_results": {
                        "passed": True,
                        "filters_passed": ["all"],
                        "filters_failed": [],
                    },
                }
                break

    # If still not found, show error
    if symbol_data is None:
        console.print()
        console.print(
            Panel(
                f"[bold red]Symbol '{symbol}' was not in the scan[/]\n\n"
                f"Run [cyan]./screen[/] without --detail to see what symbols were scanned.",
                title="Detail View Error",
                box=box.DOUBLE,
                style="red",
            )
        )
        console.print()
        return

    # Extract fields (scanned_symbols format uses lowercase keys)
    sym = symbol_data.get("symbol", "N/A")
    asset_class = symbol_data.get("asset_class", "N/A")
    price = symbol_data.get("price", 0)
    vrp_s = symbol_data.get("vrp_structural", 0)
    vrp_t = symbol_data.get("vrp_tactical", 0)
    vtr = symbol_data.get("vtr", 1.0)
    iv_pct = symbol_data.get("iv_percentile")
    score = symbol_data.get("score", 0)
    sector = symbol_data.get("sector", "N/A")

    # Get legacy fields from candidates if available (signal, vote)
    signal = symbol_data.get("signal", "N/A")
    vote = symbol_data.get("vote", "N/A")

    # If signal/vote not in scanned_symbols, try to find in candidates
    if signal == "N/A" or vote == "N/A":
        for c in candidates:
            if c.get("Symbol", "").upper() == symbol.upper():
                signal = c.get("Signal", signal)
                vote = c.get("Vote", vote)
                break

    # Get filter results
    filter_results = symbol_data.get("filter_results", {})
    passed = filter_results.get("passed", False)
    rejection_reason = filter_results.get("rejection_reason")
    filters_passed = filter_results.get("filters_passed", [])
    filters_failed = filter_results.get("filters_failed", [])

    # Build detailed panel content
    details = []
    details.append(f"[bold cyan]Symbol:[/] {sym}")
    details.append(f"[bold cyan]Asset Class:[/] {asset_class}")
    details.append(f"[bold cyan]Sector:[/] {sector}")
    details.append(f"[bold cyan]Price:[/] ${price:.2f}" if price else "[bold cyan]Price:[/] N/A")
    details.append("")

    # Filter Status Section
    details.append("[bold]Filter Status[/]")
    if passed:
        details.append("  Status:           [bold green]CANDIDATE - All filters passed[/]")
    else:
        details.append("  Status:           [bold red]REJECTED[/]")
        if rejection_reason:
            details.append(f"  Reason:           [red]{rejection_reason}[/]")

    # Show which filters passed/failed
    if filters_passed:
        details.append(f"  Passed Filters:   [green]{', '.join(filters_passed)}[/]")
    if filters_failed:
        details.append(f"  Failed Filters:   [red]{', '.join(filters_failed)}[/]")
    details.append("")

    # Volatility metrics
    details.append("[bold]Volatility Metrics[/]")
    details.append(f"  VRP Structural:   {vrp_s:.2f}" if vrp_s else "  VRP Structural:   N/A")
    details.append(f"  VRP Tactical:     {vrp_t:.2f}" if vrp_t else "  VRP Tactical:     N/A")

    # VTR with interpretation
    if isinstance(vtr, (int, float)):
        vtr_style = get_vtr_style(vtr)
        vtr_interpretation = ""
        if vtr < 0.60:
            vtr_interpretation = "severe compression, volatility has collapsed"
        elif vtr < 0.75:
            vtr_interpretation = "mild compression, volatility coiling"
        elif vtr < 0.85:
            vtr_interpretation = "contracting, volatility declining"
        elif vtr < 1.15:
            vtr_interpretation = "normal range, stable volatility"
        elif vtr < 1.30:
            vtr_interpretation = "expanding mildly, volatility rising"
        else:
            vtr_interpretation = "severe expansion, volatility spiking"

        details.append(f"  VTR:              [{vtr_style}]{vtr:.2f}[/] ({vtr_interpretation})")
    else:
        details.append("  VTR:              N/A")

    details.append(
        f"  IV Percentile:    {iv_pct:.0f}%" if iv_pct is not None else "  IV Percentile:    N/A"
    )
    details.append("")

    # Screening results (only show if it passed filters)
    if passed:
        details.append("[bold]Screening Results[/]")
        details.append(
            f"  Score:            {score:.1f}/100" if score else "  Score:            0.0/100"
        )

        if signal != "N/A":
            signal_style = get_signal_style(signal)
            details.append(f"  Signal:           [{signal_style}]{signal}[/]")

        if vote != "N/A":
            vote_style = get_vote_style(vote)
            details.append(f"  Vote:             [{vote_style}]{vote}[/]")

    # Determine panel style based on status
    panel_style = "green" if passed else "red"
    title_status = "CANDIDATE" if passed else "REJECTED"

    # Create panel
    console.print()
    console.print(
        Panel(
            "\n".join(details),
            title=f"[bold]DETAIL VIEW: {sym} ({title_status})[/]",
            box=box.DOUBLE,
            style=panel_style,
        )
    )
    console.print()


def export_csv(candidates: list[dict[str, Any]]) -> None:
    """Export candidates to CSV format on stdout."""
    if not candidates:
        print("Symbol,Asset Class,Price,VRP_S,VRP_T,VTR,IV_Pct,Score,Signal,Vote")
        return

    # Define CSV columns
    fieldnames = [
        "Symbol",
        "Asset Class",
        "Price",
        "VRP_S",
        "VRP_T",
        "VTR",
        "IV_Pct",
        "Score",
        "Signal",
        "Vote",
    ]

    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
    writer.writeheader()

    # Sort by score descending
    sorted_candidates = sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)

    for c in sorted_candidates:
        row = {
            "Symbol": c.get("Symbol", "N/A"),
            "Asset Class": c.get("Asset Class", "N/A"),
            "Price": f"{c.get('Price', 0):.2f}" if c.get("Price") else "N/A",
            "VRP_S": f"{c.get('VRP Structural', 0):.2f}" if c.get("VRP Structural") else "N/A",
            "VRP_T": f"{c.get('vrp_tactical', 0):.2f}" if c.get("vrp_tactical") else "N/A",
            "VTR": f"{c.get('VTR', c.get('Volatility Trend Ratio', 1.0)):.2f}"
            if c.get("VTR") or c.get("Volatility Trend Ratio")
            else "N/A",
            "IV_Pct": f"{c.get('IV Percentile'):.0f}"
            if c.get("IV Percentile") is not None
            else "N/A",
            "Score": f"{c.get('score', 0):.1f}" if c.get("score") is not None else "0.0",
            "Signal": c.get("Signal", "N/A"),
            "Vote": c.get("Vote", "N/A"),
        }
        writer.writerow(row)


def main() -> None:
    """Read JSON from stdin and format for terminal."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Format vol_screener JSON output for human-readable terminal display"
    )
    parser.add_argument(
        "--detail", type=str, metavar="SYMBOL", help="Show detailed view for a specific symbol"
    )
    parser.add_argument(
        "--export",
        type=str,
        metavar="FORMAT",
        choices=["csv"],
        help="Export results in specified format (csv)",
    )

    args = parser.parse_args()

    try:
        data = json.load(sys.stdin)
        candidates = data.get("candidates", [])

        # Route to appropriate handler
        if args.detail:
            render_detail_view(args.detail, data)
        elif args.export:
            if args.export == "csv":
                export_csv(candidates)
        else:
            format_screener_output(data)

    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input - {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
