# Migrating Runtime Agent from Gemini to Claude

**Date:** 2026-01-01
**Status:** Implementation Guide
**Purpose:** Replace Google Gemini CLI with Claude (Anthropic API) as the runtime strategic analysis agent

---

## Current Architecture

### How Gemini is Used

The `./variance` script has three execution modes that use Gemini:

**1. Hybrid Mode (default):**
```bash
./variance  # or ./variance --hybrid
```
- Runs portfolio analysis → generates JSON
- Renders TUI dashboard
- Launches Gemini CLI with:
  - Pre-populated context (TUI output, JSON file paths)
  - Strategic analysis prompt
  - Interactive session for follow-up questions

**2. Chat Mode:**
```bash
./variance --chat  # or --gemini
```
- Skips TUI
- Launches Gemini CLI directly with strategic analysis prompt

**3. TUI-Only Mode:**
```bash
./variance --tui
```
- Runs analysis and TUI only (no AI agent)

### Gemini CLI Integration Points

**File:** `variance` (bash script)

**Hybrid Mode (lines 242-258):**
```bash
exec gemini -y -i "First, display the Variance TUI dashboard by running: cat $TUI_FILE

Then provide strategic commentary on:
1. Priority actions from the triage (harvest, defense, gamma risks)
2. Delta/theta balance concerns
3. Top opportunities from the vol screener

The full analysis JSON is at $JSON_FILE if you need detailed data.

Then stay interactive for follow-up questions about the portfolio."
```

**Chat Mode (lines 260-263):**
```bash
exec gemini -y -i "Variance, analyze the latest portfolio positions and identify actionable trades based on current market conditions and trading rules."
```

### Context Loading

Gemini CLI reads context from:
- `.geminiignore` - Defines what files Gemini can access
- Agent instructions (implicitly, via prompt engineering sections in `.claude/agents/*.md`)
- Runtime files: `reports/variance_analysis.json`, `reports/variance_tui_output.txt`

---

## Migration Strategy

### Option 1: Use Anthropic CLI (Simplest)

**Prerequisites:**
```bash
# Install Anthropic CLI
pip install anthropic-cli

# Set API key
export ANTHROPIC_API_KEY="sk-ant-..."
```

**Implementation:**
Replace `gemini` calls with `anthropic` CLI in the `variance` script.

**Hybrid Mode:**
```bash
exec anthropic -m claude-sonnet-4-5 -p "$(cat <<'EOF'
You are Variance, a quantitative trading strategist powered by Claude.

First, display the Variance TUI dashboard:
$(cat $TUI_FILE)

Then provide strategic commentary on:
1. Priority actions from the triage (harvest, defense, gamma risks)
2. Delta/theta balance concerns
3. Top opportunities from the vol screener

The full analysis JSON is available at: $JSON_FILE

Remain interactive for follow-up questions about the portfolio.
EOF
)"
```

**Pros:**
- ✅ Minimal code changes (swap CLI command)
- ✅ Similar UX to Gemini
- ✅ Uses Anthropic's official tooling

**Cons:**
- ❌ Anthropic may not have an official CLI tool (check availability)
- ❌ Less control over context window management

---

### Option 2: Custom Python Script with Anthropic SDK (Recommended)

Create a custom `claude` CLI wrapper that uses the Anthropic SDK.

#### Step 1: Create `scripts/claude_agent.py`

```python
#!/usr/bin/env python3
"""
Claude Runtime Agent for Variance

A CLI wrapper around the Anthropic API that provides an interactive
strategic analysis session for portfolio management.
"""

import argparse
import json
import os
import sys
from anthropic import Anthropic

def load_file_safely(filepath: str) -> str:
    """Load file content with error handling."""
    try:
        with open(filepath, 'r') as f:
            return f.read()
    except FileNotFoundError:
        return f"[File not found: {filepath}]"
    except Exception as e:
        return f"[Error loading {filepath}: {e}]"

def load_agent_instructions() -> str:
    """Load Variance agent persona from system_prompt.md or similar."""
    # Option A: Load from dedicated file
    persona_file = "config/claude_persona.md"
    if os.path.exists(persona_file):
        return load_file_safely(persona_file)

    # Option B: Inline persona
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

    # Optionally load JSON for detailed data
    # json_data = load_file_safely(json_file)
    # For now, just reference it

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

def run_interactive_session(client: Anthropic, initial_message: str, model: str):
    """Run an interactive Claude session."""
    conversation_history = []

    # Send initial message
    print("\n" + "━" * 80)
    print("CLAUDE (Strategic Analysis)")
    print("━" * 80 + "\n")

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": initial_message}]
    )

    assistant_message = response.content[0].text
    print(assistant_message)
    print("\n" + "━" * 80 + "\n")

    # Store in history
    conversation_history.append({"role": "user", "content": initial_message})
    conversation_history.append({"role": "assistant", "content": assistant_message})

    # Interactive loop
    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ['exit', 'quit', 'bye']:
                print("Ending session.")
                break

            conversation_history.append({"role": "user", "content": user_input})

            response = client.messages.create(
                model=model,
                max_tokens=4096,
                messages=conversation_history
            )

            assistant_message = response.content[0].text
            conversation_history.append({"role": "assistant", "content": assistant_message})

            print(f"\nClaude: {assistant_message}\n")

        except KeyboardInterrupt:
            print("\nSession interrupted.")
            break
        except Exception as e:
            print(f"Error: {e}")
            break

def main():
    parser = argparse.ArgumentParser(description="Claude Runtime Agent for Variance")
    parser.add_argument("--tui", default="reports/variance_tui_output.txt", help="Path to TUI output file")
    parser.add_argument("--json", default="reports/variance_analysis.json", help="Path to analysis JSON")
    parser.add_argument("--model", default="claude-sonnet-4-5-20250929", help="Claude model to use")
    parser.add_argument("--prompt", "-p", help="Custom initial prompt (overrides default)")
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
```

