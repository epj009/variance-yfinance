# RFC 016: Chain of Responsibility for Triage Engine

| Status | IMPLEMENTED |
| :--- | :--- |
| **Author** | Variance (Quant Agent) |
| **Date** | 2025-12-23 |
| **Area** | Architecture / Complexity Reduction |
| **Complexity Target** | `triage_engine.py::determine_cluster_action()` (200 lines, 5+ nesting, 30+ branches) |

## 1. Problem Statement

### 1.1 Current State Analysis

The `determine_cluster_action()` function in `/Users/eric.johnson@verinext.com/Projects/variance-yfinance/src/variance/triage_engine.py` (lines 349-548) exhibits the following complexity demons:

| Metric | Current Value | Target |
|--------|--------------|--------|
| Lines of Code | 200 | < 50 (orchestrator) |
| Cyclomatic Complexity | ~30 | < 10 per handler |
| Nesting Depth | 5 levels | 2 levels max |
| Condition Branches | 30+ if/elif | Single responsibility per handler |

### 1.2 Structural Issues

```
Current Flow (Monolithic):
determine_cluster_action(metrics, context)
    |
    +-- [0] Expiration Day Check (DTE == 0)
    +-- [1] Harvest Logic (Delegated to strategy_obj)
    +-- [1.5] Size Threat Check (Tail Risk)
    +-- [2] Defense Logic (is_tested & low DTE)
    +-- [3] Gamma Zone Logic (< 21 DTE)
    +-- [4] Hedge Detection
    +-- [4.5] Hedge Check (Dead Money)
    +-- [5] Toxic Theta Check
    +-- [6] Earnings Check (Binary Event)
    +-- [7] VRP Momentum (SCALABLE)
    +-- [FINALIZE] Build TriageResult
```

**Problem:** Each check has priority-based short-circuiting (`if not cmd`), creating implicit ordering dependencies and 30+ condition evaluations.

### 1.3 Violation of SOLID Principles

- **SRP Violation:** Function handles 8+ distinct responsibilities.
- **OCP Violation:** Adding a new action requires modifying the monolithic function.
- **DIP Violation:** High-level triage logic depends on low-level condition details.

## 2. Proposed Solution: Chain of Responsibility Pattern

### 2.1 Pattern Overview

The Chain of Responsibility pattern decouples senders from receivers by allowing multiple handlers to process a request sequentially. Each handler either processes the request or passes it to the next handler.

```
    TriageRequest
         |
         v
+------------------+     +------------------+     +------------------+
| ExpirationHandler| --> | HarvestHandler   | --> | SizeThreatHandler|
+------------------+     +------------------+     +------------------+
         |                       |                       |
         v                       v                       v
+------------------+     +------------------+     +------------------+
| DefenseHandler   | --> | GammaHandler     | --> | HedgeHandler     |
+------------------+     +------------------+     +------------------+
         |                       |                       |
         v                       v                       v
+------------------+     +------------------+     +------------------+
| ToxicThetaHandler| --> | EarningsHandler  | --> | ScalableHandler  |
+------------------+     +------------------+     +------------------+
         |
         v
   TriageResult
```

### 2.2 Key Design Decisions

1. **Immutable Request Object:** `TriageRequest` is a frozen dataclass containing metrics + context.
2. **Priority-Based Ordering:** Handlers are ordered by priority for consistent tag ordering in output.
3. **Collector Semantics:** Each handler checks conditions and adds tags. ALL handlers execute (no early exit).
4. **Multi-Tag System:** Positions can have multiple tags simultaneously (HARVEST + GAMMA + EARNINGS_WARNING).
5. **Registry Pattern:** Handlers register via `@TriageHandler.register(priority=N)`.

## 3. Technical Design

### 3.1 Class Diagram

```
+----------------------+          +----------------------+
|   TriageRequest      |          |   TriageHandler      |
+----------------------+          +----------------------+
| + metrics: dict      |<>------->| + handle(request)    |
| + context: dict      |          | + set_next(handler)  |
| + tags: tuple[Tag,...]|         | # _next: Handler?    |
+----------------------+          +----------------------+
                                           ^
                                           |
          +--------------------------------+--------------------------------+
          |                |               |               |               |
+-----------------+ +-----------------+ +-----------------+ +-----------------+
|ExpirationHandler| |HarvestHandler   | |SizeThreatHandler| |DefenseHandler   |
+-----------------+ +-----------------+ +-----------------+ +-----------------+
| priority: 0     | | priority: 10    | | priority: 20    | | priority: 30    |
| handle()        | | handle()        | | handle()        | | handle()        |
+-----------------+ +-----------------+ +-----------------+ +-----------------+
```

