"""Read bank CSVs from many formats into one normalised schema:
date | description | amount (>0) | kind (debit/credit) | month | merchant
"""
import re

import numpy as np
import pandas as pd

DATE = ("date", "txn date", "transaction date", "value date", "posting date", "tran date")
DESC = ("description", "narration", "particulars", "details", "remarks", "transaction details", "transaction remarks")
DEBIT = ("debit", "withdrawal", "withdrawal amt.", "withdrawal amount", "dr", "withdrawals", "debit amount")
CREDIT = ("credit", "deposit", "deposit amt.", "deposit amount", "cr", "deposits", "credit amount")
AMOUNT = ("amount", "transaction amount", "amt")
TYPE = ("type", "dr/cr", "transaction type", "cr/dr")

_NOISE = re.compile(r"\b(UPI|IMPS|NEFT|RTGS|POS|ECOM|ATM|NACH|ACH|DEBIT|CREDIT|PAYMENT|TXN|REF|TO|FROM|ORDER|BILL|PAY)\b")


def _find(cols, options):
    return next((o for o in options if o in cols), None)


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(r"[,₹$\s]", "", regex=True), errors="coerce").fillna(0.0)


def clean_merchant(desc: str) -> str:
    s = str(desc).upper()
    s = re.sub(r"@[A-Z0-9]+", " ", s)
    s = re.sub(r"[0-9]+", " ", s)
    s = re.sub(r"[^A-Z& ]", " ", s)
    s = _NOISE.sub(" ", s)
    words = s.split()
    return " ".join(words[:2]) or "UNKNOWN"


def normalize(raw: pd.DataFrame) -> pd.DataFrame:
    raw = raw.copy()
    raw.columns = [str(c).strip().lower() for c in raw.columns]
    cols = set(raw.columns)
    dcol, scol = _find(cols, DATE), _find(cols, DESC)
    if not dcol or not scol:
        raise ValueError(f"Could not find date/description columns in {sorted(cols)}")

    dates = raw[dcol].astype(str)
    out = pd.DataFrame({
        "date": pd.to_datetime(dates, dayfirst=not dates.str.match(r"^\d{4}-").all(), errors="coerce"),
        "description": raw[scol].astype(str).str.strip(),
    })
    deb, cred, amt, typ = (_find(cols, o) for o in (DEBIT, CREDIT, AMOUNT, TYPE))
    if deb and cred:
        d, c = _num(raw[deb]), _num(raw[cred])
        out["amount"] = np.where(d > 0, d, c)
        out["kind"] = np.where(d > 0, "debit", "credit")
    elif amt:
        a = _num(raw[amt])
        if typ:
            is_credit = raw[typ].astype(str).str.lower().str.contains(r"cr|credit|deposit")
        else:
            is_credit = a > 0  # signed statements: negative = money out
        out["amount"] = a.abs()
        out["kind"] = np.where(is_credit, "credit", "debit")
    else:
        raise ValueError("Need Debit/Credit columns or an Amount column")

    out = out.dropna(subset=["date"])
    out = out[out["amount"] > 0].reset_index(drop=True)
    out["month"] = out["date"].dt.strftime("%Y-%m")
    out["merchant"] = out["description"].map(clean_merchant)
    return out


def load_csv(file) -> pd.DataFrame:
    return normalize(pd.read_csv(file))
