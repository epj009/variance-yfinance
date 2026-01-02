# RFC 018: Registry Pattern + Chain of Responsibility for Strategy Detection

| Status | IMPLEMENTED |
| :--- | :--- |
| **Author** | Variance (Quant Agent) |
| **Date** | 2025-12-23 |
| **Area** | Architecture / Complexity Reduction |
| **Complexity Targets** | `strategy_detector.py::identify_strategy()` (253 lines), `strategy_detector.py::map_strategy_to_id()` (103 lines) |

## 1. Problem Statement

### 1.1 `identify_strategy()` Analysis

The `identify_strategy()` function in `/Users/eric.johnson@verinext.com/Projects/variance-legacy provider/src/variance/strategy_detector.py` (lines 98-351) is a classification "mega-function":

| Metric | Current Value | Target |
|--------|--------------|--------|
| Lines of Code | 253 | < 30 (dispatcher) |
| Cyclomatic Complexity | ~15 | < 5 per classifier |
| If-Elif Branches | 15+ | Replaced by registry lookup |

### 1.2 `map_strategy_to_id()` Analysis

The `map_strategy_to_id()` function (lines 763-866) is a pure mapping function with 103 lines of nested if-elif:

| Metric | Current Value | Target |
|--------|--------------|--------|
| Lines of Code | 103 | < 20 (lookup table) |
| If-Elif Branches | 25+ | Static mapping dict |

### 1.3 Structural Issues

**`identify_strategy()` Problems:**
1. Single function tries to classify 20+ strategy types
2. Classification logic is order-dependent (multi-exp before single-exp)
3. Helper functions like `_butterfly_from_agg()` are inline closures
4. Adding a new strategy requires modifying the monolith

**`map_strategy_to_id()` Problems:**
1. Pure string matching with complex conditions
2. Duplicate logic (e.g., "call" in name_lower checks repeated)
3. Return values hardcoded, not validated against `strategies.json`

## 2. Proposed Solution

### 2.1 Registry Pattern (for `identify_strategy`)

Create a registry of "Strategy Classifiers" that can be queried in priority order:

```
+---------------------+
| StrategyClassifier  |  <-- ABC
+---------------------+
| + can_classify()    |
| + classify()        |
| + priority: int     |
+---------------------+
        ^
        |
+-------+-------+-------+-------+-------+
|       |       |       |       |       |
v       v       v       v       v       v
[Stock][SingleOpt][Covered][MultiExp][4Leg][3Leg][2Leg][Custom]
```

Each classifier handles ONE category of strategies.

### 2.2 Chain of Responsibility (for Classification)

Classifiers are chained by priority. First classifier that returns a non-null result wins:

```
legs: list[dict]
        |
        v
[StockClassifier] --> "Stock" or None
        |
        v (if None)
[SingleOptionClassifier] --> "Long Put" or None
        |
        v (if None)
[CoveredClassifier] --> "Covered Call" or None
        |
        v (if None)
[MultiExpClassifier] --> "Calendar Spread" or None
        |
        v (if None)
[FourLegClassifier] --> "Iron Condor" or None
        |
        v (if None)
[ThreeLegClassifier] --> "Jade Lizard" or None
        |
        v (if None)
[TwoLegClassifier] --> "Short Strangle" or None
        |
        v (if None)
[CustomClassifier] --> "Custom/Combo"
```

### 2.3 Static Mapping (for `map_strategy_to_id`)

Replace if-elif chain with a declarative mapping:

```python
STRATEGY_ID_MAP = {
    "short strangle": "short_strangle",
    "short straddle": "short_straddle",
    "iron condor": "iron_condor",
    "dynamic width iron condor": "dynamic_width_iron_condor",
    # ...
}

STRATEGY_ID_RULES = [
    # (pattern, requires_check, id_generator)
    ("vertical spread", lambda n, c: "call" in n and c < 0, "short_call_vertical_spread"),
    ("vertical spread", lambda n, c: "call" in n and c >= 0, "long_call_vertical_spread"),
    # ...
]
```