### 3.2 File Tree

```
src/variance/
├── triage/                          # NEW: Triage submodule
│   ├── __init__.py                  # Exports: TriageChain, TriageRequest
│   ├── request.py                   # TriageRequest dataclass
│   ├── handler.py                   # TriageHandler ABC + registry
│   ├── chain.py                     # TriageChain builder
│   └── handlers/                    # Individual handlers
│       ├── __init__.py
│       ├── expiration.py            # @register(priority=0)
│       ├── harvest.py               # @register(priority=10)
│       ├── size_threat.py           # @register(priority=20)
│       ├── defense.py               # @register(priority=30)
│       ├── gamma.py                 # @register(priority=40)
│       ├── hedge.py                 # @register(priority=50)
│       ├── toxic_theta.py           # @register(priority=60)
│       ├── earnings.py              # @register(priority=70)
│       └── scalable.py              # @register(priority=80)
├── triage_engine.py                 # MODIFIED: Thin orchestrator
```

### 3.3 Interface Specifications

#### A. `TriageRequest` (Immutable Data Object)
```python
# Location: src/variance/triage/request.py
from dataclasses import dataclass
from typing import Any, Optional
from ..models.actions import ActionCommand, TriageTag

@dataclass(frozen=True)
class TriageTag:
    """A single triage tag applied to a position."""
    tag_type: str  # "HARVEST", "GAMMA", "EARNINGS_WARNING", etc.
    priority: int  # Lower = more urgent
    logic: str     # Human-readable reason
    action_cmd: Optional[ActionCommand] = None  # Optional actionable command

@dataclass(frozen=True)
class TriageRequest:
    """Immutable request object passed through the triage chain."""

    # Cluster Metrics (from calculate_cluster_metrics)
    root: str
    strategy_name: str
    strategy_id: Optional[str]
    dte: int
    net_pl: float
    net_cost: float
    strategy_delta: float
    strategy_gamma: float
    pl_pct: Optional[float]
    days_held: int
    price: float
    legs: tuple[dict[str, Any], ...]  # Immutable tuple

    # Market Context
    vrp_structural: Optional[float]
    vrp_tactical: Optional[float]
    is_stale: bool
    sector: str
    earnings_date: Optional[str]

    # Portfolio Context
    portfolio_beta_delta: float
    net_liquidity: float

    # Strategy Object (for delegation)
    strategy_obj: Any  # BaseStrategy instance

    # Multi-Tag System (collector pattern)
    tags: tuple[TriageTag, ...] = ()

    def with_tag(self, tag: TriageTag) -> "TriageRequest":
        """Returns a new request with an additional tag."""
        return TriageRequest(**{**self.__dict__, "tags": self.tags + (tag,)})

    @property
    def primary_action(self) -> Optional[TriageTag]:
        """Returns the highest-priority tag (lowest priority number)."""
        if not self.tags:
            return None
        return min(self.tags, key=lambda t: t.priority)
```

#### B. `TriageHandler` (Abstract Base Class)
```python
# Location: src/variance/triage/handler.py
from abc import ABC, abstractmethod
from typing import Optional, ClassVar
from .request import TriageRequest

class TriageHandler(ABC):
    """Abstract handler in the Chain of Responsibility."""

    _registry: ClassVar[dict[int, type["TriageHandler"]]] = {}
    _next: Optional["TriageHandler"] = None

    @classmethod
    def register(cls, priority: int):
        """Decorator to register handlers by priority."""
        def decorator(handler_cls: type["TriageHandler"]) -> type["TriageHandler"]:
            cls._registry[priority] = handler_cls
            return handler_cls
        return decorator

    def set_next(self, handler: "TriageHandler") -> "TriageHandler":
        """Sets the next handler in the chain. Returns the next handler for chaining."""
        self._next = handler
        return handler

    @abstractmethod
    def handle(self, request: TriageRequest) -> TriageRequest:
        """
        Process the request and add tags if conditions match.

        IMPORTANT: This is a COLLECTOR pattern - always pass to next handler.
        Do NOT short-circuit. Positions can have multiple tags.
        """
        pass

    def _pass_to_next(self, request: TriageRequest) -> TriageRequest:
        """ALWAYS pass request to next handler (collector pattern)."""
        if self._next:
            return self._next.handle(request)
        return request
```

