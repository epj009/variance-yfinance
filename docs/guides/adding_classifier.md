# How to Add a Strategy Classifier

## Overview
Classifiers identify trade structures (e.g., "Iron Condor") from raw option legs. They run in a prioritized chain where the first successful match wins.

## Workflow

### 1. Create the Classifier
Create a new file in `src/variance/classification/classifiers/your_strat.py`.

```python
from ..base import ClassificationContext, StrategyClassifier

class YourStratClassifier(StrategyClassifier):
    def can_classify(self, legs, ctx: ClassificationContext) -> bool:
        # Perform structural check (e.g., count legs, check sides)
        return len(ctx.option_legs) == 2 and ctx.is_multi_exp
        
    def classify(self, legs, ctx: ClassificationContext) -> str:
        return "Your Strategy Name"
```

### 2. Register in the Registry
Add your classifier to the prioritized list in `src/variance/classification/registry.py`.

```python
from .classifiers.your_strat import YourStratClassifier

# Inside __init__:
self._chain = [
    StockClassifier(),
    YourStratClassifier(), # Simple checks should be earlier
    StrangleClassifier(),
]
```

### 3. Map to ID
Add the human name to the configuration ID mapping in `src/variance/classification/mapping.py`.
