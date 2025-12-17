import argparse
import json
import sys
from typing import Dict, List, Any, Optional

class TUIRenderer:
    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.width = 120
        self.portfolio_summary = self.data.get('portfolio_summary', {})

    def render(self) -> str:
        """Orchestrates full TUI generation"""
        sections = []

        # 1. Header Panels
        sections.append(self.render_header())

        # 2. Delta Spectrograph
        spectrograph = self.render_spectrograph()
        if spectrograph:
            sections.append(spectrograph)

        # 3. Stress Box
        stress_box = self.render_stress_box()
        if stress_box:
            sections.append(stress_box)

        # 4. Portfolio Triage
        sections.append(self.render_triage())

        # 5. Vol Screener Opportunities
        opportunities = self.render_opportunities()
        if opportunities:
            sections.append(opportunities)

        return "\n\n".join(sections)

    def render_header(self) -> str:
        """Renders the dashboard header panels"""
        net_liq = self.portfolio_summary.get('net_liquidity', 0.0)
        total_net_pl = self.portfolio_summary.get('total_net_pl', 0.0)
        bp_usage_pct = self.portfolio_summary.get('bp_usage_pct', 0.0)

        # P/L Status
        if total_net_pl > 0:
            pl_status = "(🟢 Harvesting)"
        else:
            pl_status = "(🔴 Dragging)"

        # BP Status
        if bp_usage_pct < 0.50:
            bp_status = "(Low - Deploy)"
        elif bp_usage_pct <= 0.75:
            bp_status = "(Optimal)"
        else:
            bp_status = "(⚠️ High)"

        # 1. Capital Console (Top Panel)
        lines = []
        lines.append("THE CAPITAL CONSOLE (Fuel Gauge)")

        # Row 1: Net Liq & Open P/L
        net_liq_str = f"• Net Liq:   {fmt_currency(net_liq)}"
        pl_str = f"• Open P/L:  {fmt_currency(total_net_pl)} {pl_status}"

        # Padding for side-by-side
        # Approx spacing: Net Liq (30 chars) ... Open P/L (rest)
        row1 = f"{net_liq_str:<35} {pl_str}"
        lines.append(row1)

        # Row 2: BP Usage
        lines.append(f"• BP Usage:  {fmt_percent(bp_usage_pct)} {bp_status}")

        # Separator
        lines.append("_" * self.width)

        # 2. Gyroscope | Engine (Split Panel)
        # Prepare Data for Gyroscope (Left)
        beta_delta = self.portfolio_summary.get('total_beta_delta', 0.0)
        theta = self.portfolio_summary.get('total_portfolio_theta', 0.0)
        stability = self.portfolio_summary.get('delta_theta_ratio', 0.0)

        if beta_delta < -50:
            tilt_str = f"Bearish ({beta_delta:.0f} Δ)"
        elif beta_delta > 50:
            tilt_str = f"Bullish ({beta_delta:.0f} Δ)"
        else:
            tilt_str = f"Neutral ({beta_delta:.0f} Δ)"

        if -0.5 <= stability <= 0.5:
            stab_status = "(✅ Stable)"
        else:
            stab_status = "(⚠️ Unstable)"

        gyro_lines = [
            "THE GYROSCOPE (Risk)",
            f"• Tilt:      {tilt_str}",
            f"• Theta:     {fmt_currency(theta)}/day",
            f"• Vega:      {fmt_currency(self.data.get('stress_box', {}).get('total_portfolio_vega', 0.0))}/pt",
            f"• Stability: {fmt_decimal(stability)} {stab_status}"
        ]

        # Prepare Data for Engine (Right)
        friction = self.portfolio_summary.get('friction_horizon_days', 0.0)
        theta_pct = self.portfolio_summary.get('theta_net_liquidity_pct', 0.0)
        mix_warning = self.data.get('asset_mix_warning', {}).get('risk', False)

        if friction < 1.0:
            fric_status = "🟢 Liquid"
        elif friction > 3.0:
            fric_status = "🔴 Trap"
        else:
            fric_status = "🟠 Sticky"

        if mix_warning:
            mix_str = "⚠️ Equity Heavy"
        else:
            mix_str = "🌍 Diversified"

        engine_lines = [
            "THE ENGINE (Structure)",
            f"• Friction:  {friction:.1f} days ({fric_status})",
            f"• Usage:     {fmt_percent(theta_pct)} of Net Liq",
            f"• Mix:       {mix_str}"
        ]

        # Merge Columns
        # Left col width: 60 chars (including padding), Sep: "|", Right: Rest
        col_width = 58
        for i in range(5):
            left = gyro_lines[i] if i < len(gyro_lines) else ""
            right = engine_lines[i] if i < len(engine_lines) else ""
            lines.append(f"{left:<{col_width}} | {right}")

        return "\n".join(lines)

    def render_stress_box(self) -> str:
        stress_data = self.data.get('stress_box', {})
        scenarios = stress_data.get('scenarios', [])
        if not scenarios:
            return ""

        beta_symbol = stress_data.get('beta_symbol', 'SPY')
        beta_price = stress_data.get('beta_price', 0.0)
        net_liq = self.portfolio_summary.get('net_liquidity', 1.0)

        output = []

        # Check for crash warning
        for scen in scenarios:
            if scen.get('est_pl', 0) < (-0.10 * net_liq):
                output.append("⚠️ WARNING: CRASH SCENARIO RISK - Portfolio may lose >10% in market downturn")
                break

        output.append(f"⚠️  STRESS TEST (Beta: {beta_symbol} @ {fmt_currency(beta_price)})")

        # Table
        # Widths: Scenario (13), SPY Move (12), Est P/L (14) = ~45 chars total
        # ┌─────────────┬────────────┬──────────────┐
        output.append("┌─────────────┬────────────┬──────────────┐")
        output.append("│ Scenario    │ SPY Move   │ Est P/L      │")
        output.append("├─────────────┼────────────┼──────────────┤")

        for scen in scenarios:
            label = scen.get('label', '')[:11]
            move = scen.get('beta_move', 0.0)
            pl = scen.get('est_pl', 0.0)

            # Format move (e.g., "-22.5 pts")
            move_str = f"{move:+.1f} pts"

            # Format PL
            pl_str = fmt_currency(pl)

            output.append(f"│ {label:<11} │ {move_str:>10} │ {pl_str:>12} │")

        output.append("└─────────────┴────────────┴──────────────┘")
        return "\n".join(output)

    def render_triage(self) -> str:
        triage_actions = self.data.get('triage_actions', [])
        portfolio_overview = self.data.get('portfolio_overview', [])

        output = ["📊 PORTFOLIO TRIAGE", ""]

        action_icons = {
            "HARVEST": "💰",
            "DEFENSE": "🛡️",
            "GAMMA": "☢️",
            "ZOMBIE": "💀",
            "HEDGE_CHECK": "🛡️",
            "EARNINGS_WARNING": "📅",
            None: "⏳"
        }

        action_badges = {
            "HARVEST": "[HARVEST]",
            "DEFENSE": "[DEFENSE]",
            "GAMMA": "[GAMMA]",
            "ZOMBIE": "[ZOMBIE]",
            "HEDGE_CHECK": "[HEDGE]",
            "EARNINGS_WARNING": "[EARNINGS]",
            None: "[HOLD]"
        }

        # 1. Render Actions
        for action in triage_actions:
            root = action.get('symbol', 'UNKNOWN')
            strategy = action.get('strategy', 'Unknown')
            net_pl = action.get('net_pl', 0.0)
            code = action.get('action_code')
            dte = action.get('dte', 0)
            logic = action.get('logic', '')

            icon = action_icons.get(code, "❓")
            badge = action_badges.get(code, "[UNKNOWN]")

            # Line 1 construction
            # TSLA (Strangle) .............................. 💰 [HARVEST] +$350.00 ✅
            prefix = f"{root} ({strategy}) "

            # Right side content
            # " 💰 [HARVEST] +$350.00 ✅"
            # Note: The checkmark isn't in JSON, adding based on context (Harvest=Success)
            # Logic: If Harvest -> ✅, If Defense -> ⚠️, Else empty
            status_mark = ""
            if code == "HARVEST": status_mark = "✅"
            elif code in ["DEFENSE", "GAMMA"]: status_mark = "⚠️"

            right_content = f" {icon} {badge} {fmt_currency(net_pl)} {status_mark}"

            # Calculate padding
            dot_count = max(5, 120 - len(prefix) - len(right_content))
            dots = "." * dot_count

            line1 = f"{prefix}{dots}{right_content}"
            output.append(line1)

            # Line 2 (Tree branch)
            # └── 45 DTE: Profit target (>50%) hit. Close to free capital.
            # Handle multiline logic if needed, but assuming simple string
            prefix2 = f"└── {dte} DTE: "
            # Wrap logic text if too long?
            # Assuming logic is concise as per spec
            output.append(f"{prefix2}{logic}")
            output.append("") # Spacer

        # 2. Render Holds Summary
        # Count holds (items in overview not in triage actions or explicit null action)
        # Note: triage_actions usually subset of overview.
        # Strategy: Count items in portfolio_overview where action_code is None
        hold_count = 0
        for pos in portfolio_overview:
            if not pos.get('action_code'):
                hold_count += 1

        if hold_count > 0:
            plural = "position" if hold_count == 1 else "positions"
            output.append(f"⏳ HOLD: {hold_count} {plural} (no action required)")
        elif not triage_actions:
            output.append("No positions found.")

        return "\n".join(output)

    def render_spectrograph(self) -> str:
        deltas = self.data.get('delta_spectrograph', [])
        if not deltas:
            return ""

        output = [
            "📊 DELTA SPECTROGRAPH (Portfolio Drag)",
            "   Visualizing position contribution to Beta-Weighted Delta",
            ""
        ]

        # Take top 10
        top_deltas = deltas[:10]

        # Find max abs delta for scaling
        max_val = 0.0
        for d in top_deltas:
            val = abs(d.get('delta', 0.0))
            if val > max_val:
                max_val = val

        if max_val == 0:
            max_val = 1.0 # Prevent div zero

        max_bar_len = 20

        for rank, item in enumerate(top_deltas, start=1):
            sym = item.get('symbol', '')[:6]
            delta = item.get('delta', 0.0)

            bar_len = int((abs(delta) / max_val) * max_bar_len)

            # Use | for positive, - for negative
            if delta >= 0:
                bar_char = "|"
            else:
                bar_char = "-"

            bar_str = bar_char * bar_len

            # Format: {rank:5} {symbol:6} [{bar:20}] {delta:+.2f}
            line = f"{rank:5} {sym:<6} [{bar_str:<20}] {delta:+.2f}"
            output.append(line)

        return "\n".join(output)

    def render_opportunities(self) -> str:
        """Renders top 10 vol screener opportunities"""
        opportunities = self.data.get('opportunities', {})
        candidates = opportunities.get('candidates', [])
        meta = opportunities.get('meta', {})

        if not candidates:
            return ""

        output = [
            "🔍 VOL SCREENER OPPORTUNITIES (Top 10)",
            "   High Vol Bias candidates for portfolio diversification",
            ""
        ]

        # Show exclusion info if any
        excluded_count = meta.get('excluded_count', 0)
        if excluded_count > 0:
            excluded = meta.get('excluded_symbols', [])
            excluded_str = ", ".join(excluded[:3])
            if len(excluded) > 3:
                excluded_str += f" (+{len(excluded) - 3} more)"
            output.append(f"   ⚠️  {excluded_count} concentrated position(s) excluded: {excluded_str}")
            output.append("")

        # Take top 10
        top_opps = candidates[:10]

        # Header row
        # Symbol (8) | Price (12) | Vol Bias (10) | Asset Class (15) | Flags
        output.append("┌────────┬────────────┬──────────┬─────────────────┬─────────────┐")
        output.append("│ Symbol │ Price      │ Vol Bias │ Asset Class     │ Flags       │")
        output.append("├────────┼────────────┼──────────┼─────────────────┼─────────────┤")

        for opp in top_opps:
            sym = opp.get('Symbol', '')[:6]
            price = opp.get('Price')
            vol_bias = opp.get('Vol Bias')
            asset_class = opp.get('Asset Class', '')[:15]

            # Format price
            if price is not None:
                if price < 10:
                    price_str = f"${price:.4f}"
                else:
                    price_str = f"${price:.2f}"
            else:
                price_str = "N/A"

            # Format vol bias
            if vol_bias is not None:
                bias_str = f"{vol_bias:.2f}"
            else:
                bias_str = "N/A"

            # Build flags
            flags = []
            if opp.get('is_rich'):
                flags.append("🔥")
            if opp.get('is_earnings_soon'):
                flags.append("📅")
            if opp.get('is_held'):
                flags.append("🛡️")
            if opp.get('is_bats_efficient'):
                flags.append("🦇")

            flags_str = " ".join(flags) if flags else ""

            # Calculate display width (emojis are 2 chars wide)
            # Each emoji counts as 2, spaces count as 1
            display_width = sum(2 if ord(c) > 127 else 1 for c in flags_str)
            flags_padding = max(0, 11 - display_width)
            flags_padded = flags_str + (" " * flags_padding)

            output.append(f"│ {sym:<6} │ {price_str:>10} │ {bias_str:>8} │ {asset_class:<15} │ {flags_padded} │")

        output.append("└────────┴────────────┴──────────┴─────────────────┴─────────────┘")

        # Legend
        output.append("")
        output.append("   Legend: 🔥 Rich (high IV/HV) | 📅 Earnings Soon | 🛡️ Already Held | 🦇 BATS Efficient")

        return "\n".join(output)