## 3. Technical Design

### 3.1 File Tree

```
src/variance/
├── classification/                  # NEW: Classification submodule
│   ├── __init__.py                  # Exports: classify_strategy, map_to_id
│   ├── registry.py                  # ClassifierRegistry
│   ├── base.py                      # StrategyClassifier ABC
│   ├── chain.py                     # ClassifierChain
│   ├── mapping.py                   # map_strategy_to_id() refactored
│   └── classifiers/                 # Individual classifiers
│       ├── __init__.py
│       ├── stock.py                 # StockClassifier
│       ├── single_option.py         # SingleOptionClassifier
│       ├── covered.py               # CoveredClassifier
│       ├── multi_exp.py             # MultiExpClassifier
│       ├── butterfly.py             # ButterflyClassifier (4-leg)
│       ├── condor.py                # CondorClassifier (4-leg)
│       ├── lizard.py                # LizardClassifier (3-leg)
│       ├── strangle.py              # StrangleClassifier (2-leg)
│       ├── vertical.py              # VerticalClassifier (2-leg)
│       ├── ratio.py                 # RatioClassifier (2-leg)
│       └── custom.py                # CustomClassifier (fallback)
├── strategy_detector.py             # MODIFIED: Thin wrapper
```

### 3.2 Interface Specifications

#### A. `StrategyClassifier` (Abstract Base Class)
```python
# Location: src/variance/classification/base.py
from abc import ABC, abstractmethod
from typing import Any, Optional

class StrategyClassifier(ABC):
    """Abstract base class for strategy classifiers."""

    _registry: dict[int, list[type["StrategyClassifier"]]] = {}

    # Override in subclasses
    priority: int = 100  # Lower = higher priority

    @classmethod
    def register(cls, priority: int):
        """Decorator to register classifiers by priority."""
        def decorator(classifier_cls: type["StrategyClassifier"]) -> type["StrategyClassifier"]:
            classifier_cls.priority = priority
            if priority not in cls._registry:
                cls._registry[priority] = []
            cls._registry[priority].append(classifier_cls)
            return classifier_cls
        return decorator

    @abstractmethod
    def can_classify(self, legs: list[dict[str, Any]], ctx: "ClassificationContext") -> bool:
        """Returns True if this classifier can handle the given legs."""
        pass

    @abstractmethod
    def classify(self, legs: list[dict[str, Any]], ctx: "ClassificationContext") -> str:
        """Returns the strategy name. Only called if can_classify() returns True."""
        pass
```

#### B. `ClassificationContext` (Shared State)
```python
# Location: src/variance/classification/base.py
from dataclasses import dataclass
from typing import Any

@dataclass
class ClassificationContext:
    """Pre-computed data shared across classifiers."""

    legs: list[dict[str, Any]]
    stock_legs: list[dict[str, Any]]
    option_legs: list[dict[str, Any]]

    call_legs: list[dict[str, Any]]
    put_legs: list[dict[str, Any]]

    long_calls: list[dict[str, Any]]
    short_calls: list[dict[str, Any]]
    long_puts: list[dict[str, Any]]
    short_puts: list[dict[str, Any]]

    long_call_qty: float
    short_call_qty: float
    long_put_qty: float
    short_put_qty: float

    long_call_strikes: list[float]
    short_call_strikes: list[float]
    long_put_strikes: list[float]
    short_put_strikes: list[float]

    is_multi_exp: bool
    underlying_price: float

    @classmethod
    def from_legs(cls, legs: list[dict[str, Any]]) -> "ClassificationContext":
        """Factory method to build context from raw legs."""
        # (All the extraction logic currently in identify_strategy, lines 114-164)
        pass
```

