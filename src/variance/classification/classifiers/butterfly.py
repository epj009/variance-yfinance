"""
Butterfly Strategy Classifier
"""

from typing import Any, Optional

from variance.portfolio_parser import parse_currency

from ..base import ClassificationContext, StrategyClassifier


class ButterflyClassifier(StrategyClassifier):
    """Identifies Butterflies and Broken Wing variants."""

    def can_classify(self, legs: list[dict[str, Any]], ctx: ClassificationContext) -> bool:
        return self._classify(ctx) is not None

    def classify(self, legs: list[dict[str, Any]], ctx: ClassificationContext) -> str:
        return self._classify(ctx) or "Custom/Combo"

    def _classify(self, ctx: ClassificationContext) -> Optional[str]:
        side = "Call" if ctx.call_legs else "Put"
        side_legs = ctx.call_legs if side == "Call" else ctx.put_legs
        if len(side_legs) not in {3, 4}:
            return None

        legs = []
        for leg in side_legs:
            qty = parse_currency(leg.get("Quantity", "0"))
            if qty == 0:
                continue
            strike = parse_currency(leg.get("Strike Price", "0"))
            legs.append((strike, qty))

        if len(legs) not in {3, 4}:
            return None

        legs.sort(key=lambda item: item[0])
        signs = [qty > 0 for _, qty in legs]
        pos_qty = sum(qty for _, qty in legs if qty > 0)
        neg_qty = -sum(qty for _, qty in legs if qty < 0)

        if len(legs) == 3:
            if signs != [True, False, True]:
                return None
            if pos_qty <= 0 or neg_qty != pos_qty:
                return None
            lower_wing = legs[1][0] - legs[0][0]
            upper_wing = legs[2][0] - legs[1][0]
            if lower_wing == upper_wing:
                return f"{side} Butterfly"
            return f"{side} Broken Wing Butterfly"

        if len(legs) == 4:
            if signs != [True, False, False, True]:
                return None
            if pos_qty <= 0 or neg_qty != pos_qty:
                return None
            return f"{side} Broken Heart Butterfly"

        return None

        # Simple butterfly has 1-2-1 ratio
        short_qty = ctx.short_call_qty if side == "Call" else ctx.short_put_qty
        long_qty = ctx.long_call_qty if side == "Call" else ctx.long_put_qty

        if abs(short_qty) == 2 and long_qty == 2:
            return f"Butterfly ({side})"

        return f"Custom {side} Butterfly"
