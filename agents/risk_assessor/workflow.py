"""
Risk Assessor Agent.
Produces contextual risk flags based on indicator data + market conditions.
Does NOT require portfolio data — purely instrument-level risk.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from libs.domain_models.recommendation import RiskFlag


def assess_risk(
    technical_result: dict,
    sentiment_result: dict | None = None,
) -> list[str]:
    """
    Derive risk flags from indicator values and sentiment.

    Returns:
        List of RiskFlag string values.
    """
    flags: list[str] = []
    indicators = technical_result or {}

    rsi = indicators.get("rsi")
    if rsi is not None:
        if rsi > 70:
            flags.append(RiskFlag.OVERBOUGHT.value)
        elif rsi < 30:
            flags.append(RiskFlag.OVERSOLD.value)

    bb_pos = indicators.get("bb_position")
    if bb_pos == "above_upper":
        flags.append(RiskFlag.HIGH_VOLATILITY.value)
    elif bb_pos == "below_lower":
        flags.append(RiskFlag.HIGH_VOLATILITY.value)

    # 52-week proximity checks
    price = indicators.get("current_price")
    high_52w = indicators.get("fifty_two_week_high")
    low_52w = indicators.get("fifty_two_week_low")

    if price and high_52w and high_52w > 0:
        if price >= high_52w * 0.98:
            flags.append(RiskFlag.NEAR_52W_HIGH.value)
    if price and low_52w and low_52w > 0:
        if price <= low_52w * 1.02:
            flags.append(RiskFlag.NEAR_52W_LOW.value)

    # Trend flags from technical signal
    signal = indicators.get("signal", "").upper()
    if signal == "BULLISH" and indicators.get("confidence", 0) >= 0.75:
        flags.append(RiskFlag.STRONG_UPTREND.value)
    elif signal == "BEARISH" and indicators.get("confidence", 0) >= 0.75:
        flags.append(RiskFlag.STRONG_DOWNTREND.value)

    # Negative sentiment amplifies risk
    if sentiment_result:
        sent_score = sentiment_result.get("score", 0)
        if sent_score < -0.5:
            if RiskFlag.HIGH_VOLATILITY.value not in flags:
                flags.append(RiskFlag.HIGH_VOLATILITY.value)

    return list(set(flags))  # deduplicate