#### C. `ClassifierChain` (Chain of Responsibility)
```python
# Location: src/variance/classification/chain.py
from typing import Any, Optional
from .base import StrategyClassifier, ClassificationContext

class ClassifierChain:
    """Executes classifiers in priority order."""

    def __init__(self):
        self._chain: list[StrategyClassifier] = self._build_chain()

    def _build_chain(self) -> list[StrategyClassifier]:
        """Build the chain from registered classifiers, sorted by priority."""
        chain = []
        for priority in sorted(StrategyClassifier._registry.keys()):
            for cls in StrategyClassifier._registry[priority]:
                chain.append(cls())
        return chain

    def classify(self, legs: list[dict[str, Any]]) -> str:
        """
        Classify the given legs using the chain of classifiers.

        Returns the first successful classification, or "Custom/Combo" as fallback.
        """
        if not legs:
            return "Empty"

        ctx = ClassificationContext.from_legs(legs)

        for classifier in self._chain:
            if classifier.can_classify(legs, ctx):
                return classifier.classify(legs, ctx)

        return "Custom/Combo"
```

#### D. Example Classifiers

```python
# Location: src/variance/classification/classifiers/stock.py
from ..base import StrategyClassifier, ClassificationContext

@StrategyClassifier.register(priority=0)
class StockClassifier(StrategyClassifier):
    """Classifies single stock positions."""

    def can_classify(self, legs, ctx: ClassificationContext) -> bool:
        return len(legs) == 1 and len(ctx.stock_legs) == 1

    def classify(self, legs, ctx: ClassificationContext) -> str:
        return "Stock"
```

```python
# Location: src/variance/classification/classifiers/condor.py
from ..base import StrategyClassifier, ClassificationContext

@StrategyClassifier.register(priority=40)
class CondorClassifier(StrategyClassifier):
    """Classifies Iron Condors and Iron Flies."""

    def can_classify(self, legs, ctx: ClassificationContext) -> bool:
        if len(ctx.option_legs) != 4:
            return False
        if ctx.is_multi_exp:
            return False
        return (
            len(ctx.short_calls) == 1 and len(ctx.long_calls) == 1 and
            len(ctx.short_puts) == 1 and len(ctx.long_puts) == 1
        )

    def classify(self, legs, ctx: ClassificationContext) -> str:
        # Iron Fly check
        if ctx.short_call_strikes and ctx.short_put_strikes:
            if ctx.short_call_strikes[0] == ctx.short_put_strikes[0]:
                return "Iron Fly"

        # Dynamic Width check
        call_width = abs(ctx.long_call_strikes[0] - ctx.short_call_strikes[0])
        put_width = abs(ctx.short_put_strikes[0] - ctx.long_put_strikes[0])
        if call_width and put_width and call_width != put_width:
            return "Dynamic Width Iron Condor"

        return "Iron Condor"
```

#### E. `map_strategy_to_id()` Refactored

