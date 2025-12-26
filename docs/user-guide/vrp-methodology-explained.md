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

## Quick Reference

**VRP Structural:**
```
VRP = IV / HV90 (quarterly baseline)
Threshold: 1.10 (10% markup minimum)
Rich: 1.30 (30% markup)
```

**VRP Tactical:**
```
VRP = IV / HV30 (monthly pulse)
For held positions only
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

**Last Updated:** 2025-12-26
**Maintained By:** Variance Development Team