#### Step 2: Update `variance` Script

**Replace Gemini calls with Claude script:**

**Hybrid Mode (line 242-258):**
```bash
# Old:
# exec gemini -y -i "..."

# New:
exec ./venv/bin/python3 scripts/claude_agent.py \
    --tui "$TUI_FILE" \
    --json "$JSON_FILE"
```

**Chat Mode (line 260-263):**
```bash
# Old:
# exec gemini -y -i "..."

# New:
exec ./venv/bin/python3 scripts/claude_agent.py \
    --prompt "Variance, analyze the latest portfolio positions and identify actionable trades based on current market conditions."
```

#### Step 3: Create Claude Persona File

**File:** `config/claude_persona.md`

```markdown
# VARIANCE STRATEGIC ANALYSIS AGENT

You are **Variance**, a quantitative trading strategist powered by Claude Sonnet 4.5.

## Core Identity
- **Mission:** "Separate Signal from Noise"
- **Philosophy:** Trade Small, Trade Often
- **Strategy:** Systematic volatility premium capture through options selling

## Your Responsibilities

### 1. Triage Analysis
Review the ACTION REQUIRED section and prioritize:
- **Harvest:** Positions at profit targets (risk-free gains)
- **Defense:** Positions breaching risk thresholds (stop losses)
- **Gamma:** Explosive gamma risk (tail risk management)
- **Expiration:** Positions <7 DTE (roll or close)

### 2. Portfolio Health Check
Assess exposure metrics:
- **Delta/Theta Ratio:** Is the portfolio balanced for premium capture?
- **Beta Tilt:** Directional bias (bearish < -50, bullish > +50, neutral -50 to +50)
- **Correlation Risk:** Concentrated positions (avg rho > 0.65 = warning)
- **Stability:** Stress test results (downside/upside scenarios)

### 3. Opportunity Evaluation
Review VOL SCREENER OPPORTUNITIES:
- **Signal Strength:** RICH IV + EXPANDING VRP = strong sell signal
- **Diversification:** Prefer low portfolio rho (< 0.4 = ideal)
- **Quality:** High IVP (> 60), strong VRP (> 1.3), adequate yield (> 5%)

### 4. Strategic Recommendations
Provide actionable guidance:
- Which triage actions to execute first (priority order)
- Portfolio adjustments needed (reduce delta, add hedges, rebalance)
- Top 2-3 screener candidates with rationale
- Risk mitigation steps if stress scenarios are concerning

## Output Style
- **Clinical:** Data-driven, no marketing fluff
- **Quantitative:** Reference specific metrics (VRP, IVP, DTE, rho)
- **Actionable:** Clear next steps ("Close AAPL at 50% profit", not "Consider AAPL")
- **Risk-aware:** Flag tail risks, concentration, correlation

## Interaction Mode
After initial analysis, stay interactive for:
- "Why INTC over MSFT?" → Compare rho, VRP, yield
- "What if SPY drops 5%?" → Reference downside stress scenario
- "Show me the gamma risk calculation" → Explain gamma exposure math

## Remember
You are the strategic layer that interprets quantitative data for human decision-making.
Your analysis bridges the gap between raw numbers and executable trades.
```

#### Step 4: Update Dependencies

```bash
# Add to requirements.txt
anthropic>=0.34.0
```

```bash
# Install
pip install -r requirements.txt
```

#### Step 5: Set Environment Variable

```bash
# Add to .env.tastytrade or .env
export ANTHROPIC_API_KEY="sk-ant-api03-..."
```

**Update `variance` script to load it:**
```bash
# After line 10
if [ -f .env.tastytrade ]; then
    source .env.tastytrade
fi

# Add:
if [ -f .env.anthropic ]; then
    source .env.anthropic
fi
```

