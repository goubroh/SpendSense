"""Hybrid categoriser: fast keyword rules first, optional LLM for unknown merchants,
and a persistent cache so user corrections / LLM answers are reused."""
import json
import re

import pandas as pd

from .config import CATEGORY_CACHE

# Order matters: specific rules before generic ones.
RULES = {
    "Subscriptions": ["NETFLIX", "SPOTIFY", "PRIME VIDEO", "AMAZON PRIME", "HOTSTAR", "YOUTUBE PREMIUM", "OPENAI", "CHATGPT", "AUDIBLE", "ICLOUD", "GOOGLE ONE", "ADOBE", "LINKEDIN PREM", "SONYLIV", "ZEE5"],
    "Rent & Housing": ["RENT", "PG ", "LANDLORD", "HOSTEL", "MAINTENANCE", "BROKERAGE"],
    "Groceries": ["BIGBASKET", "BLINKIT", "ZEPTO", "DMART", "GROFERS", "JIOMART", "INSTAMART", "RELIANCE FRESH", "KIRANA", "SUPERMARKET", "VEGETABLE"],
    "Food Delivery": ["SWIGGY", "ZOMATO", "EATSURE", "DOMINOS", "FAASOS"],
    "Dining Out": ["RESTAURANT", "CAFE", "STARBUCKS", "MCDONALD", "KFC", "BURGER", "PIZZA", "HALDIRAM", "BARBEQUE", "DHABA", "CHAI", "BAKERY"],
    "Transport": ["UBER", "OLA", "RAPIDO", "METRO", "DMRC", "FASTAG", "PETROL", "FUEL", "IOCL", "BPCL", "HPCL", "NAMMA", "BMTC"],
    "Travel": ["IRCTC", "MAKEMYTRIP", "GOIBIBO", "REDBUS", "INDIGO", "AIR INDIA", "VISTARA", "AIRBNB", "OYO", "BOOKING.COM", "CLEARTRIP", "HOTEL"],
    "Shopping": ["AMAZON", "FLIPKART", "MYNTRA", "AJIO", "NYKAA", "MEESHO", "CROMA", "RELIANCE DIGITAL", "DECATHLON", "IKEA", "LIFESTYLE", "ZARA", "H&M", "TATA CLIQ"],
    "Entertainment": ["BOOKMYSHOW", "PVR", "INOX", "STEAM", "PLAYSTATION", "DREAM11", "GAMING", "CONCERT"],
    "Utilities & Bills": ["AIRTEL", "JIO", "VODAFONE", "VI ", "BSNL", "ELECTRICITY", "BESCOM", "TATA POWER", "BROADBAND", "ACT FIBERNET", "GAS", "WATER BILL", "RECHARGE", "DTH"],
    "Health": ["PHARMACY", "APOLLO", "MEDPLUS", "1MG", "PHARMEASY", "HOSPITAL", "CLINIC", "DIAGNOSTIC", "NETMEDS", "DOCTOR", "CULT.FIT", "GYM"],
    "Education": ["UDEMY", "COURSERA", "UNACADEMY", "BYJU", "EXAM FEE", "TUITION", "UNIVERSITY", "COLLEGE", "BOOKS", "NPTEL", "SPRINGBOARD"],
    "Investments": ["SIP", "MUTUAL FUND", "ZERODHA", "GROWW", "UPSTOX", "NPS", "PPF", "COIN", "KUVERA", "SMALLCASE"],
    "Cash Withdrawal": ["ATM WDL", "ATM CASH", "CASH WITHDRAWAL", "ATM-"],
    "Fees & Charges": ["CHARGES", "PENALTY", "ANNUAL FEE", "SMS CHRG", "GST", "LATE FEE", "INTEREST DEBIT"],
    "Transfers": ["SELF TRANSFER", "OWN ACCOUNT", "TRANSFER TO"],
}
_COMPILED = {c: re.compile("|".join(re.escape(k) for k in kws)) for c, kws in RULES.items()}


def rule_category(description: str) -> str:
    d = str(description).upper()
    for cat, rx in _COMPILED.items():
        if rx.search(d):
            return cat
    return "Others"


def _load_cache() -> dict:
    return json.loads(CATEGORY_CACHE.read_text()) if CATEGORY_CACHE.exists() else {}


def _save_cache(c: dict):
    CATEGORY_CACHE.parent.mkdir(parents=True, exist_ok=True)
    CATEGORY_CACHE.write_text(json.dumps(c, indent=2))


def set_override(merchant: str, category: str):
    """User correction ('this merchant is actually Groceries') - persisted and reused forever."""
    c = _load_cache()
    c[merchant.upper()] = category
    _save_cache(c)


def llm_categorize_unknown(merchants: list[str], llm) -> dict:
    """Ask the LLM to classify merchants the rules could not. Returns {merchant: category}."""
    from .llm_client import ask_json
    if not merchants or llm is None:
        return {}
    cats = list(RULES) + ["Others"]
    prompt = (
        f"Classify each merchant/payee name from an Indian bank statement into exactly one of: {cats}.\n"
        f"Merchants: {merchants[:40]}\nReturn ONLY a JSON object mapping merchant -> category."
    )
    res = ask_json(llm, "You are a precise transaction classifier.", prompt) or {}
    return {m: c for m, c in res.items() if c in cats}


def categorize(df: pd.DataFrame, llm=None) -> pd.DataFrame:
    df = df.copy()
    cache = _load_cache()
    cats = []
    for desc, mer, kind in zip(df["description"], df["merchant"], df["kind"]):
        if kind == "credit":
            cats.append("Income")
        elif mer.upper() in cache:
            cats.append(cache[mer.upper()])
        else:
            cats.append(rule_category(desc))
    df["category"] = cats
    if llm is not None:
        unknown = sorted(df.loc[df["category"] == "Others", "merchant"].unique())
        learned = llm_categorize_unknown(unknown, llm)
        if learned:
            cache.update({k.upper(): v for k, v in learned.items()})
            _save_cache(cache)
            df["category"] = [learned.get(m, c) if c == "Others" else c for m, c in zip(df["merchant"], df["category"])]
    return df
