from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.columns import Columns
from rich.text import Text
from rich import box

def show_poc():
    console = Console()
    
    # --- 1. Capital Console Header ---
    header_content = Layout(name="header")
    header_content.split_row(
        Layout(name="left"),
        Layout(name="right")
    )
    
    # Left: Core Metrics
    left_text = Text()
    left_text.append("• Net Liq:   ", style="dim")
    left_text.append("$50,000.00\n", style="bold white")
    left_text.append("• BP Usage:  ", style="dim")
    left_text.append("11.2% ", style="bold green")
    left_text.append("(Low - Deploy)", style="italic dim")
    
    # Right: P/L Status
    right_text = Text()
    right_text.append("Open P/L: ", style="dim")
    right_text.append("+$1,135.00 ", style="bold green")
    right_text.append("(🟢 Harvesting)", style="dim")
    
    header_panel = Panel(
        Columns([left_text, right_text], expand=True),
        title="[bold blue]THE CAPITAL CONSOLE[/bold blue]",
        border_style="blue",
        box=box.ROUNDED
    )
    
    # --- 2. Stress Box ---
    stress_table = Table(
        title="[bold yellow]📊 PROBABILISTIC STRESS TEST (1-Day Horizon)[/bold yellow]",
        show_header=True,
        header_style="bold magenta",
        box=box.MINIMAL_DOUBLE_HEAD,
        expand=True
    )
    stress_table.add_column("Confidence", width=20)
    stress_table.add_column("Sigma", justify="right")
    stress_table.add_column("Move pts", justify="right")
    stress_table.add_column("Est P/L", justify="right")
    stress_table.add_column("Delta Drift", justify="right")
    
    stress_table.add_row("Tail Risk (2SD-)", "-2.0σ", "-10.68", "[bold red]-$1,054.99[/bold red]", "+98.8 Δ")
    stress_table.add_row("1SD Move (-)", "-1.0σ", "-5.34", "[red]-$527.49[/red]", "+98.8 Δ")
    stress_table.add_row("Flat", "+0.0σ", "+0.00", "$0.00", "+98.8 Δ")
    stress_table.add_row("1SD Move (+)", "+1.0σ", "+5.34", "[green]+$527.49[/green]", "+98.8 Δ")
    stress_table.add_row("Tail Risk (2SD+)", "+2.0σ", "+10.77", "[bold green]+$1,054.99[/bold green]", "+98.8 Δ")

    # --- 3. Rendering ---
    console.print(header_panel)
    console.print(stress_table)
    console.print("\n[dim]Note: Rendering powered by 'rich' library for quant-desk resolution.[/dim]")

if __name__ == "__main__":
    show_poc()
