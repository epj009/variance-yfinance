import argparse
import json
import sys
from typing import Dict, List, Any, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich import box
from rich.style import Style
from rich.theme import Theme

# Define professional theme
VARIANCE_THEME = Theme({
    "header": "bold blue",
    "profit": "bold green",
    "loss": "bold red",
    "warning": "bold yellow",
    "dim": "dim white",
    "neutral": "bold white",
    "sigma": "bold cyan",
    "delta": "bold magenta",
    "label": "dim cyan",
    "value": "bold white"
})

class TUIRenderer:
    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.console = Console(theme=VARIANCE_THEME)
        self.portfolio_summary = self.data.get('portfolio_summary', {})

    def render(self):
        """Orchestrates full TUI generation using Rich"""
        # 1. Header Panels
        self.render_header()

        # 2. Delta Spectrograph
        self.render_spectrograph()

        # 3. Portfolio Triage
        self.render_triage()

        # 4. Vol Screener Opportunities
        self.render_opportunities()

    def render_header(self):
        """Renders the dashboard header panels using Rich Panels and Layout Tables"""
        net_liq = self.portfolio_summary.get('net_liquidity', 0.0)
        total_net_pl = self.portfolio_summary.get('total_net_pl', 0.0)
        bp_usage_pct = self.portfolio_summary.get('bp_usage_pct', 0.0)

        # --- Panel 1: Capital Console (Grid Layout) ---
        cap_grid = Table.grid(padding=(0, 4))
        cap_grid.add_column()
        cap_grid.add_column()

        # Left Column: Liquidity
        bp_style = "profit" if bp_usage_pct < 0.50 else "warning" if bp_usage_pct <= 0.75 else "loss"
        bp_status = "Deploy" if bp_usage_pct < 0.50 else "Optimal" if bp_usage_pct <= 0.75 else "⚠️ High"
        
        liq_text = Text()
        liq_text.append("• Net Liq:  ", style="label")
        liq_text.append(f"{fmt_currency(net_liq)}\n", style="value")
        liq_text.append("• BP Usage: ", style="label")
        liq_text.append(f"{fmt_percent(bp_usage_pct)} ", style=bp_style)
        liq_text.append(f"({bp_status})", style="dim")

        # Right Column: P/L
        pl_style = "profit" if total_net_pl >= 0 else "loss"
        pl_status = "Harvesting" if total_net_pl >= 0 else "Dragging"
        
        pl_text = Text()
        pl_text.append("• Open P/L: ", style="label")
        pl_text.append(f"{fmt_currency(total_net_pl)}\n", style=pl_style)
        pl_text.append("• Status:   ", style="label")
        pl_text.append(f"{pl_status}", style="dim")

        cap_grid.add_row(liq_text, pl_text)

        cap_panel = Panel(
            cap_grid,
            title="[header]THE CAPITAL CONSOLE[/header]",
            border_style="blue",
            box=box.ROUNDED,
            expand=False
        )

        # --- Panel 2: Gyroscope & Engine (Grid Layout) ---
        beta_delta = self.portfolio_summary.get('total_beta_delta', 0.0)
        theta_raw = self.portfolio_summary.get('total_portfolio_theta', 0.0)
        theta_vrp = self.portfolio_summary.get('total_portfolio_theta_vrp_adj', theta_raw)
        stability = self.portfolio_summary.get('delta_theta_ratio', 0.0)
        markup = self.portfolio_summary.get('portfolio_vrp_markup', 0.0)

        tilt_style = "loss" if abs(beta_delta) > 100 else "neutral"
        tilt_name = "Bearish" if beta_delta < -50 else "Bullish" if beta_delta > 50 else "Neutral"
        stab_style = "profit" if -0.5 <= stability <= 0.5 else "warning"
        stab_status = "Stable" if -0.5 <= stability <= 0.5 else "Unstable"

        # Gyro (Left)
        gyro_grid = Table.grid(padding=(0, 4))
        gyro_grid.add_column()
        gyro_grid.add_column()

        gyro_left = Text()
        gyro_left.append("THE GYROSCOPE (Risk)\n", style="header")
        gyro_left.append("• Tilt:      ", style="label")
        gyro_left.append(f"{tilt_name} ({beta_delta:.0f} Δ)\n", style=tilt_style)
        gyro_left.append("• Theta:     ", style="label")
        gyro_left.append(f"{fmt_currency(theta_raw)} → {fmt_currency(theta_vrp)} ", style="profit")
        gyro_left.append(f"({markup:+.0%} VRP)\n", style="dim")
        gyro_left.append("• Stability: ", style="label")
        gyro_left.append(f"{stability:.2f} ", style=stab_style)
        gyro_left.append(f"({stab_status})", style="dim")

        # Engine (Right)
        stress_scenarios = self.data.get('stress_box', {}).get('scenarios', [])
        downside_pl = 0.0
        downside_label = "None"
        worst_case = min(stress_scenarios, key=lambda x: x.get('est_pl', 0.0)) if stress_scenarios else None
        if worst_case and worst_case.get('est_pl', 0) < 0:
            downside_pl = worst_case['est_pl']
            downside_label = worst_case.get('label', 'Tail')

        upside_pl = 0.0
        upside_label = "None"
        best_case = max(stress_scenarios, key=lambda x: x.get('est_pl', 0.0)) if stress_scenarios else None
        if best_case and best_case.get('est_pl', 0) > 0:
            upside_pl = best_case['est_pl']
            upside_label = best_case.get('label', 'Rally')

        tail_risk_pct = self.portfolio_summary.get('tail_risk_pct', 0.0)
        risk_style = "profit" if tail_risk_pct < 0.05 else "warning" if tail_risk_pct < 0.15 else "loss"
        risk_status = "Safe" if tail_risk_pct < 0.05 else "Loaded" if tail_risk_pct < 0.15 else "Extreme"
        theta_nl_pct = self.portfolio_summary.get('theta_net_liquidity_pct', 0.0)
        mix_warning = self.data.get('asset_mix_warning', {}).get('risk', False)

        gyro_right = Text()
        gyro_right.append("THE ENGINE (Exposure)\n", style="header")
        gyro_right.append("• Downside:  ", style="label")
        gyro_right.append(f"{fmt_currency(downside_pl)} ", style=risk_style)
        gyro_right.append(f"({downside_label})\n", style="dim")
        gyro_right.append("• Upside:    ", style="label")
        gyro_right.append(f"{fmt_currency(upside_pl)} ", style="profit")
        gyro_right.append(f"({upside_label})\n", style="dim")
        gyro_right.append("• Mix:       ", style="label")
        gyro_right.append("⚠️ Equity Heavy" if mix_warning else "🌍 Diversified", style="warning" if mix_warning else "profit")

        gyro_grid.add_row(gyro_left, gyro_right)

        gyro_panel = Panel(
            gyro_grid,
            border_style="dim",
            box=box.ROUNDED,
            expand=False
        )

        self.console.print(cap_panel)
        self.console.print(gyro_panel)

    def render_triage(self):
        triage_actions = self.data.get('triage_actions', [])
        portfolio_overview = self.data.get('portfolio_overview', [])

        self.console.print("\n[header]📊 PORTFOLIO TRIAGE[/header]")

        action_icons = {
            "HARVEST": "💰",
            "DEFENSE": "🛡️",
            "GAMMA": "☢️",
            "TOXIC": "💀",
            "SIZE_THREAT": "🐳",
            "HEDGE_CHECK": "🌳",
            "SCALABLE": "➕",
            "EARNINGS_WARNING": "📅",
            None: "⏳"
        }

        if triage_actions:
            for action in triage_actions:
                code = action.get('action_code')
                icon = action_icons.get(code, "❓")
                badge_style = "profit" if code == "HARVEST" else "loss" if code in ["DEFENSE", "GAMMA", "SIZE_THREAT", "TOXIC"] else "warning"
                
                # Header Line: Natural flow, no vertical alignment
                row = Text()
                row.append(f"{icon} ", style="neutral")
                row.append(f"{action.get('symbol', '???')} ", style="neutral")
                row.append(f"({action.get('strategy', 'Unknown')}) ", style="dim")
                row.append(f"[{code}]", style=badge_style)
                row.append("    ") # Fixed 4-space gap before P/L
                
                net_pl = action.get('net_pl', 0.0)
                row.append(f"{fmt_currency(net_pl)}", style="profit" if net_pl >= 0 else "loss")
                
                if action.get('data_quality_warning'):
                    row.append(" ⚠️", style="warning")
                
                self.console.print(row)
                
                # Detail Line: Indented Logic
                self.console.print(f"   [dim]└── {action.get('dte', 0)} DTE: {action.get('logic', '')}[/dim]")
        else:
            self.console.print("   [dim](No priority actions detected)[/dim]")

        # --- Section 2: Positions on Hold ---
        if portfolio_overview:
            self.console.print("\n[dim]⌛ POSITIONS ON HOLD[/dim]")
            for pos in portfolio_overview:
                row = Text()
                row.append(f"   {pos.get('symbol', '???')} ", style="dim")
                row.append(f"({pos.get('strategy', 'Unknown')})", style="dim")
                row.append("    ")
                
                net_pl = pos.get('net_pl', 0.0)
                row.append(f"{fmt_currency(net_pl)}", style="profit" if net_pl >= 0 else "loss")
                
                if pos.get('data_quality_warning'):
                    row.append(" ⚠️", style="warning")
                
                row.append(f" ({pos.get('dte', 0)} DTE)", style="dim")
                
                self.console.print(row)

        hold_count = len(portfolio_overview)
        self.console.print(f"\n[dim]TOTAL: {len(triage_actions)} actions | {hold_count} positions on hold[/dim]")

    def render_spectrograph(self):
        deltas = self.data.get('delta_spectrograph', [])
        if not deltas:
            return

        table = Table(
            title="\n[header]📊 DELTA SPECTROGRAPH (Portfolio Drag)[/header]\n[dim]Visualizing position contribution to Beta-Weighted Delta[/dim]",
            box=box.SIMPLE,
            title_justify="left",
            show_header=False
        )
        table.add_column("Rank", width=4, justify="right")
        table.add_column("Symbol", width=10, style="neutral")
        table.add_column("Bar", width=35)
        table.add_column("Delta", width=12, justify="right")

        max_val = max([abs(d.get('delta', 0.0)) for d in deltas]) if deltas else 1.0
        
        for rank, item in enumerate(deltas[:10], start=1):
            delta = item.get('delta', 0.0)
            # Use fixed max bar length for tightness
            bar_len = int((abs(delta) / max_val) * 30)
            bar_style = "profit" if delta >= 0 else "loss"
            bar = Text("┃" * bar_len, style=bar_style)
            
            table.add_row(
                str(rank),
                item.get('symbol', ''),
                bar,
                f"{delta:+.2f} Δ"
            )
        self.console.print(table)

    def render_opportunities(self):
        """Renders top vol screener opportunities using Rich Table"""
        opportunities = self.data.get('opportunities', {})
        candidates = opportunities.get('candidates', [])
        meta = opportunities.get('meta', {})

        if not candidates:
            return

        self.console.print("\n[header]🔍 VOL SCREENER OPPORTUNITIES[/header]")
        
        # Grid for Subheader
        sub_grid = Table.grid(padding=(0, 2))
        sub_grid.add_column()
        sub_grid.add_column()
        
        excluded_count = meta.get('excluded_count', 0)
        warning_text = ""
        if excluded_count > 0:
            excluded = meta.get('excluded_symbols', [])
            warning_text = f"[warning]⚠️ {excluded_count} concentrated symbols excluded: {', '.join(excluded[:2])}[/warning]"
        
        sub_grid.add_row(
            "   [dim]High Vol Bias candidates for portfolio diversification[/dim]",
            warning_text
        )
        self.console.print(sub_grid)

        table = Table(
            box=box.ROUNDED,
            header_style="bold cyan",
            border_style="dim"
        )
        table.add_column("Symbol", style="neutral", width=10)
        table.add_column("Price", justify="right", width=12)
        table.add_column("VRP (S)", justify="right", style="sigma", width=10)
        table.add_column("VRP (T)", justify="right", style="profit", width=10)
        table.add_column("Signal", justify="center", width=15)
        table.add_column("Asset Class", style="dim", justify="right", width=15)

        for opp in candidates:
            vrp_t = opp.get('NVRP', 0.0)
            signal = opp.get('Signal', 'FAIR')
            if opp.get('is_bats_efficient'):
                signal = f"{signal} 🦇"

            table.add_row(
                opp.get('Symbol', ''),
                fmt_currency(opp.get('Price', 0.0)),
                f"{opp.get('VRP Structural', 0.0):.2f}",
                f"{vrp_t:+.0%}",
                signal,
                opp.get('Asset Class', 'Equity')
            )

        self.console.print(table)
        self.console.print("   [dim]Legend: 💸 Rich | ↔️ Bound | ❄️ Cheap | 📅 Event | 🤝 Fair[/dim]")

    def render_spectrograph(self):
        deltas = self.data.get('delta_spectrograph', [])
        if not deltas:
            return

        table = Table(
            title="\n[header]📊 DELTA SPECTROGRAPH (Portfolio Drag)[/header]\n[dim]Visualizing position contribution to Beta-Weighted Delta[/dim]",
            box=box.SIMPLE,
            title_justify="left",
            show_header=False,
            expand=False,
            padding=(0, 2)
        )
        table.add_column("Rank", width=4, justify="right")
        table.add_column("Symbol", width=10, style="neutral")
        table.add_column("Bar", width=35)
        table.add_column("Delta", width=14, justify="right")

        max_val = max([abs(d.get('delta', 0.0)) for d in deltas]) if deltas else 1.0
        
        for rank, item in enumerate(deltas[:10], start=1):
            delta = item.get('delta', 0.0)
            # Use fixed max bar length for functional visualization
            bar_len = int((abs(delta) / max_val) * 30)
            bar_style = "profit" if delta >= 0 else "loss"
            bar = Text("┃" * bar_len, style=bar_style)
            
            table.add_row(
                str(rank),
                item.get('symbol', ''),
                bar,
                f"{delta:+.2f} Δ"
            )
        
        self.console.print(table)

    def render_opportunities(self):
        """Renders top vol screener opportunities using Rich Table"""
        opportunities = self.data.get('opportunities', {})
        candidates = opportunities.get('candidates', [])
        meta = opportunities.get('meta', {})

        if not candidates:
            return

        self.console.print("\n[header]🔍 VOL SCREENER OPPORTUNITIES[/header]")
        self.console.print("   [dim]High Vol Bias candidates for portfolio diversification[/dim]")

        # Show exclusion info
        excluded_count = meta.get('excluded_count', 0)
        if excluded_count > 0:
            excluded = meta.get('excluded_symbols', [])
            self.console.print(f"   [warning]⚠️  {excluded_count} concentrated position(s) excluded: {', '.join(excluded[:3])}[/warning]")

        table = Table(
            box=box.ROUNDED,
            header_style="bold cyan",
            border_style="dim",
            expand=False,
            padding=(0, 1)
        )
        table.add_column("Symbol", style="neutral")
        table.add_column("Price")
        table.add_column("VRP (S)", style="sigma")
        table.add_column("VRP (T)", style="profit")
        table.add_column("Signal")
        table.add_column("Asset Class", style="dim")

        for opp in candidates:
            vrp_t = opp.get('NVRP', 0.0)
            signal = opp.get('Signal', 'FAIR')
            if opp.get('is_bats_efficient'):
                signal = f"{signal} 🦇"

            table.add_row(
                opp.get('Symbol', ''),
                fmt_currency(opp.get('Price', 0.0)),
                f"{opp.get('VRP Structural', 0.0):.2f}",
                f"{vrp_t:+.0%}",
                signal,
                opp.get('Asset Class', 'Equity')
            )

        self.console.print(table)
        self.console.print("   [dim]Legend: 💸 Rich | ↔️ Bound | ❄️ Cheap | 📅 Event | 🤝 Fair[/dim]")

# --- Formatting Helpers ---

def fmt_currency(val: Optional[float]) -> str:
    if val is None: return "$0.00"
    return f"${val:,.2f}"

def fmt_percent(val: Optional[float]) -> str:
    if val is None: return "0.0%"
    return f"{val:.1%}"

def main():
    parser = argparse.ArgumentParser(description="Variance Rich TUI Renderer")
    parser.add_argument("input_file", nargs="?", help="Input JSON file path")
    args = parser.parse_args()

    data = {}
    if args.input_file:
        with open(args.input_file, 'r') as f:
            data = json.load(f)
    elif not sys.stdin.isatty():
        data = json.load(sys.stdin)

    if not data:
        return

    renderer = TUIRenderer(data)
    renderer.render()

if __name__ == "__main__":
    main()