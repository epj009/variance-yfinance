import argparse
import json
import sys
from typing import Any, Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich.tree import Tree

# Define professional theme
VARIANCE_THEME = Theme(
    {
        "header": "bold blue",
        "profit": "bold green",
        "loss": "bold red",
        "warning": "bold yellow",
        "dim": "dim white",
        "neutral": "bold white",
        "sigma": "bold cyan",
        "delta": "bold magenta",
        "label": "dim cyan",
        "value": "bold white",
    }
)


class TUIRenderer:
    def __init__(self, data: dict[str, Any], *, show_diagnostics: bool = False):
        self.data = data
        self.console = Console(theme=VARIANCE_THEME)
        self.portfolio_summary = self.data.get("portfolio_summary", {})
        self.show_diagnostics = show_diagnostics

    def render(self) -> None:
        """Main entry point for TUI rendering."""
        self.render_integrity_banner()
        self.render_header()
        if self.show_diagnostics:
            self.render_diagnostics()
        self.render_triage()
        self.render_opportunities()

    def render_integrity_banner(self) -> None:
        """Renders a high-visibility warning if data is stale or after-hours."""
        from variance.get_market_data import is_market_open

        market_closed = not is_market_open()

        if not market_closed:
            return

        details = (
            "Quotes may be stale and options IV may be unavailable.\n"
            "For full coverage, run during market hours."
        )

        banner = Panel(
            Text(details, style="dim"),
            title="[bold yellow]⚠️  AFTER-HOURS MODE ⚠️[/bold yellow]",
            title_align="center",
            border_style="yellow",
            box=box.ROUNDED,
            expand=False,
        )
        self.console.print(banner)

    def render_header(self) -> None:
        """Renders the dashboard header panels using Rich Panels and Layout Tables"""
        net_liq = self.portfolio_summary.get("net_liquidity", 0.0)
        total_net_pl = self.portfolio_summary.get("total_net_pl", 0.0)
        bp_usage_pct = self.portfolio_summary.get("bp_usage_pct", 0.0)

        # --- Panel 1: Capital Console (Grid Layout) ---
        cap_grid = Table.grid(padding=(0, 4))
        cap_grid.add_column()
        cap_grid.add_column()

        # Left Column: Liquidity
        bp_style = (
            "profit" if bp_usage_pct < 0.50 else "warning" if bp_usage_pct <= 0.75 else "loss"
        )
        bp_status = (
            "Deploy" if bp_usage_pct < 0.50 else "Optimal" if bp_usage_pct <= 0.75 else "⚠️ High"
        )

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
            expand=False,
        )

        # --- Panel 2: Gyroscope & Engine (Grid Layout) ---
        beta_delta = self.portfolio_summary.get("total_beta_delta", 0.0)
        theta_raw = self.portfolio_summary.get("total_portfolio_theta", 0.0)
        theta_vrp = self.portfolio_summary.get("total_portfolio_theta_vrp_adj", theta_raw)
        stability = self.portfolio_summary.get("delta_theta_ratio", 0.0)
        markup = self.portfolio_summary.get("portfolio_vrp_markup", 0.0)

        tilt_style = "loss" if abs(beta_delta) > 100 else "neutral"
        tilt_name = "Bearish" if beta_delta < -50 else "Bullish" if beta_delta > 50 else "Neutral"

        # Stability Logic (Delta/Theta Ratio)
        # If Theta is negative, the portfolio is inherently unstable for a premium seller.
        if theta_vrp <= 0:
            stab_style = "loss"
            stab_status = "Unstable (Paying)"
        else:
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
        stress_scenarios = self.data.get("stress_box", {}).get("scenarios", [])

        # Directional Mapping:
        # Downside = Worst result of Bearish moves (beta_move < 0)
        # Upside   = Best result of Bullish moves (beta_move > 0)
        bearish_scenarios = [s for s in stress_scenarios if s.get("beta_move", 0) < 0]
        bullish_scenarios = [s for s in stress_scenarios if s.get("beta_move", 0) > 0]

        downside_pl = 0.0
        downside_label = "None"
        if bearish_scenarios:
            worst_bear = min(bearish_scenarios, key=lambda x: x.get("est_pl", 0.0))
            downside_pl = worst_bear.get("est_pl", 0.0)
            downside_label = worst_bear.get("label", "Bearish")

        upside_pl = 0.0
        upside_label = "None"
        if bullish_scenarios:
            best_bull = max(bullish_scenarios, key=lambda x: x.get("est_pl", 0.0))
            upside_pl = best_bull.get("est_pl", 0.0)
            upside_label = best_bull.get("label", "Bullish")

        # Style based on outcome: Red if losing, Green if making money
        downside_style = "loss" if downside_pl < 0 else "profit"
        upside_style = "profit" if upside_pl > 0 else "loss"

        # Mix Status based on correlation (RFC 020)
        avg_corr = self.portfolio_summary.get("avg_correlation", 0.0)
        corr_status = self.portfolio_summary.get("correlation_status", "DIVERSIFIED")

        mix_labels = {
            "DIVERSIFIED": "🌍 Diversified",
            "BOUND": "⚖️  Bound",
            "CONCENTRATED": "🪤  CONCENTRATED",
        }
        mix_styles = {
            "DIVERSIFIED": "profit",
            "BOUND": "warning",
            "CONCENTRATED": "loss bold",
        }

        gyro_right = Text()
        gyro_right.append("THE ENGINE (Exposure)\n", style="header")
        gyro_right.append("• Downside:  ", style="label")
        gyro_right.append(f"{fmt_currency(downside_pl)} ", style=downside_style)
        gyro_right.append(f"({downside_label})\n", style="dim")
        gyro_right.append("• Upside:    ", style="label")
        gyro_right.append(f"{fmt_currency(upside_pl)} ", style=upside_style)
        gyro_right.append(f"({upside_label})\n", style="dim")
        gyro_right.append("• Mix:       ", style="label")
        gyro_right.append(
            f"{mix_labels.get(corr_status)} ({avg_corr:.2f} ρ)\n",
            style=mix_styles.get(corr_status),
        )

        gyro_grid.add_row(gyro_left, gyro_right)

        gyro_panel = Panel(gyro_grid, border_style="dim", box=box.ROUNDED, expand=False)

        self.console.print(cap_panel)
        self.console.print(gyro_panel)

    def render_triage(self) -> None:
        triage_actions = self.data.get("triage_actions", [])
        portfolio_overview = self.data.get("portfolio_overview", [])

        self.console.print("\n")  # Spacer

        # Root Tree
        root = Tree("📂 [header]PORTFOLIO OVERVIEW[/header]", guide_style="dim")

        # Action Branch
        if triage_actions:
            action_branch = root.add(
                f"🚨 [bold red]ACTION REQUIRED ({len(triage_actions)})[/bold red]"
            )
            for action in triage_actions:
                self._add_position_node(action_branch, action, is_action=True)
        else:
            root.add("✅ [dim]No immediate actions required[/dim]")

        # Holding Branch
        if portfolio_overview:
            hold_branch = root.add(
                f"⏳ [bold white]HOLDING ({len(portfolio_overview)})[/bold white]"
            )
            for pos in portfolio_overview:
                self._add_position_node(hold_branch, pos, is_action=False)

        self.console.print(root)

    def _add_position_node(
        self, parent_branch: Tree, item: dict[str, Any], is_action: bool
    ) -> None:
        """Helper to format and add a position node to the tree."""
        sym = item.get("symbol", "???")
        strat = item.get("strategy", "Unknown")
        net_pl = item.get("net_pl", 0.0)
        dte = item.get("dte", 0)
        logic = item.get("logic", "")
        tags = item.get("tags", [])

        # Format Node Text
        text = Text()
        text.append(f"{sym} ", style="bold white")
        text.append(f"({strat}) ", style="dim")

        # P/L
        pl_style = "profit" if net_pl >= 0 else "loss"
        text.append(f"{fmt_currency(net_pl)} ", style=pl_style)

        # Multi-Tag Badges (New in Phase 4)
        if tags:
            from .tui.tag_renderer import TagRenderer

            renderer = TagRenderer(self.portfolio_summary.get("triage_display", {}))
            text.append(" ")
            text.append(renderer.render_tags(tags))

        # Add Node
        node = parent_branch.add(text)

        # Add Detail Leaf
        detail_text = Text()
        detail_text.append(f"{dte} DTE", style="dim")
        if logic:
            detail_text.append(f": {logic}", style="dim")

        node.add(detail_text)

    def render_opportunities(self) -> None:
        """Renders top vol screener opportunities using Rich Table"""
        opportunities = self.data.get("opportunities", {})
        candidates = opportunities.get("candidates", [])
        meta = opportunities.get("meta", {})
        summary = opportunities.get("summary", {})

        if not candidates:
            if not summary:
                return

            self.console.print("\n[header]🔍 VOL SCREENER OPPORTUNITIES[/header]")
            self.console.print("   [dim]No candidates available for this scan[/dim]")

            scanned = summary.get("scanned_symbols_count", 0)
            if scanned:
                self.console.print(f"   [dim]Scanned {scanned} symbols[/dim]")

            excluded_count = meta.get("excluded_count", 0)
            if excluded_count > 0:
                excluded = meta.get("excluded_symbols", [])
                self.console.print(
                    f"   [warning]⚠️  {excluded_count} concentrated position(s) excluded: {', '.join(excluded[:3])}[/warning]"
                )

            drop_reasons = [
                ("missing IV", summary.get("iv_unavailable_count", 0)),
                ("illiquid", summary.get("illiquid_skipped_count", 0)),
                ("low vrp", summary.get("low_vrp_structural_count", 0)),
                ("missing tactical VRP", summary.get("tactical_skipped_count", 0)),
                ("market data errors", summary.get("market_data_error_count", 0)),
                ("low vol trap", summary.get("low_vol_trap_skipped_count", 0)),
                ("data integrity", summary.get("data_integrity_skipped_count", 0)),
            ]
            drop_reasons = [r for r in drop_reasons if r[1]]
            drop_reasons.sort(key=lambda x: x[1], reverse=True)
            if drop_reasons:
                top = ", ".join(f"{label}: {count}" for label, count in drop_reasons[:3])
                self.console.print(f"   [dim]Top filters: {top}[/dim]")

            return

        self.console.print("\n[header]🔍 VOL SCREENER OPPORTUNITIES[/header]")
        self.console.print("   [dim]High Vol Bias candidates for portfolio diversification[/dim]")

        # Show exclusion info
        excluded_count = meta.get("excluded_count", 0)
        if excluded_count > 0:
            excluded = meta.get("excluded_symbols", [])
            self.console.print(
                f"   [warning]⚠️  {excluded_count} concentrated position(s) excluded: {', '.join(excluded[:3])}[/warning]"
            )

        # Show Illiquid & Implied Info
        illiquid_count = summary.get("illiquid_skipped_count", 0)
        implied_count = summary.get("implied_liquidity_count", 0)
        correlation_skips = summary.get("correlation_skipped_count", 0)
        tactical_skips = summary.get("tactical_skipped_count", 0)
        correlation_max = summary.get("correlation_max")

        if illiquid_count > 0 or implied_count > 0:
            liq_text = Text("   ", style="dim")
            if illiquid_count > 0:
                liq_text.append(f"🚫 {illiquid_count} illiquid excluded ", style="dim red")
            if implied_count > 0:
                liq_text.append(
                    f"💧 {implied_count} accepted via tight spreads (0 vol)", style="dim cyan"
                )
            self.console.print(liq_text)

        if correlation_skips > 0:
            corr_note = ""
            if isinstance(correlation_max, (int, float)):
                corr_note = f" (ρ>{correlation_max:.2f})"
            self.console.print(
                f"   [dim]🔗 {correlation_skips} high correlation excluded{corr_note}[/dim]"
            )

        if tactical_skips > 0:
            self.console.print(f"   [dim]🧮 {tactical_skips} missing tactical VRP excluded[/dim]")

        # Check for Data Integrity Skips (Strict Mode)
        integrity_skips = summary.get("data_integrity_skipped_count", 0)
        lean_skips = summary.get("lean_data_skipped_count", 0)
        anomalous_skips = summary.get("anomalous_data_skipped_count", 0)

        total_hidden = (
            integrity_skips + lean_skips + anomalous_skips + correlation_skips + tactical_skips
        )
        if total_hidden > 0:
            filter_reasons: list[str] = []
            if integrity_skips:
                filter_reasons.append(f"{integrity_skips} bad data")
            if lean_skips:
                filter_reasons.append(f"{lean_skips} lean data")
            if anomalous_skips:
                filter_reasons.append(f"{anomalous_skips} anomalies")
            if correlation_skips:
                filter_reasons.append(f"{correlation_skips} high correlation")
            if tactical_skips:
                filter_reasons.append(f"{tactical_skips} missing tactical VRP")

            self.console.print(
                f"   [dim]🚫 {total_hidden} symbols hidden due to strict data filters: {', '.join(filter_reasons)}[/dim]"
            )

        table = Table(
            box=box.ROUNDED,
            header_style="header",
            border_style="dim",
            padding=(0, 1),
            expand=False,
        )
        table.add_column("Symbol", style="cyan", width=8)
        table.add_column("Price", justify="right", width=9)
        table.add_column("VRP (S)", justify="right", width=9)
        table.add_column("VRP (T)", justify="right", width=9)
        table.add_column("IVP", justify="right", width=7)
        table.add_column("Signal", width=12)
        table.add_column("Score", justify="right", width=7)
        table.add_column("Rho (ρ)", justify="right", width=9)
        table.add_column("Asset Class", width=14)

        for c in candidates:
            # Signal Styling
            sig = str(c.get("Signal", "N/A"))
            sig_style = "profit" if "RICH" in sig else "loss" if "DISCOUNT" in sig else "warning"

            # Rho Styling (RFC 020)
            rho = c.get("portfolio_rho")
            rho_str = f"{rho:.2f}" if rho is not None else "N/A"
            rho_style = "profit" if (rho or 0) < 0.4 else "warning" if (rho or 0) < 0.65 else "loss"

            vtm = c.get("vrp_tactical_markup")
            vtm_str = f"{vtm:+.0%}" if isinstance(vtm, (int, float)) else "N/A"

            ivp = c.get("IV Percentile")
            ivp_str = f"{ivp:.0f}" if isinstance(ivp, (int, float)) else "N/A"

            table.add_row(
                c.get("symbol", "N/A"),
                fmt_currency(c.get("price", 0)),
                f"{c.get('vrp_structural', 0):.2f}",
                vtm_str,
                ivp_str,
                f"[{sig_style}]{sig}[/]",
                f"{c.get('Score', 0):.1f}",
                f"[{rho_style}]{rho_str}[/]",
                c.get("Asset Class", "Equity"),
            )

        self.console.print(table)
        self.console.print(
            "   [dim]Legend: 💸 Rich | ↔️ Bound | ❄️ Cheap | 📅 Event | 🦇 BATS Efficient | 🌀 Coiled | ⚡ Expanding[/dim]"
        )

    def render_diagnostics(self) -> None:
        """Renders diagnostics panels for pipeline visibility."""
        panels = []

        market_diag = self.data.get("market_data_diagnostics", {})
        if market_diag:
            items = [
                ("Symbols", market_diag.get("symbols_total", 0)),
                ("Stale", market_diag.get("stale_count", 0)),
                ("Errors", market_diag.get("market_data_error_count", 0)),
                ("Missing IV", market_diag.get("iv_unavailable_count", 0)),
                ("Missing Hist", market_diag.get("history_unavailable_count", 0)),
                ("Missing Price", market_diag.get("price_unavailable_count", 0)),
                ("Unknown", market_diag.get("unknown_error_count", 0)),
            ]
            panels.append(self._build_diag_panel("MARKET DATA", items))

        triage_diag = self.data.get("triage_diagnostics", {})
        if triage_diag:
            items = [
                ("Positions", triage_diag.get("positions_total", 0)),
                ("Tagged", triage_diag.get("positions_with_tags", 0)),
                ("Stale", triage_diag.get("positions_stale", 0)),
                ("Missing Data", triage_diag.get("missing_market_data_count", 0)),
                ("Missing VRP T", triage_diag.get("missing_vrp_tactical_count", 0)),
                ("Missing VRP S", triage_diag.get("missing_vrp_structural_count", 0)),
            ]

            tag_items = [
                (k.replace("tag_", "").upper(), v)
                for k, v in triage_diag.items()
                if k.startswith("tag_") and v
            ]
            tag_items.sort(key=lambda x: x[1], reverse=True)
            for tag, count in tag_items[:4]:
                items.append((f"Tag {tag}", count))

            panels.append(self._build_diag_panel("TRIAGE", items))

        opportunities = self.data.get("opportunities", {})
        summary = opportunities.get("summary", {})
        if summary:
            items = [
                ("Scanned", summary.get("scanned_symbols_count", 0)),
                ("Candidates", summary.get("candidates_count", 0)),
                ("Low VRP", summary.get("low_vrp_structural_count", 0)),
                ("Missing VRP", summary.get("missing_vrp_structural_count", 0)),
                ("Missing VRP T", summary.get("tactical_skipped_count", 0)),
                ("Illiquid", summary.get("illiquid_skipped_count", 0)),
                ("Low IVP", summary.get("low_iv_percentile_skipped_count", 0)),
                ("High Corr", summary.get("correlation_skipped_count", 0)),
                ("Data Errors", summary.get("market_data_error_count", 0)),
            ]

            fetch_diag = opportunities.get("meta", {}).get("market_data_diagnostics", {})
            if fetch_diag:
                items.append(("Fetch Errors", fetch_diag.get("symbols_with_errors", 0)))
                items.append(("Fetch Stale", fetch_diag.get("stale_count", 0)))

            panels.append(self._build_diag_panel("SCREENER", items))

        if not panels:
            return

        grid = Table.grid(padding=(0, 2))
        grid.add_column()
        grid.add_column()

        row = []
        for panel in panels:
            row.append(panel)
            if len(row) == 2:
                grid.add_row(*row)
                row = []

        if row:
            grid.add_row(row[0], "")

        self.console.print("\n[header]DIAGNOSTICS[/header]")
        self.console.print(grid)

    def _build_diag_panel(self, title: str, items: list[tuple[str, Any]]) -> Panel:
        grid = Table.grid(padding=(0, 1))
        grid.add_column(justify="left")
        grid.add_column(justify="right")
        for label, value in items:
            grid.add_row(str(label), str(value))
        return Panel(grid, title=f"[header]{title}[/header]", border_style="blue", box=box.ROUNDED)


# --- Formatting Helpers ---


def fmt_currency(val: Optional[float]) -> str:
    if val is None:
        return "$0.00"
    return f"${val:,.2f}"


def fmt_percent(val: Optional[float]) -> str:
    if val is None:
        return "0.0%"
    return f"{val:.1%}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Variance Rich TUI Renderer")
    parser.add_argument("input_file", nargs="?", help="Input JSON file path")
    parser.add_argument(
        "--debug",
        "--diag",
        action="store_true",
        dest="show_diagnostics",
        help="Show diagnostics panels",
    )
    args = parser.parse_args()

    data = {}
    if args.input_file:
        with open(args.input_file) as f:
            data = json.load(f)
    elif not sys.stdin.isatty():
        data = json.load(sys.stdin)

    if not data:
        return

    renderer = TUIRenderer(data, show_diagnostics=args.show_diagnostics)
    renderer.render()


if __name__ == "__main__":
    main()
