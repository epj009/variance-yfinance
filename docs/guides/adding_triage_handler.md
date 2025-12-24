# How to Add a Triage Handler

## Overview
Triage handlers detect specific risk or opportunity conditions and apply **TriageTags** to a position. They execute in a deterministic sequence via the **Chain of Responsibility** pattern.

## Workflow

### 1. Create the Handler
Create a new file in `src/variance/triage/handlers/your_rule.py`.

```python
from ..handler import TriageHandler
from ..request import TriageRequest, TriageTag
from ...models.actions import ActionFactory

class YourRuleHandler(TriageHandler):
    def handle(self, request: TriageRequest) -> TriageRequest:
        if self._condition_met(request):
            cmd = ActionFactory.create("YOUR_CODE", request.root, "Your logic message")
            if cmd:
                tag = TriageTag(
                    tag_type="YOUR_CODE",
                    priority=50, # 0 (Urgent) to 100 (Info)
                    logic=cmd.logic,
                    action_cmd=cmd
                )
                request = request.with_tag(tag)
        
        return self._pass_to_next(request)
```

### 2. Register in the Chain
Add your handler to the explicit sequence in `src/variance/triage/chain.py`.

```python
from .handlers.your_rule import YourRuleHandler

# Inside _build_chain():
handlers = [
    ExpirationHandler(self.rules),
    # ...
    YourRuleHandler(self.rules), # Place according to priority
]
```

### 3. Verification
Add a unit test in `tests/triage/handlers/test_your_rule_handler.py`.
