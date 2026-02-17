"""Market Environment Recommendation Mapping."""


def get_recommended_environment(signal_type: str) -> str:
    """Maps Signal Type to a recommended market environment for strategy selection."""
    if signal_type.startswith("COILED"):
        return "Low IV / Vol Expansion"
    if signal_type.startswith("EXPANDING"):
        return "High IV / Neutral (Undefined)"
    if signal_type == "RICH":
        return "High IV / Neutral (Undefined)"
    if signal_type == "DISCOUNT":
        return "Low IV / Vol Expansion"
    if signal_type == "EVENT":
        return "Binary Risk"
    return "Neutral / Fair Value"