```python
# Location: src/variance/classification/mapping.py
from typing import Optional

# Static direct mappings (no conditions)
DIRECT_MAP: dict[str, str] = {
    "short strangle": "short_strangle",
    "strangle": "short_strangle",
    "short straddle": "short_straddle",
    "straddle": "short_straddle",
    "iron condor": "iron_condor",
    "dynamic width iron condor": "dynamic_width_iron_condor",
    "iron fly": "iron_fly",
    "iron butterfly": "iron_fly",
    "covered call": "covered_call",
    "covered put": "covered_put",
    "short call": "short_naked_call",
    "short put": "short_naked_put",
    "jade lizard": "jade_lizard",
    "big lizard": "big_lizard",
    "reverse jade lizard": "reverse_jade_lizard",
    "twisted sister": "reverse_jade_lizard",
    "reverse big lizard": "reverse_big_lizard",
    "call zebra": "call_zebra",
    "put zebra": "put_zebra",
    "call butterfly": "call_butterfly",
    "put butterfly": "put_butterfly",
    "call broken wing butterfly": "call_broken_wing_butterfly",
    "put broken wing butterfly": "put_broken_wing_butterfly",
    "call broken heart butterfly": "call_broken_heart_butterfly",
    "put broken heart butterfly": "put_broken_heart_butterfly",
    "call calendar spread": "call_calendar_spread",
    "put calendar spread": "put_calendar_spread",
    "poor man's covered call": "poor_mans_covered_call",
    "poor mans covered call": "poor_mans_covered_call",
    "poor man's covered put": "poor_mans_covered_put",
    "poor mans covered put": "poor_mans_covered_put",
}

# Conditional mappings (require net_cost check)
CONDITIONAL_RULES: list[tuple[str, callable, str]] = [
    # (pattern, condition(name, net_cost) -> bool, strategy_id)
    ("vertical spread", lambda n, c: "call" in n and c < 0, "short_call_vertical_spread"),
    ("vertical spread", lambda n, c: "call" in n and c >= 0, "long_call_vertical_spread"),
    ("vertical spread", lambda n, c: "put" in n and c < 0, "short_put_vertical_spread"),
    ("vertical spread", lambda n, c: "put" in n and c >= 0, "long_put_vertical_spread"),
    ("front-ratio", lambda n, c: "call" in n, "call_front_ratio_spread"),
    ("front ratio", lambda n, c: "call" in n, "call_front_ratio_spread"),
    ("ratio spread", lambda n, c: "call" in n, "call_front_ratio_spread"),
    ("front-ratio", lambda n, c: "put" in n, "put_front_ratio_spread"),
    ("front ratio", lambda n, c: "put" in n, "put_front_ratio_spread"),
    ("ratio spread", lambda n, c: "put" in n, "put_front_ratio_spread"),
    ("double diagonal", lambda n, c: c < 0, "double_diagonal"),
    ("diagonal spread", lambda n, c: c < 0, "double_diagonal"),
]


def map_strategy_to_id(name: str, net_cost: float) -> Optional[str]:
    """
    Maps strategy name to strategy ID using declarative lookups.

    Refactored from 103-line if-elif chain to table-driven approach.
    """
    name_lower = name.lower()

    # 1. Direct lookup (most common case)
    if name_lower in DIRECT_MAP:
        return DIRECT_MAP[name_lower]

    # 2. Partial match with conditions
    for pattern, condition, strategy_id in CONDITIONAL_RULES:
        if pattern in name_lower and condition(name_lower, net_cost):
            return strategy_id

    # 3. Fallback patterns
    if "back spread" in name_lower or ("ratio" in name_lower and "backspread" in name_lower):
        return "back_spread"

    return None
```

### 3.3 Modified `identify_strategy()` (Thin Wrapper)

```python
# Location: src/variance/strategy_detector.py (MODIFIED)

from .classification import ClassifierChain

# Module-level chain (singleton)
_classifier_chain: ClassifierChain = None

def _get_chain() -> ClassifierChain:
    global _classifier_chain
    if _classifier_chain is None:
        _classifier_chain = ClassifierChain()
    return _classifier_chain

def identify_strategy(legs: list[dict[str, Any]]) -> str:
    """
    Identify the option strategy based on a list of position legs.

    This function is now a thin wrapper around ClassifierChain.
    """
    return _get_chain().classify(legs)
```

## 4. Classifier Priority Matrix

