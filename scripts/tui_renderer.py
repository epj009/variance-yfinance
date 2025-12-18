import argparse
import json
import sys
import re # For stripping ANSI codes from string length calculation
from typing import Dict, List, Any, Optional

class Colors:
    RESET = ""
    BOLD = ""
    DIM = ""
    UNDERLINE = ""
    
    RED = ""
    GREEN = ""
    YELLOW = ""
    BLUE = ""
    MAGENTA = ""
    CYAN = ""
    WHITE = ""
    
    BG_RED = ""
    BG_GREEN = ""

# Helper to calculate visible length of string with ANSI codes
def visible_len(s):
    clean_s = re.sub(r'\x1b\[[0-9;]*m', '', s)
    length = len(clean_s)
    
    # Heuristic for wide emojis that have len=1 in Python but width=2 in terminal
    # These cause misalignment if not accounted for.
    wide_len_1 = ["🔥", "🦇", "🌀", "📅", "✅", "💰", "💀", "🐳", "❓"]
    
    for char in wide_len_1:
        length += clean_s.count(char)
        
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
            pl_color = Colors.GREEN
            pl_status = f"({Colors.GREEN}🟢 Harvesting{Colors.RESET})"
        else:
            pl_color = Colors.RED
            pl_status = f"({Colors.RED}🔴 Dragging{Colors.RESET})"

        # BP Status
        if bp_usage_pct < 0.50:
            bp_color = Colors.GREEN
            bp_status = f"({Colors.GREEN}Low - Deploy{Colors.RESET})"
        elif bp_usage_pct <= 0.75:
            bp_color = Colors.YELLOW
            bp_status = f"({Colors.YELLOW}Optimal{Colors.RESET})"
        else:
            bp_color = Colors.RED
            bp_status = f"({Colors.RED}⚠️ High{Colors.RESET})"

        # 1. Capital Console (Top Panel)
        lines = []
        lines.append(f"{Colors.BOLD}{Colors.CYAN}THE CAPITAL CONSOLE (Fuel Gauge){Colors.RESET}")

        # Row 1: Net Liq & Open P/L
        net_liq_val = fmt_currency(net_liq)
        net_liq_display = f"• Net Liq:   {Colors.BOLD}{net_liq_val}{Colors.RESET}"
        
        # Define pl_str properly
        pl_str_colored = f"{pl_color}{fmt_currency(total_net_pl)}{Colors.RESET} {pl_status}"

        # Calculate padding needed, accounting for ANSI codes
        # 35 chars is target total width for net_liq_display + padding
        padding_needed = 35 - visible_len(net_liq_display)
        
        row1 = f"{net_liq_display}{' ' * padding_needed}{pl_str_colored}"
        lines.append(row1)

        # Row 2: BP Usage
        lines.append(f"• BP Usage:  {bp_color}{fmt_percent(bp_usage_pct)}{Colors.RESET} {bp_status}")

        # Separator
        lines.append(f"{Colors.DIM}" + "_" * self.width + f"{Colors.RESET}")

        # 2. Gyroscope | Engine (Split Panel)
        # Prepare Data for Gyroscope (Left)
        beta_delta = self.portfolio_summary.get('total_beta_delta', 0.0)
        theta = self.portfolio_summary.get('total_portfolio_theta', 0.0)
        portfolio_vega = self.data.get('stress_box', {}).get('total_portfolio_vega', 0.0)
        stability = self.portfolio_summary.get('delta_theta_ratio', 0.0)

        if beta_delta < -50:
            tilt_str = f"{Colors.RED}Bearish{Colors.RESET} ({beta_delta:.0f} Δ)"
        elif beta_delta > 50:
            tilt_str = f"{Colors.GREEN}Bullish{Colors.RESET} ({beta_delta:.0f} Δ)"
        else:
            tilt_str = f"{Colors.YELLOW}Neutral{Colors.RESET} ({beta_delta:.0f} Δ)"

        if -0.5 <= stability <= 0.5:
            stab_status = f"({Colors.GREEN}✅ Stable{Colors.RESET})"
            stab_val_color = Colors.GREEN
        else:
            stab_status = f"({Colors.RED}⚠️ Unstable{Colors.RESET})"
            stab_val_color = Colors.RED

        gyro_lines = [
            f"{Colors.BOLD}{Colors.CYAN}THE GYROSCOPE (Risk){Colors.RESET}",
            f"• Tilt:      {tilt_str}",
            f"• Theta:     {Colors.GREEN}{fmt_currency(theta)}{Colors.RESET}/day",
            f"• Vega:      {Colors.CYAN}{fmt_currency(portfolio_vega)}{Colors.RESET}/pt",
            f"• Stability: {stab_val_color}{fmt_decimal(stability)}{Colors.RESET} {stab_status}"
        ]

        # Prepare Data for Engine (Right)
        friction = self.portfolio_summary.get('friction_horizon_days', 0.0)
        theta_pct = self.portfolio_summary.get('theta_net_liquidity_pct', 0.0)
        mix_warning = self.data.get('asset_mix_warning', {}).get('risk', False)

        if friction < 1.0:
            fric_status = f"{Colors.GREEN}🟢 Liquid{Colors.RESET}"
            fric_color = Colors.GREEN
        elif friction > 3.0:
            fric_status = f"{Colors.RED}🔴 Trap{Colors.RESET}"
            fric_color = Colors.RED
        else:
            fric_status = f"{Colors.YELLOW}🟠 Sticky{Colors.RESET}"
            fric_color = Colors.YELLOW

        if mix_warning:
            mix_str = f"{Colors.YELLOW}⚠️ Equity Heavy{Colors.RESET}"
        else:
            mix_str = f"{Colors.GREEN}🌍 Diversified{Colors.RESET}"

        # Usage Color
        if 0.001 <= theta_pct <= 0.005:
            usage_color = Colors.GREEN
        elif theta_pct > 0.005:
            usage_color = Colors.RED
        else:
            usage_color = Colors.YELLOW

        engine_lines = [
            f"{Colors.BOLD}{Colors.CYAN}THE ENGINE (Structure){Colors.RESET}",
            f"• Friction:  {fric_color}{friction:.1f} days{Colors.RESET} ({fric_status})",
            f"• Usage:     {usage_color}{fmt_percent(theta_pct)}{Colors.RESET} of Net Liq",
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
                output.append(f"{Colors.BG_RED}{Colors.WHITE} ⚠️ WARNING: CRASH SCENARIO RISK - Portfolio may lose >10% in market downturn {Colors.RESET}")
                break

        output.append(f"⚠️  {Colors.BOLD}STRESS TEST{Colors.RESET} (Beta: {beta_symbol} @ {fmt_currency(beta_price)})")

        # Table
        # ┌─────────────┬────────────┬──────────────┐
        output.append(f"{Colors.DIM}┌─────────────┬────────────┬──────────────┐{Colors.RESET}")
        output.append(f"{Colors.DIM}│{Colors.RESET} {Colors.BOLD}{'Scenario':<11}{Colors.RESET} {Colors.DIM}│{Colors.RESET} {Colors.BOLD}{'SPY Move':<10}{Colors.RESET} {Colors.DIM}│{Colors.RESET} {Colors.BOLD}{'Est P/L':<12}{Colors.RESET} {Colors.DIM}│{Colors.RESET}")
        output.append(f"{Colors.DIM}├─────────────┼────────────┼──────────────┤{Colors.RESET}")

        for scen in scenarios:
            label = scen.get('label', '')[:11]
            move = scen.get('beta_move', 0.0)
            pl = scen.get('est_pl', 0.0)

            # Format move (e.g., "-22.5 pts")
            move_str = f"{move:+.1f} pts"

            # Format PL
            pl_str = fmt_currency(pl)
            if pl > 0:
                pl_display = f"{Colors.GREEN}{pl_str:>12}{Colors.RESET}"
            elif pl < 0:
                pl_display = f"{Colors.RED}{pl_str:>12}{Colors.RESET}"
            else:
                pl_display = f"{Colors.DIM}{pl_str:>12}{Colors.RESET}"

            output.append(f"{Colors.DIM}│{Colors.RESET} {label:<11} {Colors.DIM}│{Colors.RESET} {move_str:>10} {Colors.DIM}│{Colors.RESET} {pl_display} {Colors.DIM}│{Colors.RESET}")

        output.append(f"{Colors.DIM}└─────────────┴────────────┴──────────────┘{Colors.RESET}")
        return "\n".join(output)

    def render_triage(self) -> str:
        triage_actions = self.data.get('triage_actions', [])
        portfolio_overview = self.data.get('portfolio_overview', [])

        output = [f"{Colors.BOLD}{Colors.MAGENTA}📊 PORTFOLIO TRIAGE{Colors.RESET}", ""]

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
            "HARVEST": f"{Colors.GREEN}[HARVEST]{Colors.RESET}",
            "DEFENSE": f"{Colors.YELLOW}[DEFENSE]{Colors.RESET}",
            "GAMMA": f"{Colors.RED}[GAMMA]{Colors.RESET}",
            "ZOMBIE": f"{Colors.DIM}{Colors.WHITE}[ZOMBIE]{Colors.RESET}",
            "SIZE_THREAT": f"{Colors.RED}[SIZE RISK]{Colors.RESET}",
            "HEDGE_CHECK": f"{Colors.BLUE}[HEDGE]{Colors.RESET}",
            "EARNINGS_WARNING": f"{Colors.YELLOW}[EARNINGS]{Colors.RESET}",
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
            badge = action_badges.get(code, f"{Colors.MAGENTA}[UNKNOWN]{Colors.RESET}")

            # Line 1 construction
            prefix = f"{Colors.BOLD}{root}{Colors.RESET} ({strategy}) "

            # Right side content
            status_mark = ""
            if code == "HARVEST": status_mark = "✅"
            elif code in ["DEFENSE", "GAMMA", "SIZE_THREAT", "EARNINGS_WARNING"]: status_mark = "⚠️"
            elif code == "HEDGE_CHECK": status_mark = "ℹ️"

            # Colorize P/L
            if net_pl > 0:
                pl_display = f"{Colors.GREEN}{fmt_currency(net_pl)}{Colors.RESET}"
            elif net_pl < 0:
                pl_display = f"{Colors.RED}{fmt_currency(net_pl)}{Colors.RESET}"
            else:
                pl_display = f"{Colors.DIM}{fmt_currency(net_pl)}{Colors.RESET}"

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


            dots = f"{Colors.DIM}" + "." * dot_count + f"{Colors.RESET}"

            line1 = f"{prefix}{dots}{right_part_str}"
            output.append(line1)

            # Line 2 (Tree branch)
            prefix2 = f"{Colors.DIM}└──{Colors.RESET} {dte} DTE: "
            output.append(f"{prefix2}{Colors.DIM}{logic}{Colors.RESET}")
            output.append("") # Spacer

        # 2. Render Holds Summary
        hold_count = 0
        for pos in portfolio_overview:
            if not pos.get('action_code'):
                hold_count += 1

        if hold_count > 0:
            plural = "position" if hold_count == 1 else "positions"
            output.append(f"{Colors.DIM}⏳ HOLD: {hold_count} {plural} (no action required){Colors.RESET}")
        elif not triage_actions:
            output.append("No positions found.")

        return "\n".join(output)

    def render_spectrograph(self) -> str:
        deltas = self.data.get('delta_spectrograph', [])
        if not deltas:
            return ""

        output = [
            f"{Colors.BOLD}{Colors.MAGENTA}📊 DELTA SPECTROGRAPH (Portfolio Drag){Colors.RESET}",
            f"   {Colors.DIM}Visualizing position contribution to Beta-Weighted Delta{Colors.RESET}",
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
                bar_color = Colors.GREEN
            else:
                bar_char = "-"
                bar_color = Colors.RED

            bar_str = bar_char * bar_len
            
            # Construct Bar: [|||||     ]
            bar_display = f"{Colors.DIM}[{Colors.RESET}{bar_color}{bar_str:<20}{Colors.RESET}{Colors.DIM}]{Colors.RESET}"

            # Format: {rank:5} {symbol:6} [{bar:20}] {delta:+.2f}
            line = f"{rank:5} {Colors.BOLD}{sym:<6}{Colors.RESET} {bar_display} {bar_color}{delta:+.2f}{Colors.RESET}"
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
            f"{Colors.BOLD}{Colors.MAGENTA}🔍 VOL SCREENER OPPORTUNITIES (Top 10){Colors.RESET}",
            f"   {Colors.DIM}High Vol Bias candidates for portfolio diversification{Colors.RESET}",
            ""
        ]

        # Show exclusion info if any
        excluded_count = meta.get('excluded_count', 0)
        if excluded_count > 0:
            excluded = meta.get('excluded_symbols', [])
            excluded_str = ", ".join(excluded[:3])
            if len(excluded) > 3:
                excluded_str += f" (+{len(excluded) - 3} more)"
            output.append(f"   {Colors.YELLOW}⚠️  {excluded_count} concentrated position(s) excluded: {excluded_str}{Colors.RESET}")
            output.append("")

        # Take top 10
        top_opps = candidates[:10]

        # Header row
        output.append(f"{Colors.DIM}┌────────┬────────────┬────────┬─────────┬─────────────────┬─────────────┐{Colors.RESET}")
        output.append(f"{Colors.DIM}│{Colors.RESET} {Colors.BOLD}{'Symbol':<6}{Colors.RESET} {Colors.DIM}│{Colors.RESET} {Colors.BOLD}{'Price':<10}{Colors.RESET} {Colors.DIM}│{Colors.RESET} {Colors.BOLD}{'Bias':<6}{Colors.RESET} {Colors.DIM}│{Colors.RESET} {Colors.BOLD}{'NVRP':<7}{Colors.RESET} {Colors.DIM}│{Colors.RESET} {Colors.BOLD}{'Asset Class':<15}{Colors.RESET} {Colors.DIM}│{Colors.RESET} {Colors.BOLD}{'Flags':<11}{Colors.RESET} {Colors.DIM}│{Colors.RESET}")
        output.append(f"{Colors.DIM}├────────┼────────────┼────────┼─────────┼─────────────────┼─────────────┤{Colors.RESET}")

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
                if vol_bias > 1.2: # Very rich
                    bias_str = f"{Colors.RED}{bias_str:>6}{Colors.RESET}"
                elif vol_bias > 1.0: # Rich
                    bias_str = f"{Colors.YELLOW}{bias_str:>6}{Colors.RESET}"
                else:
                    bias_str = f"{bias_str:>6}" # Fair/Low
            else:
                bias_str = f"{'N/A':>6}"

            # Format NVRP
            nvrp = opp.get('NVRP')
            nvrp_str = "N/A"
            if nvrp is not None:
                val = nvrp * 100
                nvrp_str = f"{val:+.0f}%"
                if val > 50: # > 50% Markup
                    nvrp_str = f"{Colors.GREEN}{nvrp_str:>7}{Colors.RESET}"
                elif val < 0: # Discount
                    nvrp_str = f"{Colors.RED}{nvrp_str:>7}{Colors.RESET}"
                else:
                    nvrp_str = f"{nvrp_str:>7}"
            else:
                nvrp_str = f"{'N/A':>7}"

            # Build flags with colors
            flags_list = []
            if opp.get('is_rich'):
                flags_list.append(f"{Colors.RED}🔥{Colors.RESET}")
            if opp.get('is_coiled'):
                flags_list.append(f"{Colors.CYAN}🗜️{Colors.RESET}")
            if opp.get('is_earnings_soon'):
                flags_list.append(f"{Colors.YELLOW}📅{Colors.RESET}")
            if opp.get('is_held'):
                flags_list.append(f"{Colors.BLUE}🛡️{Colors.RESET}")
            if opp.get('is_bats_efficient'):
                flags_list.append(f"{Colors.MAGENTA}🦇{Colors.RESET}")
            
            flags_str_colored = " ".join(flags_list)
            # Pad based on visible length of the colored string
            flags_padded = flags_str_colored + (" " * max(0, 11 - visible_len(flags_str_colored)))


            output.append(f"{Colors.DIM}│{Colors.RESET} {sym:<6} {Colors.DIM}│{Colors.RESET} {price_str:>10} {Colors.DIM}│{Colors.RESET} {bias_str} {Colors.DIM}│{Colors.RESET} {nvrp_str} {Colors.DIM}│{Colors.RESET} {asset_class:<15} {Colors.DIM}│{Colors.RESET} {flags_padded} {Colors.DIM}│{Colors.RESET}")

        output.append(f"{Colors.DIM}└────────┴────────────┴────────┼─────────┼─────────────────┼─────────────┘{Colors.RESET}")

        # Legend
        output.append("")
        output.append(f"   {Colors.DIM}Legend: {Colors.RED}🔥 Rich{Colors.RESET} | {Colors.CYAN}🗜️ Coiled{Colors.RESET} | {Colors.YELLOW}📅 Earnings{Colors.RESET} | {Colors.BLUE}🛡️ Held{Colors.RESET} | {Colors.MAGENTA}🦇 BATS{Colors.RESET}{Colors.RESET}")

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
