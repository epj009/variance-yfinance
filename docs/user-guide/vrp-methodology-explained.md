# VRP Methodology Explained (For Users)

**Purpose:** Understand how Variance measures the edge in options selling

**TL;DR:** We use ratio (IV/HV) not spread (IV-HV), and we measure ATM IV even though we trade OTM. Both are mathematically sound for retail options selling.

---

## The Two Big Questions

### Q1: Why Ratio (IV/HV) Instead of Spread (IV-HV)?

**Simple Answer:** Because credit scales with volatility.

**Example:**

Imagine two stocks:

**Stock A (Low Vol):**
- IV = 12%, HV = 10%
- Sell strangle → Collect $1.00

**Stock B (High Vol):**
- IV = 52%, HV = 50%
- Sell strangle → Collect $5.00

**Using Spread:**
- Stock A: IV - HV = 12 - 10 = 2 points
- Stock B: IV - HV = 52 - 50 = 2 points
- **Conclusion: Both have same edge** ❌ Wrong!

**Using Ratio:**
- Stock A: IV/HV = 12/10 = 1.20 (20% markup)
- Stock B: IV/HV = 52/50 = 1.04 (4% markup)
- **Conclusion: Stock A has 5x better relative edge** ✅ Correct!

**Why?**
- You collect $1.00 on Stock A with $10 of risk → 10% edge
- You collect $5.00 on Stock B with $50 of risk → 10% edge (same!)
- Wait, but Stock A has 20% markup and Stock B has 4%?

The key insight: **Risk also scales with vol.**

When vol is higher:
- You collect MORE premium ✓
- But the stock moves MORE too (more risk) ✗
- **Edge is the percentage markup, not absolute dollars**

---

### Q2: Why Measure ATM When We Trade OTM?

**Simple Answer:** Because ATM drives the entire options chain.

**The Seeming Mismatch:**
- **We measure:** ATM IV (50-delta, at the money)
- **We trade:** 20-30 delta strangles (out of the money)

**Why This Works:**

Think of the options chain like a solar system:
- **ATM is the sun** (center of gravity)
- **OTM strikes are planets** (orbit around ATM)
- When the sun moves, all planets move too

**Example:**

| Environment | ATM IV | 25-delta Put | 25-delta Call | Skew |
|-------------|--------|--------------|---------------|------|
| **Normal** | 15% | 18% (+3) | 13% (-2) | 5 points |
| **Spike** | 30% | 33% (+3) | 28% (-2) | 5 points |

Notice: **Skew stays ~5 points**. When ATM jumps from 15% to 30%, EVERYTHING jumps.

**If ATM is rich, the wings are also rich.**

**The Math:**

When you sell a strangle (both sides):

```
Wing IV = (Put IV + Call IV) / 2
        = (ATM + 3pts) + (ATM - 2pts) / 2
        = ATM + 0.5pts
        ≈ ATM
```

**Skew cancels out** when you average both wings!

---

## Why This Matters

### For Screening

**Goal:** "Find stocks where options are overpriced"

If we measured only put IV, we'd miss call edge.
If we measured only wing IV, we'd get the same result as ATM (skew cancels).

**ATM is the simplest, most robust measure of overall richness.**

### For Tastylive/Spina Methodology

The strategy is:
1. **Mechanical** - Always sell 20-30 delta (no strike optimization)
2. **Delta-neutral** - Balanced structures (strangles, condors)
3. **VRP-based** - Trade when IV > HV across the board

**We don't optimize skew. We screen stocks.**

---

## The Two-Stage Screening Funnel

**This is the core philosophy of Variance screening.**

Variance uses a two-stage filter to find trade candidates:

```
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 1: VRP STRUCTURAL (Historical Edge)                     │
│  ──────────────────────────────────────────                     │
│  Formula: IV / HV90                                             │
│  Threshold: > 1.10                                              │
│                                                                 │
│  Question: "Has there been a persistent premium in this name?"  │
│                                                                 │
│  Looks at 90 days of realized volatility. If IV has exceeded   │
│  what actually happened over the quarter, there's been edge    │
│  to collect.                                                    │
│                                                                 │
│  Pass = "Options have been priced rich vs quarterly realized"  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 2: VRP TACTICAL (Current Edge)                          │
│  ─────────────────────────────────────                          │
│  Formula: IV / HV30                                             │
│  Threshold: > 1.15                                              │
│                                                                 │
│  Question: "Does that edge still exist TODAY?"                  │
│                                                                 │
│  Looks at 30 days of realized volatility. If recent movement   │
│  has caught up to IV, the edge may have evaporated.            │
│                                                                 │
│  Pass = "Current IV still exceeds recent realized movement"    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                      [Trade Candidate]
```

