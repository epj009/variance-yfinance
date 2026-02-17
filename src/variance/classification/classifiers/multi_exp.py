"""
Multi-Expiry Strategy Classifier
"""

from datetime import datetime

from variance.models.position import Position

from ..base import ClassificationContext, StrategyClassifier


class MultiExpClassifier(StrategyClassifier):
    """Identifies Calendars and Diagonals."""

    def can_classify(self, legs: list[Position], ctx: ClassificationContext) -> bool:
        if not ctx.is_multi_exp or len(ctx.option_legs) != 2:
            return False
        return len(ctx.call_legs) == 2 or len(ctx.put_legs) == 2

    def classify(self, legs: list[Position], ctx: ClassificationContext) -> str:
        def _leg_dte(leg: Position) -> int:
            if leg.dte > 0:
                return leg.dte
            exp_str = leg.exp_date
            if not exp_str:
                return 0
            try:
                exp_date = datetime.strptime(str(exp_str), "%Y-%m-%d").date()
                return (exp_date - datetime.now().date()).days
            except ValueError:
                return 0

        def _is_pmcc(long_leg: Position, short_leg: Position) -> bool:
            long_dte = _leg_dte(long_leg)
            short_dte = _leg_dte(short_leg)
            if long_dte < 60 or long_dte < short_dte + 30:
                return False

            long_delta = float(long_leg.delta or 0.0)
            short_delta = float(short_leg.delta or 0.0)
            if long_delta != 0 and short_delta != 0:
                if long_delta < 0.60 or short_delta > 0.35 or short_delta <= 0:
                    return False
            else:
                long_strike = float(long_leg.strike or 0.0)
                short_strike = float(short_leg.strike or 0.0)
                if ctx.underlying_price and not (long_strike < ctx.underlying_price < short_strike):
                    return False

            return True

        def _is_pmcp(long_leg: Position, short_leg: Position) -> bool:
            long_dte = _leg_dte(long_leg)
            short_dte = _leg_dte(short_leg)
            if long_dte < 60 or long_dte < short_dte + 30:
                return False

            long_delta = float(long_leg.delta or 0.0)
            short_delta = float(short_leg.delta or 0.0)
            if long_delta != 0 and short_delta != 0:
                if long_delta > -0.60 or short_delta < -0.35 or short_delta >= 0:
                    return False
            else:
                long_strike = float(long_leg.strike or 0.0)
                short_strike = float(short_leg.strike or 0.0)
                if ctx.underlying_price and not (short_strike < ctx.underlying_price < long_strike):
                    return False

            return True

        if len(ctx.call_legs) == 2:
            if ctx.long_calls and ctx.short_calls:
                if _is_pmcc(ctx.long_calls[0], ctx.short_calls[0]):
                    return "Poor Man's Covered Call"
            if ctx.long_call_strikes == ctx.short_call_strikes:
                return "Calendar Spread (Call)"
            return "Diagonal Spread (Call)"
        if len(ctx.put_legs) == 2:
            if ctx.long_puts and ctx.short_puts:
                if _is_pmcp(ctx.long_puts[0], ctx.short_puts[0]):
                    return "Poor Man's Covered Put"
            if ctx.long_put_strikes == ctx.short_put_strikes:
                return "Calendar Spread (Put)"
            return "Diagonal Spread (Put)"

        return "Multi-Exp Combo"
