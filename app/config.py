"""Central configuration. Override anything through environment variables or a .env file."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.getenv("SPENDSENSE_DATA", ROOT / "data"))
STORE_DIR = DATA_DIR / "store"
REPORT_DIR = DATA_DIR / "reports"
SAMPLE_DIR = ROOT / "data" / "sample"  # demo statements always ship with the code
for _d in (STORE_DIR, REPORT_DIR, SAMPLE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

TXN_FILE = STORE_DIR / "transactions.csv"
CATEGORY_CACHE = STORE_DIR / "category_cache.json"

CURRENCY = os.getenv("CURRENCY", "₹")

# Used by budget + "unnecessary spending" logic
ESSENTIAL = {"Rent & Housing", "Groceries", "Utilities & Bills", "Health", "Transport", "Education"}
DISCRETIONARY = {"Food Delivery", "Dining Out", "Shopping", "Entertainment", "Subscriptions", "Travel"}
NON_SPEND = {"Investments", "Transfers"}  # money moved, not consumed
