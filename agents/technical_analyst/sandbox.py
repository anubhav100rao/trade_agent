"""
Restricted Python sandbox for safe indicator calculation.

Pattern:
  - LLM produces a Python *snippet* (no import statements)
  - Snippet is executed in a namespace that has pd/np/ta pre-injected
  - __builtins__ is empty — arbitrary imports are blocked
  - 3-second timeout enforced via threading
"""
import threading
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import pandas_ta as ta


# Safe builtins allowed inside the sandbox
_SAFE_BUILTINS = {
    "round": round,
    "float": float,
    "int": int,
    "abs": abs,
    "min": min,
    "max": max,
    "len": len,
    "list": list,
    "dict": dict,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "print": print,
    "True": True,
    "False": False,
    "None": None,
}


class SandboxTimeout(Exception):
    pass


class SandboxError(Exception):
    pass


def run_indicator_script(
    script: str,
    candles: list[dict],
    timeout_seconds: float = 4.0,
) -> dict:
    """
    Execute a pandas-ta indicator script safely.

    Args:
        script:  Python code snippet. Must assign to `result` dict.
                 Libraries pd, np, ta are pre-injected.
                 No import statements allowed.
        candles: List of OHLCV dicts with keys: open, high, low, close, volume.
        timeout_seconds: Hard timeout.

    Returns:
        The `result` dict set by the script.

    Raises:
        SandboxTimeout: if script exceeds timeout.
        SandboxError:   if script raises or result not set.
    """
    df = pd.DataFrame(candles)
    # Normalize column names
    df.columns = [c.lower() for c in df.columns]

    namespace = {
        "__builtins__": _SAFE_BUILTINS,
        "pd": pd,
        "np": np,
        "ta": ta,
        "df": df,
        "close": df["close"] if "close" in df.columns else pd.Series(dtype=float),
        "high": df["high"] if "high" in df.columns else pd.Series(dtype=float),
        "low": df["low"] if "low" in df.columns else pd.Series(dtype=float),
        "open_": df["open"] if "open" in df.columns else pd.Series(dtype=float),
        "volume": df["volume"] if "volume" in df.columns else pd.Series(dtype=float),
        "result": {},
    }

    exc_holder: list = []

    def _exec():
        try:
            exec(script, namespace)  # noqa: S102
        except Exception as e:
            exc_holder.append(e)

    thread = threading.Thread(target=_exec, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        raise SandboxTimeout(f"Script exceeded {timeout_seconds}s timeout")

    if exc_holder:
        raise SandboxError(f"Script error: {exc_holder[0]}")

    result = namespace.get("result", {})
    if not isinstance(result, dict):
        raise SandboxError("`result` must be a dict")

    return result