#### C. `TriageChain` (Builder/Orchestrator)
```python
# Location: src/variance/triage/chain.py
from typing import Optional
from .handler import TriageHandler
from .request import TriageRequest

class TriageChain:
    """Builds and executes the triage handler chain."""

    def __init__(self, rules: dict):
        self.rules = rules
        self._head: Optional[TriageHandler] = None
        self._build_chain()

    def _build_chain(self) -> None:
        """Builds the chain from registered handlers, sorted by priority."""
        sorted_priorities = sorted(TriageHandler._registry.keys())

        handlers = [TriageHandler._registry[p](self.rules) for p in sorted_priorities]

        if not handlers:
            return

        self._head = handlers[0]
        current = self._head
        for handler in handlers[1:]:
            current = current.set_next(handler)

    def triage(self, request: TriageRequest) -> TriageRequest:
        """Execute the chain and return the final request with cmd populated."""
        if self._head:
            return self._head.handle(request)
        return request
```

#### D. Example Handler: `HarvestHandler`
```python
# Location: src/variance/triage/handlers/harvest.py
from ..handler import TriageHandler
from ..request import TriageRequest, TriageTag

@TriageHandler.register(priority=10)
class HarvestHandler(TriageHandler):
    """Handles profit harvesting logic."""

    def __init__(self, rules: dict):
        self.rules = rules

    def handle(self, request: TriageRequest) -> TriageRequest:
        # Only check credit positions
        if request.net_cost >= 0:
            return self._pass_to_next(request)

        if request.pl_pct is None:
            return self._pass_to_next(request)

        # Delegate to strategy object
        cmd = request.strategy_obj.check_harvest(
            request.root,
            request.pl_pct,
            request.days_held
        )

        if cmd:
            # Add HARVEST tag
            tag = TriageTag(
                tag_type="HARVEST",
                priority=10,
                logic=f"Profit target hit: {request.pl_pct:.1%}",
                action_cmd=cmd
            )
            request = request.with_tag(tag)

        # ALWAYS pass to next (collector pattern)
        return self._pass_to_next(request)
```

#### E. Example Handler: `GammaHandler`
```python
# Location: src/variance/triage/handlers/gamma.py
from ..handler import TriageHandler
from ..request import TriageRequest, TriageTag

@TriageHandler.register(priority=40)
class GammaHandler(TriageHandler):
    """Detects gamma zone positions (not tested, approaching expiration)."""

    def __init__(self, rules: dict):
        self.rules = rules

    def handle(self, request: TriageRequest) -> TriageRequest:
        gamma_trigger = self.rules.get("gamma_trigger_dte", 21)

        # Check if in gamma zone
        if request.dte >= gamma_trigger:
            return self._pass_to_next(request)

        # Skip if already tested (that's DEFENSE territory)
        if self._is_tested(request):
            return self._pass_to_next(request)

        # Add GAMMA tag
        tag = TriageTag(
            tag_type="GAMMA",
            priority=40,
            logic=f"Entering gamma zone: {request.dte} DTE",
            action_cmd=None  # Informational tag
        )
        request = request.with_tag(tag)

        return self._pass_to_next(request)

    def _is_tested(self, request: TriageRequest) -> bool:
        """Check if position is tested (underlying through short strikes)."""
        # (Implementation from current code)
        pass
```

### 3.4 Modified `determine_cluster_action()` (Thin Orchestrator)

```python
# Location: src/variance/triage_engine.py (MODIFIED)

from .triage import TriageChain, TriageRequest

def determine_cluster_action(metrics: dict[str, Any], context: TriageContext) -> TriageResult:
    """
    Step 2 of Triage: Determine Action Code using Chain of Responsibility.

    This function is now a thin orchestrator that:
    1. Builds the TriageRequest from metrics/context
    2. Runs the handler chain
    3. Converts the result to TriageResult
    """
    # Build immutable request
    request = _build_triage_request(metrics, context)

    # Execute chain
    chain = TriageChain(context["rules"])
    result = chain.triage(request)

    # Convert to TriageResult (backward compatibility)
    return _build_triage_result(result, context)


def _build_triage_request(metrics: dict, context: TriageContext) -> TriageRequest:
    """Factory function to build TriageRequest from legacy structures."""
    # ... (extraction logic, ~30 lines)
    pass


def _build_triage_result(request: TriageRequest, context: TriageContext) -> TriageResult:
    """Converts the final request back to TriageResult with multi-tag support."""
    primary = request.primary_action

    return {
        "root": request.root,
        "strategy_name": request.strategy_name,
        "price": request.price,
        "is_stale": request.is_stale,
        "vrp_structural": request.vrp_structural,
        # ... (remaining fields)

        # Primary action (highest priority tag for TUI display)
        "action_code": primary.tag_type if primary else None,
        "logic": primary.logic if primary else "",

        # NEW: All tags for comprehensive analysis
        "tags": [
            {
                "type": tag.tag_type,
                "priority": tag.priority,
                "logic": tag.logic,
                "actionable": tag.action_cmd is not None
            }
            for tag in request.tags
        ],
    }
```