| Priority | Classifier | Strategies | Condition |
|----------|-----------|------------|-----------|
| 0 | StockClassifier | Stock | Single stock leg |
| 10 | SingleOptionClassifier | Long/Short Call/Put | Single option leg |
| 20 | CoveredClassifier | Covered Call/Put/Strangle, Collar | Stock + options |
| 30 | MultiExpClassifier | Calendar, Diagonal, PMCC/PMCP | Multiple expirations |
| 40 | CondorClassifier | Iron Condor, Iron Fly, DWIC | 4-leg same-exp |
| 50 | ButterflyClassifier | Butterfly, BWB, BHB | 4-leg with ratios |
| 60 | LizardClassifier | Jade/Big/Reverse Lizard | 3-leg |
| 70 | RatioClassifier | ZEBRA, Front-Ratio | 2-leg with qty mismatch |
| 80 | VerticalClassifier | Vertical Spread | 2-leg same type |
| 90 | StrangleClassifier | Strangle, Straddle | 2-leg short C/P |
| 100 | CustomClassifier | Custom/Combo | Fallback |

## 5. Benefits & Trade-offs

### 5.1 Benefits

| Benefit | Description |
|---------|-------------|
| **Testability** | Each classifier tested independently |
| **Extensibility** | New strategies via `@register(priority=N)` |
| **Readability** | Each classifier ~30 lines |
| **Maintainability** | Classification logic decoupled |
| **Performance** | Short-circuit on first match |
| **Declarative** | `map_strategy_to_id` now a lookup table |

### 5.2 Trade-offs

| Trade-off | Mitigation |
|-----------|------------|
| More files | Logical grouping in `classifiers/` |
| Registry complexity | Clear priority ordering |
| Context overhead | One-time computation, reused |

## 6. Migration Strategy

### Phase 1: Extract Context (0.5 days)
1. Create `ClassificationContext` with all pre-computed data
2. Verify extraction matches current lines 114-164

### Phase 2: Create Classifiers (1.5 days)
1. Create one classifier per strategy category
2. Port logic from corresponding if-elif blocks
3. Unit test each classifier

### Phase 3: Wire Up Chain (0.5 days)
1. Create `ClassifierChain`
2. Replace `identify_strategy()` body
3. Run regression tests

### Phase 4: Refactor Mapping (0.5 days)
1. Create `DIRECT_MAP` and `CONDITIONAL_RULES`
2. Replace `map_strategy_to_id()` body
3. Verify all IDs match `strategies.json`

## 7. Testing Strategy

### 7.1 Unit Tests (Per Classifier)
```python
# tests/classification/test_condor_classifier.py
def test_identifies_iron_condor():
    legs = [
        {"Call/Put": "Call", "Quantity": "-1", "Strike Price": "100"},
        {"Call/Put": "Call", "Quantity": "1", "Strike Price": "105"},
        {"Call/Put": "Put", "Quantity": "-1", "Strike Price": "95"},
        {"Call/Put": "Put", "Quantity": "1", "Strike Price": "90"},
    ]
    classifier = CondorClassifier()
    ctx = ClassificationContext.from_legs(legs)
    assert classifier.can_classify(legs, ctx)
    assert classifier.classify(legs, ctx) == "Iron Condor"
```

### 7.2 Mapping Tests
```python
# tests/classification/test_mapping.py
def test_direct_mapping():
    assert map_strategy_to_id("Short Strangle", -100) == "short_strangle"
    assert map_strategy_to_id("Iron Condor", -200) == "iron_condor"

def test_conditional_mapping():
    assert map_strategy_to_id("Vertical Spread (Call)", -50) == "short_call_vertical_spread"
    assert map_strategy_to_id("Vertical Spread (Call)", 50) == "long_call_vertical_spread"
```

### 7.3 Regression Tests
```python
# tests/classification/test_regression.py
KNOWN_STRATEGIES = [
    ([], "Empty"),
    ([stock_leg], "Stock"),
    ([short_call, short_put], "Short Strangle"),
    ([short_call, long_call, short_put, long_put], "Iron Condor"),
    # ... (full matrix from current tests)
]

@pytest.mark.parametrize("legs,expected", KNOWN_STRATEGIES)
def test_classification_matches_legacy(legs, expected):
    assert identify_strategy(legs) == expected
```

## 8. Status
**Proposed.** Ready for Developer implementation upon approval.