### Why Two Stages?

**Tactical catches when reality catches up to pricing.**

| HV90 | HV30 | IV | Structural | Tactical | What's Happening |
|------|------|-----|-----------|----------|------------------|
| 20% | 18% | 28% | 1.40 ✅ | 1.56 ✅ | Options rich, vol stable → **Edge exists** |
| 20% | 35% | 30% | 1.50 ✅ | 0.86 ❌ | Options looked rich, but stock got volatile → **Edge gone** |
| 20% | 25% | 28% | 1.40 ✅ | 1.12 ⚠️ | Vol rising, edge shrinking → **Caution** |
| 25% | 20% | 22% | 0.88 ❌ | 1.10 ⚠️ | No historical edge, slight current edge → **Skip** |

**Row 2 is the key insight:**

Structural says "historically, options were priced rich." But Tactical says "the stock is NOW moving enough to justify that pricing." The 30-day realized vol caught up to IV—the edge evaporated.

**Row 4 is the trap to avoid:**

IV looks slightly elevated vs recent vol, but historically there's been no persistent premium. Chasing this signal is less reliable.

### What Each Stage Actually Proves

| Stage | What It Proves | What It Does NOT Prove |
|-------|---------------|------------------------|
| **Structural** | Options have been priced above quarterly realized vol | That IV will compress (mean reversion) |
| **Tactical** | Current IV exceeds recent realized movement | That the edge will persist |
| **Both passing** | There was edge AND it still exists today | Future profitability (requires backtesting) |

**Important:** These metrics identify statistical edge based on IV > HV. They do NOT guarantee mean reversion or profitability. The approach is grounded in academic research (Carr & Wu, AQR, Tastytrade) but should be validated with your own backtesting.

### The Mental Model

Think of it like a job candidate:

| Stage | Analogy | VRP Equivalent |
|-------|---------|----------------|
| **Structural** | "Has this person performed well historically?" | "Have options been priced rich over the quarter?" |
| **Tactical** | "Are they still performing well now?" | "Does that edge still exist today?" |

You want BOTH: historical track record AND current availability of edge.

### Threshold Tuning

You can adjust thresholds in `config/trading_rules.json`:

```json
{
  "vrp_structural_threshold": 1.10,   // Baseline: 10% markup minimum
  "vrp_tactical_threshold": 1.15      // Current: 15% markup minimum
}
```

**More selective (spike hunting):**
```json
{
  "vrp_structural_threshold": 1.15,
  "vrp_tactical_threshold": 1.30      // Only trade vol spikes
}
```

**Wider net (more candidates):**
```json
{
  "vrp_structural_threshold": 1.10,
  "vrp_tactical_threshold": 1.10      // Accept thinner edge
}
```

---

## Compression Ratio (Volatility Momentum)

**Formula:** HV30 / HV90

This ratio tells us whether realized volatility is **compressed** (coiling) or **expanded** relative to its longer-term baseline. This matters because Variance is a **short volatility** strategy.

**Interpretation (short vol):**
- **< 0.60:** Severe compression → avoid (expansion risk)
- **0.60-0.75:** Mild compression → caution, downgrade conviction
- **0.75-1.15:** Normal regime → standard entries
- **1.15-1.30:** Mild expansion → favorable for short vol
- **> 1.30:** Severe expansion → strongest short vol edge (contraction expected)

**Why it flips vs long vol:** If volatility is already compressed, the odds favor expansion, which is bad for short gamma. Elevated volatility tends to mean-revert down, which is ideal for short premium.

---

## Common Concerns Addressed

### "But academic VRP is IV - HV!"

**True, but:**
- Academic VRP is for **variance swap pricing** (institutional product)
- We're doing **options selling** (retail strategy)
- Different tools for different jobs

**Analogy:**
- Academic VRP = measuring temperature in Kelvin (for science)
- Our VRP ratio = measuring temperature in Fahrenheit (for daily life)
- Both are valid, one is more practical for your use case

### "But I read that VRP is concentrated in OTM puts!"

**Also true, but:**
- That's for **directional put selling** (skew arbitrage)
- We do **delta-neutral strangles** (both sides)
- When you sell both wings, skew effects cancel

**If you ONLY sold puts:**
- Yes, you'd want to measure 25-delta put IV specifically

