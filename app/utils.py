from .config import CURRENCY


def fmt(x: float) -> str:
    return f"{CURRENCY}{x:,.0f}"


def pct(a: float, b: float) -> float:
    return 0.0 if b == 0 else (a - b) / b * 100