# --- Formatting Helpers ---

def fmt_currency(val: float) -> str:
    """Format as $1,234.56"""
    if val is None: return "$0.00"
    return f"${val:,.2f}"

def fmt_percent(val: float) -> str:
    """Format as 12.5%"""
    if val is None: return "0.0%"
    return f"{val * 100:.1f}%"

def fmt_decimal(val: float, places: int = 2) -> str:
    """Format as 1.25"""
    if val is None: return "0.00"
    return f"{val:.{places}f}"

# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Variance TUI Renderer")
    parser.add_argument("input_file", nargs="?", help="Input JSON file path (optional, defaults to stdin)")
    args = parser.parse_args()

    data = {}

    # Try reading from file
    if args.input_file:
        try:
            with open(args.input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"ERROR: Could not read file {args.input_file} - {e}", file=sys.stderr)
            sys.exit(1)
    # Try reading from stdin
    elif not sys.stdin.isatty():
        try:
            content = sys.stdin.read()
            if content.strip():
                data = json.loads(content)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON from stdin - {e}", file=sys.stderr)
            sys.exit(1)

    if not data:
        # Fallback or silent exit if no data provided
        if args.input_file:
            sys.exit(1)
        # If interactive mode without file, maybe print help or nothing
        return

    renderer = TUIRenderer(data)
    try:
        print(renderer.render())
    except BrokenPipeError:
        # Handle pipe closed (e.g. | head)
        sys.stderr.close()
        sys.exit(0)

if __name__ == "__main__":
    main()
