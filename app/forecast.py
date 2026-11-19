"""Next-month spend forecast per category: outlier-dampened weighted average blended with a linear trend."""
import numpy as np
import pandas as pd

from .analysis import monthly_matrix


def _predict_series(v: np.ndarray) -> tuple[float, float]:
    k = len(v)
    if k == 0:
        return 0.0, 0.0
    if k < 3:
        return float(v.mean()), float(v.std()) if k > 1 else float(v.mean() * 0.2)
    if k >= 4:  # damp one-off spikes so a single big purchase does not distort the forecast
        v = np.minimum(v, 2.5 * max(np.median(v), 1.0))
    wma = np.average(v, weights=np.arange(1, k + 1))
    slope, intercept = np.polyfit(np.arange(k), v, 1)
    fit = intercept + slope * np.arange(k)
    sd = float((v - fit).std(ddof=1)) if k > 2 else float(v.std())
    return float(max(0.0, 0.6 * wma + 0.4 * (intercept + slope * k))), sd


def _predict_total(mat: pd.DataFrame) -> float:
    return sum(_predict_series(mat[c].values)[0] for c in mat.columns)


def forecast_next(df: pd.DataFrame) -> dict:
    mat = monthly_matrix(df)
    if mat.empty:
        return {"available": False}
    next_month = (pd.Period(mat.index[-1]) + 1).strftime("%Y-%m")
    cats, var = {}, 0.0
    for c in mat.columns:
        p, sd = _predict_series(mat[c].values)
        cats[c] = {"forecast": p, "last_month": float(mat[c].iloc[-1]), "avg": float(mat[c].mean())}
        var += sd ** 2
    total, sd = sum(v["forecast"] for v in cats.values()), var ** 0.5

    errs = []  # rolling-origin backtest on total spend
    for i in range(3, len(mat)):
        actual = mat.iloc[i].sum()
        if actual > 0:
            errs.append(abs(_predict_total(mat.iloc[:i]) - actual) / actual)
    return {
        "available": True, "month": next_month, "total": float(total),
        "low": float(max(0, total - 1.28 * sd)), "high": float(total + 1.28 * sd),  # ~80% interval
        "by_category": dict(sorted(cats.items(), key=lambda kv: -kv[1]["forecast"])),
        "history": {m: float(v) for m, v in mat.sum(axis=1).items()},
        "backtest_mape": float(np.mean(errs) * 100) if errs else None,
        "method": "0.6 x weighted moving average (outlier-damped) + 0.4 x linear trend, per category",
    }
