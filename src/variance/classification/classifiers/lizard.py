"""
Lizard Strategy Classifier
"""

from variance.models.position import Position

from ..base import ClassificationContext, StrategyClassifier


class LizardClassifier(StrategyClassifier):
    """Identifies Jade and Big Lizards."""

    def can_classify(self, legs: list[Position], ctx: ClassificationContext) -> bool:
        if len(ctx.option_legs) != 3:
            return False
        return (
            len(ctx.short_puts) == 1 and len(ctx.short_calls) == 1 and len(ctx.long_calls) == 1
        ) or (len(ctx.short_calls) == 1 and len(ctx.short_puts) == 1 and len(ctx.long_puts) == 1)

    def classify(self, legs: list[Position], ctx: ClassificationContext) -> str:
        # Jade Lizard: Short Put + Call Credit Spread
        if len(ctx.short_puts) == 1 and len(ctx.short_calls) == 1 and len(ctx.long_calls) == 1:
            short_put_strike = float(ctx.short_puts[0].strike or 0.0)
            if ctx.underlying_price and short_put_strike >= ctx.underlying_price:
                return "Big Lizard"
            return "Jade Lizard"
        # Reverse Jade Lizard: Short Call + Put Credit Spread
        if len(ctx.short_calls) == 1 and len(ctx.short_puts) == 1 and len(ctx.long_puts) == 1:
            short_call_strike = float(ctx.short_calls[0].strike or 0.0)
            if ctx.underlying_price and short_call_strike <= ctx.underlying_price:
                return "Reverse Big Lizard"
            return "Reverse Jade Lizard"

        return "Custom/Combo"