**But we sell strangles:**
- Put side: Higher IV than ATM (+3pts from skew)
- Call side: Lower IV than ATM (-2pts from skew)
- Average: ≈ ATM IV

### "Isn't this just curve-fitting to make the numbers work?"

**No, here's why:**

1. **Ratio math is fundamental**
   - Credit scaling with vol is a mathematical fact
   - Not a parameter we tuned

2. **Skew cancellation is provable**
   - (ATM+3 + ATM-2)/2 = ATM+0.5
   - Not an empirical observation, it's algebra

3. **Industry standard**
   - Market makers use ratio language ("1.2x realized")
   - Tastylive uses IV vs HV comparisons (ratios)
   - This isn't our invention

---

## The Bottom Line

**For retail options selling with delta-neutral strategies:**

✅ **VRP Ratio (IV/HV)** is the correct metric
- Normalizes across vol levels
- Aligns with credit collected
- Industry standard

✅ **ATM IV** is the correct measurement
- Anchors the entire surface
- Skew cancels for balanced trades
- Simplest and most robust

**These aren't compromises or approximations. They're the mathematically sound approach for our use case.**

---

## Want to Go Deeper?

**Technical Documentation:**
- `docs/adr/0012-vrp-measurement-methodology.md` - Full mathematical analysis
- `docs/analysis/vrp-ratio-vs-spread-analysis.md` - Deep dive on ratio vs spread
- `docs/analysis/skew-risk-analysis.md` - Proof of skew cancellation

**Code References:**
- `src/variance/get_market_data.py` - VRP calculation (line 944)
- `src/variance/get_market_data.py` - ATM IV measurement (line 340)

**User Playbook:**
- `docs/QUANT_PLAYBOOK.md` - Section 2.6-2.7 (Why Ratio? Why ATM?)

---

## Open Questions (Revisit After Live Trading)

### Is the Dual VRP Filter Necessary?

**Current Design:** Candidates must pass BOTH VRP Structural AND VRP Tactical.

**The Question:** If VRP Tactical (IV/HV30) shows edge exists today, and IV Percentile confirms IV is elevated, do we actually need VRP Structural (IV/HV90)?

**Arguments for keeping both:**

| Scenario | HV90 | HV30 | IV | Structural | Tactical | Risk |
|----------|------|------|-----|-----------|----------|------|
| Recent vol spike | 20% | 28% | 30% | 1.50 ✅ | 1.07 ❌ | Tactical catches edge erosion |
| Temporary calm | 28% | 18% | 30% | 1.07 ❌ | 1.67 ✅ | Structural catches temporary lull |

- Structural provides "regression to mean" protection
- If HV30 is temporarily low, Structural asks "is this normal for this stock?"
- Requiring both ensures edge existed AND still exists

**Arguments for simplifying to Tactical + IVP only:**

- Both filters use CURRENT IV (only HV lookback differs)
- If edge exists now (Tactical), historical persistence may not matter
- IVP partially covers the "is IV elevated?" question
- Simpler filter = easier to understand and tune

**Decision (January 2026):** Keep dual filter, trade with it, evaluate empirically.

**Evaluation Criteria:**
- Are good candidates being rejected by Structural that pass Tactical + IVP?
- When Structural and Tactical diverge, which signal is more predictive?
- Does win rate differ for Structural-only vs Tactical-only passes?

**To revisit:** After 3-6 months of live trading, analyze rejected candidates and trade outcomes.

---

## Quick Reference

**VRP Structural (Stage 1 - Historical Edge):**
```
VRP = IV / HV90 (quarterly baseline)
Question: "Has there been a persistent premium in this name?"
Threshold: 1.10 (10% markup minimum)
Rich: 1.30+ (high conviction)
```

**VRP Tactical (Stage 2 - Current Edge):**
```
VRP = IV / HV30 (monthly pulse)
Question: "Does that edge still exist TODAY?"
Threshold: 1.15 (15% markup minimum)
Also used for position management (harvest timing, defense triggers)
```

**What These Metrics Prove:**
```
✅ IV has exceeded realized vol (statistical edge exists)
❌ IV will compress in the future (mean reversion)
❌ The trade will be profitable (requires backtesting)
```

**IV Measurement:**
```
IV = (ATM_call_IV + ATM_put_IV) / 2
Closest strike to current price
30-day expiration preferred
```

**HV Floor:**
```
All VRP calculations: max(HV, 5%)
Prevents ratio explosion on dead vol stocks
```

---

**Last Updated:** 2026-01-04
**Maintained By:** Variance Development Team