## 4. Data Flow Diagram (Collector Pattern)

```
calculate_cluster_metrics(legs, context)
              |
              v
+---------------------------+
|     TriageRequest         |
| (tags = [])               |
+---------------------------+
              |
              v
+---------------------------+
|     TriageChain.triage()  |
+---------------------------+
              |
              v
      [ExpirationHandler] --> tags = [EXPIRING?]
              |
              v
      [HarvestHandler]    --> tags = [EXPIRING?, HARVEST?]
              |
              v
      [SizeThreatHandler] --> tags = [EXPIRING?, HARVEST?, SIZE_THREAT?]
              |
              v
      [DefenseHandler]    --> tags = [EXPIRING?, HARVEST?, SIZE_THREAT?, DEFENSE?]
              |
              v
      [GammaHandler]      --> tags = [EXPIRING?, HARVEST?, SIZE_THREAT?, DEFENSE?, GAMMA?]
              |
              v
      [HedgeHandler]      --> tags = [..., HEDGE_CHECK?]
              |
              v
      [ToxicThetaHandler] --> tags = [..., TOXIC?]
              |
              v
      [EarningsHandler]   --> tags = [..., EARNINGS_WARNING?]
              |
              v
      [ScalableHandler]   --> tags = [..., SCALABLE?]
              |
              v
+---------------------------+
|   TriageRequest.tags      |
| (All applicable tags)     |
+---------------------------+
              |
              v
+---------------------------+
|   _build_triage_result()  |
| - primary_action (min priority)
| - all_tags (comprehensive)
+---------------------------+
              |
              v
      TriageResult (dict)
      {
        "action_code": "HARVEST",  # Primary
        "tags": [
          {"type": "HARVEST", "priority": 10},
          {"type": "GAMMA", "priority": 40},
          {"type": "EARNINGS_WARNING", "priority": 70}
        ]
      }
```

## 5. Handler Priority Matrix (Multi-Tag System)

| Priority | Handler | Tag Type | Condition Summary | Actionable? |
|----------|---------|----------|-------------------|-------------|
| 0 | ExpirationHandler | EXPIRING | DTE == 0 | Yes (Roll) |
| 10 | HarvestHandler | HARVEST | pl_pct >= target (delegated) | Yes (Close) |
| 20 | SizeThreatHandler | SIZE_THREAT | Tail risk > 5% NLV | Yes (Reduce) |
| 30 | DefenseHandler | DEFENSE | is_tested AND DTE < gamma_trigger | Yes (Adjust) |
| 40 | GammaHandler | GAMMA | NOT is_tested AND DTE < gamma_trigger | No (Warning) |
| 50 | HedgeHandler | HEDGE_CHECK | is_hedge AND dead_money range | No (Monitor) |
| 60 | ToxicThetaHandler | TOXIC | dead_money AND VRP collapsed | Yes (Close) |
| 70 | EarningsHandler | EARNINGS_WARNING | earnings within N days | No (Alert) |
| 80 | ScalableHandler | SCALABLE | VRP momentum surge | Yes (Add) |

**Priority determines:**
1. Which tag becomes the "primary action" displayed prominently in TUI
2. Order of tags in output (most urgent first)

**Example Position with Multiple Tags:**
```
AAPL Iron Condor  [🎯 HARVEST] [⚠️ GAMMA] [📅 EARNINGS_WARNING]
                   ↑ priority=10  ↑ priority=40  ↑ priority=70
                   Primary action shown in TUI
```

## 6. Benefits & Trade-offs

### 6.1 Benefits