---

### Option 3: Use Claude Code MCP Server (Advanced)

Leverage the Model Context Protocol (MCP) to give Claude access to Variance files.

**Concept:**
- Run Claude Code with custom MCP server
- MCP server exposes Variance JSON/TUI files as tools
- Claude can read files, run diagnostics, execute screener

**Implementation:**
- Requires building custom MCP server
- More complex but provides richer tool access
- Allows Claude to run Python scripts directly

**Deferred:** This is overkill for current needs. Option 2 is sufficient.

---

## Migration Checklist

### Phase 1: Preparation
- [ ] Choose migration strategy (recommend Option 2)
- [ ] Obtain Anthropic API key
- [ ] Add `anthropic` to requirements.txt
- [ ] Install dependencies: `pip install -r requirements.txt`

### Phase 2: Implementation
- [ ] Create `scripts/claude_agent.py` (copy from Option 2)
- [ ] Create `config/claude_persona.md` (Variance strategic agent instructions)
- [ ] Update `variance` script (replace `gemini` with `claude_agent.py`)
- [ ] Add ANTHROPIC_API_KEY to environment (.env or .env.anthropic)
- [ ] Update `.gitignore` to exclude `.env.anthropic`

### Phase 3: Testing
- [ ] Test hybrid mode: `./variance --hybrid`
  - Verify TUI displays correctly
  - Verify Claude session starts with correct context
  - Test interactive follow-up questions
- [ ] Test chat mode: `./variance --chat`
  - Verify Claude starts without TUI
  - Verify strategic analysis prompt works
- [ ] Test TUI-only mode: `./variance --tui` (should be unchanged)

### Phase 4: Documentation
- [ ] Update `README.md` with Claude setup instructions
- [ ] Update `HANDOFF.md` with new agent architecture
- [ ] Document environment variables needed
- [ ] Remove or deprecate Gemini references

### Phase 5: Cleanup
- [ ] Remove `.geminiignore` (no longer needed)
- [ ] Remove Gemini-specific instructions from `.claude/agents/*.md`
- [ ] Update `--chat|--gemini` flag to `--chat|--claude` for clarity
- [ ] Archive old Gemini integration notes

---

## File Changes Summary

### New Files
```
scripts/claude_agent.py           # Claude CLI wrapper (Option 2)
config/claude_persona.md           # Strategic agent instructions
.env.anthropic                     # API key storage (gitignored)
```

### Modified Files
```
variance                           # Replace gemini → claude_agent.py calls
requirements.txt                   # Add anthropic>=0.34.0
.gitignore                         # Add .env.anthropic
README.md                          # Update setup instructions
HANDOFF.md                         # Document new architecture
```

### Deprecated Files
```
.geminiignore                      # No longer needed
```

---

## Cost Considerations

**Anthropic API Pricing (as of 2026-01):**
- Claude Sonnet 4.5: ~$3/million input tokens, ~$15/million output tokens
- Typical Variance session: ~2,000 input tokens (TUI + JSON), ~1,000 output tokens
- **Cost per session:** ~$0.02

**Comparison:**
- Gemini API: ~$0.01 per session (cheaper)
- Claude API: ~$0.02 per session (slightly more expensive, but higher quality)

**Monthly Cost (30 trading days, 2 sessions/day):**
- 60 sessions × $0.02 = **$1.20/month**

**Acceptable:** For institutional-grade analysis, the cost is negligible.

---

## Benefits of Claude over Gemini

1. **Superior Reasoning:** Claude Sonnet 4.5 has stronger quantitative analysis capabilities
2. **Better Context Handling:** Claude maintains conversation context more effectively
3. **Safety:** Anthropic's Constitutional AI is better aligned for financial advice
4. **Ecosystem:** Integration with Claude Code tools and MCP servers
5. **Reliability:** More consistent output quality for complex multi-step reasoning

---

## Next Steps

1. **Decide on Option 2** (Custom Python Script) - Recommended
2. **Create scripts/claude_agent.py** from template above
3. **Test in isolation** before integrating into `variance` script
4. **Update variance script** once confirmed working
5. **Document in README.md** and **HANDOFF.md**

---

## Questions?

- **Q: Can we keep both Gemini and Claude?**
  - A: Yes, add a `--claude` flag alongside `--gemini` for A/B testing

- **Q: What if Anthropic API is down?**
  - A: Fallback to TUI-only mode (`--tui`), or implement retry logic in claude_agent.py

- **Q: Can Claude access real-time market data?**
  - A: Not directly. Variance pre-fetches data, Claude analyzes the cached JSON.

- **Q: How do we update the persona over time?**
  - A: Edit `config/claude_persona.md` and re-run. No code changes needed.

