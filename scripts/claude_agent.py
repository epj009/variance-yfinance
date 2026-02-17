#!/usr/bin/env python3
"""
Claude Runtime Agent for Variance

A CLI wrapper around the Anthropic API that provides an interactive
strategic analysis session for portfolio management.
"""

import argparse
import os
import sys

from anthropic import Anthropic
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel


def load_file_safely(filepath: str) -> str:
    """Load file content with error handling."""
    try:
        with open(filepath) as f:
            return f.read()
    except FileNotFoundError:
        return f"[File not found: {filepath}]"
    except Exception as e:
        return f"[Error loading {filepath}: {e}]"


def load_agent_instructions() -> str:
    """Load Variance agent persona from config/claude_persona.md."""
    persona_file = "config/claude_persona.md"
    if os.path.exists(persona_file):
        return load_file_safely(persona_file)

    # Fallback inline persona if file doesn't exist
    return """You are Variance, a quantitative trading strategist.

## Mission
"Separate Signal from Noise" - Provide actionable trade recommendations based on systematic volatility analysis.

## Philosophy
- Trade Small, Trade Often
- Quantitative rules over discretion
- Risk-first portfolio management

## Your Role
Analyze the portfolio dashboard and screening results to provide:
1. Triage priorities (what needs immediate action)
2. Risk exposure analysis (delta, gamma, correlation)
3. Opportunity assessment (new positions to consider)

## Output Style
- Clinical, data-driven analysis
- Specific actionable recommendations
- Risk/reward quantification for each suggestion
"""


def build_context(tui_file: str, json_file: str) -> str:
    """Build context from TUI output and JSON analysis."""
    tui_output = load_file_safely(tui_file)

    return f"""# Current Portfolio Dashboard

{tui_output}

# Data Source
Full analysis JSON available at: {json_file}

# Your Task
Analyze the dashboard above and provide strategic commentary on:
1. **Triage Priorities:** Which positions require immediate action (harvest, defense, gamma management)?
2. **Portfolio Balance:** Is delta/theta exposure balanced? Any concentration risks?
3. **Opportunities:** Which screener candidates align with current portfolio needs?

Then remain interactive for follow-up questions.
"""


def run_interactive_session(client: Anthropic, initial_message: str, model: str) -> None:
    """Run an interactive Claude session with Rich formatting."""
    console = Console()
    conversation_history = []

    # Header panel
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]STRATEGIC ANALYSIS[/bold cyan]",
            title="[bold white]CLAUDE[/bold white]",
            border_style="cyan",
        )
    )
    console.print()

    # Send initial message
    response = client.messages.create(
        model=model, max_tokens=4096, messages=[{"role": "user", "content": initial_message}]
    )

    assistant_message = response.content[0].text

    # Render response with Rich Markdown
    markdown = Markdown(assistant_message)
    console.print(markdown)
    console.print()

    # Store in history
    conversation_history.append({"role": "user", "content": initial_message})
    conversation_history.append({"role": "assistant", "content": assistant_message})

    # Interactive loop
    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", "bye"]:
                console.print("\n[dim]Ending session.[/dim]")
                break

            conversation_history.append({"role": "user", "content": user_input})

            response = client.messages.create(
                model=model, max_tokens=4096, messages=conversation_history
            )

            assistant_message = response.content[0].text
            conversation_history.append({"role": "assistant", "content": assistant_message})

            # Render follow-up response
            console.print()
            markdown = Markdown(assistant_message)
            console.print(markdown)
            console.print()

        except KeyboardInterrupt:
            console.print("\n[dim]Session interrupted.[/dim]")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            break


def main() -> None:
    parser = argparse.ArgumentParser(description="Claude Runtime Agent for Variance")
    parser.add_argument(
        "--tui",
        default="reports/variance_tui_output.txt",
        help="Path to TUI output file",
    )
    parser.add_argument(
        "--json",
        default="reports/variance_analysis.json",
        help="Path to analysis JSON",
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-5-20250929",
        help="Claude model to use",
    )
    parser.add_argument(
        "--prompt",
        "-p",
        help="Custom initial prompt (overrides default)",
    )
    args = parser.parse_args()

    # Check API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    # Initialize client
    client = Anthropic(api_key=api_key)

    # Build initial message
    if args.prompt:
        initial_message = args.prompt
    else:
        persona = load_agent_instructions()
        context = build_context(args.tui, args.json)
        initial_message = f"{persona}\n\n{context}"

    # Run session
    run_interactive_session(client, initial_message, args.model)


if __name__ == "__main__":
    main()
