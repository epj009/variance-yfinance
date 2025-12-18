import argparse
import json
import sys
import re # For stripping ANSI codes from string length calculation
from typing import Dict, List, Any, Optional

# Helper to calculate visible width of string (correcting for wide emojis)
def visible_len(s):
    length = len(s)
    
    # Heuristic for wide emojis that have len=1 in Python but width=2 in terminal
    # These cause misalignment if not accounted for.
    wide_len_1 = ["🔥", "🦇", "🌀", "📅", "✅", "💰", "💀", "🐳", "❓", "🚀", "😐"]
    
    for char in wide_len_1:
        length += s.count(char)
        
    return length

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
        net_liq_val = fmt_currency(net_liq)
        net_liq_display = f"• Net Liq:   {net_liq_val}"
        
        pl_str_colored = f"{fmt_currency(total_net_pl)} {pl_status}"

        # Calculate padding
        padding_needed = 35 - visible_len(net_liq_display)
        
        row1 = f"{net_liq_display}{' ' * padding_needed}{pl_str_colored}"
        lines.append(row1)

        # Row 2: BP Usage
        lines.append(f"• BP Usage:  {fmt_percent(bp_usage_pct)} {bp_status}")

        # Separator
        lines.append("_" * self.width)

        # 2. Gyroscope | Engine (Split Panel)
        beta_delta = self.portfolio_summary.get('total_beta_delta', 0.0)
        theta = self.portfolio_summary.get('total_portfolio_theta', 0.0)
        portfolio_vega = self.data.get('stress_box', {}).get('total_portfolio_vega', 0.0)
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
            f"• Vega:      {fmt_currency(portfolio_vega)}/pt",
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
        col_width = 58 # Visual width
        for i in range(5):
            left = gyro_lines[i] if i < len(gyro_lines) else ""
            right = engine_lines[i] if i < len(engine_lines) else ""
            
            # Pad left string based on its visible length to align the pipe
            pad = " " * (col_width - visible_len(left))
            lines.append(f"{left}{pad} | {right}")

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
            pl_display = f"{pl_str:>12}"

            output.append(f"│ {label:<11} │ {move_str:>10} │ {pl_display} │")

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
            "SIZE_THREAT": "🐳",
            "HEDGE_CHECK": "🛡️",
            "EARNINGS_WARNING": "📅",
            None: "⏳"
        }

        action_badges = {
            "HARVEST": "[HARVEST]",
            "DEFENSE": "[DEFENSE]",
            "GAMMA": "[GAMMA]",
            "ZOMBIE": "[ZOMBIE]",
            "SIZE_THREAT": "[SIZE RISK]",
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
            prefix = f"{root} ({strategy}) "

            # Right side content
            status_mark = ""
            if code == "HARVEST": status_mark = "✅"
            elif code in ["DEFENSE", "GAMMA", "SIZE_THREAT", "EARNINGS_WARNING"]: status_mark = "⚠️"
            elif code == "HEDGE_CHECK": status_mark = "ℹ️"

            # PL
            pl_display = fmt_currency(net_pl)

            # Calculate padding based on visible length
            raw_prefix_len = visible_len(prefix)
            
            # Estimate visible length of right_content
            # This is a bit tricky with emojis and dynamic content
            # Let's make a reasonable estimate for now, might need fine-tuning
            est_right_len = 1 + visible_len(icon) + 1 + visible_len(badge) + 1 + visible_len(pl_display) + 1 + visible_len(status_mark)

            # dot_count = max(5, self.width - raw_prefix_len - est_right_len)
            
            # More accurate visible length for the entire right part including icon and badge
            right_part_str = f" {icon} {badge} {pl_display} {status_mark}"
            dot_count = max(5, self.width - visible_len(prefix) - visible_len(right_part_str))


            dots = "." * dot_count

            line1 = f"{prefix}{dots}{right_part_str}"
            output.append(line1)

            # Line 2 (Tree branch)
            prefix2 = f"└── {dte} DTE: "
            output.append(f"{prefix2}{logic}")
            output.append("") # Spacer

        # 2. Render Holds Summary
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
            
            # Construct Bar: [|||||     ]
            bar_display = f"[{bar_str:<20}]"

            # Format: {rank:5} {symbol:6} [{bar:20}] {delta:+.2f}
            line = f"{rank:5} {sym:<6} {bar_display} {delta:+.2f}"
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
        output.append("┌────────┬────────────┬────────┬─────────┬──────────────┬─────────────────┐")
        output.append(f"│ {'Symbol':<6} │ {'Price':<10} │ {'Bias':<6} │ {'NVRP':<7} │ {'Signal':<12} │ {'Asset Class':<15} │")
        output.append("├────────┼────────────┼────────┼─────────┼──────────────┼─────────────────┤")

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
            bias_str = ""
            if vol_bias is not None:
                bias_str = f"{vol_bias:.2f}"
                if vol_bias > 1.2: 
                    bias_str = f"{bias_str:>6}"
                elif vol_bias > 1.0: 
                    bias_str = f"{bias_str:>6}"
                else:
                    bias_str = f"{bias_str:>6}" 
            else:
                bias_str = f"{'N/A':>6}"

            # Format NVRP
            nvrp = opp.get('NVRP')
            nvrp_str = "N/A"
            if nvrp is not None:
                val = nvrp * 100
                nvrp_str = f"{val:+.0f}%"
                nvrp_str = f"{nvrp_str:>7}"
            else:
                nvrp_str = f"{'N/A':>7}"

            # Signal Formatting
            sig_raw = opp.get('Signal', 'FAIR')
            sig_display = ""
            
            if sig_raw == "EVENT":
                sig_display = "📅 Event"
            elif sig_raw == "DISCOUNT":
                sig_display = "❄️ Cheap"
            elif sig_raw == "COILED":
                sig_display = "🗜️ Coiled"
            elif sig_raw == "RICH":
                sig_display = "🚀 Rich"
            else: # FAIR
                sig_display = "😐 Fair"
                
            # Padding
            pad_len = 12 - visible_len(sig_display)
            sig_padded = sig_display + (" " * max(0, pad_len))

            output.append(f"│ {sym:<6} │ {price_str:>10} │ {bias_str} │ {nvrp_str} │ {sig_padded} │ {asset_class:<15} │")

        output.append("└────────┴────────────┴────────┼─────────┼──────────────┼─────────────────┘")

        # Legend
        output.append("")
        output.append("   Legend: 🔥 Rich | 🗜️ Coiled | ❄️ Cheap | 📅 Event | 😐 Fair")

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