| Benefit | Description |
|---------|-------------|
| **Comprehensive Analysis** | Positions can have multiple flags (HARVEST + GAMMA + EARNINGS) |
| **Testability** | Each handler is unit-testable in isolation |
| **Extensibility** | New handlers added via `@register(priority=N)` without modifying core |
| **Readability** | Each handler is < 50 lines with single responsibility |
| **Debuggability** | Chain can be logged/traced at each step |
| **Maintainability** | Changes to one action don't affect others |
| **Rich Context** | TUI can show primary action + secondary warnings |

### 6.2 Trade-offs

| Trade-off | Mitigation |
|-----------|------------|
| More files | Handlers grouped in `handlers/` subdirectory |
| Slight overhead | Negligible for 9 handlers; chain built once per triage |
| Learning curve | Clear documentation and consistent pattern |

## 7. Migration Strategy

### Phase 1: Parallel Implementation (1-2 days)
1. Create `src/variance/triage/` module structure
2. Implement `TriageRequest`, `TriageHandler`, `TriageChain`
3. Port each handler from `determine_cluster_action()`

### Phase 2: Integration Testing (1 day)
1. Create `tests/test_triage_chain.py`
2. Test each handler independently
3. Test full chain with sample portfolios

### Phase 3: Cutover (0.5 days)
1. Replace `determine_cluster_action()` body with orchestrator
2. Run full regression suite
3. Verify TUI output unchanged

### Phase 4: Cleanup (0.5 days)
1. Remove commented legacy code
2. Update docstrings
3. Add ADR entry

## 8. Testing Strategy

### 8.1 Unit Tests (Per Handler)
```python
# tests/triage/test_harvest_handler.py
def test_harvest_handler_adds_tag_on_profit_target():
    request = TriageRequest(pl_pct=0.55, net_cost=-100, ...)
    handler = HarvestHandler(rules)
    result = handler.handle(request)

    harvest_tags = [t for t in result.tags if t.tag_type == "HARVEST"]
    assert len(harvest_tags) == 1
    assert harvest_tags[0].priority == 10

def test_harvest_handler_skips_debit_positions():
    request = TriageRequest(pl_pct=0.55, net_cost=100, ...)  # Debit
    handler = HarvestHandler(rules)
    result = handler.handle(request)

    harvest_tags = [t for t in result.tags if t.tag_type == "HARVEST"]
    assert len(harvest_tags) == 0
```

### 8.2 Integration Tests (Full Chain)
```python
# tests/triage/test_chain_integration.py
def test_chain_collects_multiple_tags():
    """Position can have HARVEST + GAMMA + EARNINGS tags simultaneously."""
    request = TriageRequest(
        dte=7,           # In gamma zone
        pl_pct=0.60,     # Profit target hit
        net_cost=-100,   # Credit position
        earnings_date="2025-12-30",  # Earnings in 7 days
        ...
    )
    chain = TriageChain(rules)
    result = chain.triage(request)

    tag_types = {t.tag_type for t in result.tags}
    assert "HARVEST" in tag_types
    assert "GAMMA" in tag_types
    assert "EARNINGS_WARNING" in tag_types

    # Primary action should be HARVEST (lowest priority number)
    assert result.primary_action.tag_type == "HARVEST"

def test_chain_priority_determines_primary():
    """When multiple tags exist, lowest priority number wins as primary."""
    request = TriageRequest(dte=0, pl_pct=0.60, ...)
    chain = TriageChain(rules)
    result = chain.triage(request)

    # Should have both EXPIRING (0) and HARVEST (10)
    assert len(result.tags) >= 2
    # But EXPIRING is primary (lower priority number)
    assert result.primary_action.tag_type == "EXPIRING"
```

### 8.3 Regression Tests
```bash
# Verify primary action_code unchanged (backward compatibility)
python -m variance.analyze_portfolio util/sample_positions.csv --json > before.json
# (Apply refactor)
python -m variance.analyze_portfolio util/sample_positions.csv --json > after.json

# Primary action codes should match
jq '.positions[].action_code' before.json > before_actions.txt
jq '.positions[].action_code' after.json > after_actions.txt
diff before_actions.txt after_actions.txt  # Should match

# New: Verify multi-tag enrichment
jq '.positions[] | select(.tags | length > 1) | {root, tags: [.tags[].type]}' after.json
# Example output:
# {"root": "AAPL", "tags": ["HARVEST", "GAMMA", "EARNINGS_WARNING"]}
```

## 9. Status
**Proposed.** Ready for Developer implementation upon approval.
