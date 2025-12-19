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
    "delta": "bold magenta"
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

        # 3. Stress Box
        self.render_stress_box()

        # 4. Portfolio Triage
        self.render_triage()

        # 5. Vol Screener Opportunities
        self.render_opportunities()

    def render_header(self):
        """Renders the dashboard header panels using Rich Panels and Columns"""
        net_liq = self.portfolio_summary.get('net_liquidity', 0.0)
        total_net_pl = self.portfolio_summary.get('total_net_pl', 0.0)
        bp_usage_pct = self.portfolio_summary.get('bp_usage_pct', 0.0)

        # --- Panel 1: Capital Console ---
        pl_style = "profit" if total_net_pl >= 0 else "loss"
        pl_status = "(🟢 Harvesting)" if total_net_pl >= 0 else "(🔴 Dragging)"
        
        bp_style = "profit" if bp_usage_pct < 0.50 else "warning" if bp_usage_pct <= 0.75 else "loss"
        bp_status = "(Low - Deploy)" if bp_usage_pct < 0.50 else "(Optimal)" if bp_usage_pct <= 0.75 else "(⚠️ High)"

        cap_text = Text()
        cap_text.append(f"• Net Liq:   ", style="dim")
        cap_text.append(f"{fmt_currency(net_liq)}\n", style="neutral")
        cap_text.append(f"• BP Usage:  ", style="dim")
        cap_text.append(f"{fmt_percent(bp_usage_pct)} ", style=bp_style)
        cap_text.append(f"{bp_status}", style="dim")

        pl_text = Text()
        pl_text.append(f"\nOpen P/L: ", style="dim")
        pl_text.append(f"{fmt_currency(total_net_pl)} ", style=pl_style)
        pl_text.append(f"{pl_status}", style="dim")

        cap_panel = Panel(
            Columns([cap_text, pl_text], expand=True),
            title="[header]THE CAPITAL CONSOLE[/header]",
            border_style="blue",
            box=box.ROUNDED
        )

        # --- Panel 2: Gyroscope & Engine (Split) ---
        beta_delta = self.portfolio_summary.get('total_beta_delta', 0.0)
        theta_raw = self.portfolio_summary.get('total_portfolio_theta', 0.0)
        theta_vrp = self.portfolio_summary.get('total_portfolio_theta_vrp_adj', theta_raw)
        stability = self.portfolio_summary.get('delta_theta_ratio', 0.0)
        markup = self.portfolio_summary.get('portfolio_vrp_markup', 0.0)
        
        portfolio_vega = self.data.get('stress_box', {}).get('total_portfolio_vega', 0.0)

        tilt_style = "loss" if abs(beta_delta) > 100 else "neutral"
        tilt_name = "Bearish" if beta_delta < -50 else "Bullish" if beta_delta > 50 else "Neutral"
        
        stab_style = "profit" if -0.5 <= stability <= 0.5 else "warning"
        stab_status = "(✅ Stable)" if -0.5 <= stability <= 0.5 else "(⚠️ Unstable)"

        gyro_text = Text()
        gyro_text.append("THE GYROSCOPE (Risk)\n", style="header")
        gyro_text.append(f"• Tilt:      {tilt_name} ", style="dim")
        gyro_text.append(f"({beta_delta:.0f} Δ)\n", style=tilt_style)
        gyro_text.append(f"• Theta:     ", style="dim")
        gyro_text.append(f"{fmt_currency(theta_raw)} → {fmt_currency(theta_vrp)} ", style="profit")
        gyro_text.append(f"({markup:+.0%} VRP)\n", style="dim")
        gyro_text.append(f"• Vega:      ", style="dim")
        gyro_text.append(f"{fmt_currency(portfolio_vega)}/pt\n", style="neutral")
        gyro_text.append(f"• Stability: ", style="dim")
        gyro_text.append(f"{stability:.2f} ", style=stab_style)
        gyro_text.append(stab_status, style="dim")

        # Engine (Right)
        tail_risk = self.portfolio_summary.get('total_tail_risk', 0.0)
        tail_risk_pct = self.portfolio_summary.get('tail_risk_pct', 0.0)
        theta_nl_pct = self.portfolio_summary.get('theta_net_liquidity_pct', 0.0)
        mix_warning = self.data.get('asset_mix_warning', {}).get('risk', False)

        risk_style = "profit" if tail_risk_pct < 0.05 else "warning" if tail_risk_pct < 0.15 else "loss"
        risk_status = "Safe" if tail_risk_pct < 0.05 else "Loaded" if tail_risk_pct < 0.15 else "Extreme"

        engine_text = Text()
        engine_text.append("THE ENGINE (Structure)\n", style="header")
        engine_text.append(f"• Tail Risk: ", style="dim")
        engine_text.append(f"{fmt_currency(tail_risk)} ", style=risk_style)
        engine_text.append(f"({risk_status})\n", style="dim")
        engine_text.append(f"• Usage:     ", style="dim")
        engine_text.append(f"{fmt_percent(theta_nl_pct)} ", style="neutral")
        engine_text.append("of Net Liq\n", style="dim")
        engine_text.append(f"• Mix:       ", style="dim")
        engine_text.append("⚠️ Equity Heavy" if mix_warning else "🌍 Diversified", style="warning" if mix_warning else "profit")

        gyro_panel = Panel(
            Columns([gyro_text, engine_text], expand=True),
            border_style="dim",
            box=box.HORIZONTALS
        )

        self.console.print(cap_panel)
        self.console.print(gyro_panel)

    def render_stress_box(self):
        stress_data = self.data.get('stress_box') or {}
        scenarios = stress_data.get('scenarios', [])
        if not scenarios:
            return

        beta_symbol = stress_data.get('beta_symbol', 'SPY')
        beta_price = stress_data.get('beta_price', 0.0)
        beta_iv = stress_data.get('beta_iv', 0.0)
        em_1sd = stress_data.get('em_1sd', 0.0)
        net_liq = self.portfolio_summary.get('net_liquidity', 1.0)

        # Check for crash warning
        for scen in scenarios:
            if scen.get('est_pl', 0) < (-0.10 * net_liq):
                self.console.print("\n[bold red]⚠️ WARNING: CRASH SCENARIO RISK - Portfolio may lose >10% in a tail event[/bold red]")
                break

        table = Table(
            title=f"\n[header]📊 PROBABILISTIC STRESS TEST (1-Day Horizon)[/header]\n[dim]Beta: {beta_symbol} @ {fmt_currency(beta_price)} | IV: {beta_iv:.1f}% | 1SD Expected Move: +/- {fmt_currency(em_1sd)}[/dim]",
            header_style="bold cyan",
            box=box.MINIMAL_DOUBLE_HEAD,
            expand=True,
            title_justify="left"
        )
        table.add_column("Confidence", style="neutral")
        table.add_column("Sigma", justify="right", style="sigma")
        table.add_column("Move pts", justify="right", style="dim")
        table.add_column("Est P/L", justify="right")
        table.add_column("Delta Drift", justify="right", style="delta")

        for scen in scenarios:
            pl = scen.get('est_pl', 0.0)
            pl_style = "profit" if pl > 0 else "loss" if pl < 0 else "neutral"
            
            table.add_row(
                scen.get('label', ''),
                f"{scen.get('sigma', 0.0):+.1f}σ",
                f"{scen.get('beta_move', 0.0):+.2f}",
                Text(fmt_currency(pl), style=pl_style),
                f"{scen.get('new_delta', 0.0):>+6.1f} Δ"
            )

        self.console.print(table)
        self.console.print("[dim]Note: P/L includes non-linear Gamma adjustment and IV expansion.[/dim]")

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

        if not triage_actions:
            self.console.print("   [dim](No priority actions detected)[/dim]")
        
        for action in triage_actions:
            code = action.get('action_code')
            icon = action_icons.get(code, "❓")
            
            # Action Row
            row = Text()
            row.append(f"{icon} ", style="neutral")
            row.append(f"{action.get('symbol', '???'):<6} ", style="neutral")
            row.append(f"({action.get('strategy', 'Unknown')}) ", style="dim")
            
            # Action Badge
            badge_style = "profit" if code == "HARVEST" else "loss" if code in ["DEFENSE", "GAMMA", "SIZE_THREAT", "TOXIC"] else "warning"
            row.append(f"[{code}] ", style=badge_style)
            
            # P/L
            net_pl = action.get('net_pl', 0.0)
            row.append(f"{fmt_currency(net_pl):>12} ", style="profit" if net_pl >= 0 else "loss")
            
            self.console.print(row)
            # Logic Line
            self.console.print(f"   [dim]└── {action.get('dte', 0)} DTE: {action.get('logic', '')}[/dim]")

        # Summary Footer
        hold_count = len([p for p in portfolio_overview if not p.get('action_code')])
        self.console.print(f"\n[dim]TOTAL: {len(triage_actions)} actions | {hold_count} positions on hold[/dim]")

    def render_spectrograph(self):
        deltas = self.data.get('delta_spectrograph', [])
        if not deltas:
            return

        table = Table(
            title="\n[header]📊 DELTA SPECTROGRAPH (Portfolio Drag)[/header]\n[dim]Visualizing position contribution to Beta-Weighted Delta[/dim]",
            box=box.SIMPLE,
            expand=True,
            title_justify="left",
            show_header=False
        )
        table.add_column("Rank", width=4, justify="right")
        table.add_column("Symbol", width=8, style="neutral")
        table.add_column("Bar", ratio=1)
        table.add_column("Delta", width=12, justify="right")

        max_val = max([abs(d.get('delta', 0.0)) for d in deltas]) if deltas else 1.0
        
        for rank, item in enumerate(deltas[:10], start=1):
            delta = item.get('delta', 0.0)
            bar_len = int((abs(delta) / max_val) * 30)
            
            bar_char = "█"
            bar_style = "profit" if delta >= 0 else "loss"
            bar = Text(bar_char * bar_len, style=bar_style)
            
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
            expand=True,
            header_style="bold cyan",
            border_style="dim"
        )
        table.add_column("Symbol", style="neutral")
        table.add_column("Price", justify="right")
        table.add_column("VRP (S)", justify="right", style="sigma")
        table.add_column("VRP (T)", justify="right", style="profit")
        table.add_column("Signal", style="warning")
        table.add_column("Asset Class", style="dim")

        for opp in candidates:
            vrp_t = opp.get('NVRP', 0.0)
            
            signal_display = opp.get('Signal', 'FAIR')
            if opp.get('is_bats_efficient'):
                signal_display = f"{signal_display} 🦇"

            table.add_row(
                opp.get('Symbol', ''),
                fmt_currency(opp.get('Price', 0.0)),
                f"{opp.get('VRP Structural', 0.0):.2f}",
                f"{vrp_t:+.0%}",
                signal_display,
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