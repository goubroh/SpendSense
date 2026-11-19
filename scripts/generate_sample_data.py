"""Generate 6 realistic months of Indian bank statements (May-Oct 2026) with deliberate
'mysteries' in the latest month so the Spending Detective has something to find:
a 18,999 gadget purchase, doubled food delivery, a duplicate Netflix charge, a new
subscription, a first-time travel booking, and a new unknown merchant."""
import random
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parents[1] / "data" / "sample"
rng = random.Random(42)


def r(a, b, step=1):
    return round(rng.randint(a // step, b // step) * step)


def month_rows(y, m, last=False):
    rows, D = [], lambda d: f"{d:02d}/{m:02d}/{y}"
    add = lambda d, text, wd=0, dep=0: rows.append((D(min(d, 28)), text, wd or "", dep or ""))
    add(1, "NEFT-STIPEND-INFOSYS SPRINGBOARD-SAL", dep=45000)
    add(3, "UPI-PG RENT-OWNER SHARMA-8841@okaxis", wd=9000)
    add(5, "UPI-GROWW-MUTUAL FUND SIP-2231@icici", wd=3000)
    add(7, "UPI-JIO RECHARGE-9910@ybl", wd=299)
    add(9, "UPI-AIRTEL BROADBAND BILL-1120@paytm", wd=r(700, 800))
    add(12, "UPI-NETFLIX.COM-3321@ybl", wd=649)
    add(12, "UPI-SPOTIFY INDIA-5521@ybl", wd=119)
    add(15, "UPI-OPENAI CHATGPT PLUS-4412@ybl", wd=1950)
    for _ in range(r(6, 8)):
        add(r(1, 28), f"UPI-{rng.choice(['BIGBASKET', 'BLINKIT', 'DMART', 'ZEPTO'])}-GROCERY-{r(1000, 9999)}@ybl", wd=r(180, 900, 10))
    n_food = r(15, 17) if last else r(6, 8)
    for _ in range(n_food):
        add(r(1, 28), f"UPI-{rng.choice(['SWIGGY', 'ZOMATO'])}-ORDER {r(1000, 9999)}@ybl", wd=r(250, 650, 10) if last else r(180, 380, 10))
    for _ in range(r(2, 3)):
        add(r(1, 28), f"POS-{rng.choice(['STARBUCKS', 'HALDIRAMS RESTAURANT', 'CAFE COFFEE DAY'])}-{r(100, 999)}", wd=r(200, 700, 10))
    for _ in range(r(12, 16)):
        add(r(1, 28), f"UPI-{rng.choice(['UBER INDIA', 'OLA CABS', 'DMRC METRO', 'RAPIDO'])}-{r(1000, 9999)}@ybl", wd=r(40, 260, 5))
    for _ in range(r(1, 2)):
        add(r(1, 28), f"ECOM-{rng.choice(['AMAZON PAY', 'FLIPKART', 'MYNTRA'])}-{r(10000, 99999)}", wd=r(500, 2200, 10))
    add(r(8, 24), "UPI-APOLLO PHARMACY-6621@ybl", wd=r(250, 900, 10))
    add(r(1, 28), "ATM WDL-SBI ATM NOIDA-SEC62", wd=2000)
    if m in (6, 9):
        add(r(10, 20), "UPI-UDEMY COURSE-7712@ybl", wd=r(449, 699, 50))
    if m == 8:
        add(14, "UPI-BOOKMYSHOW-MOVIE TICKETS-2231@ybl", wd=r(600, 900, 10))
    if last:  # the mysteries
        add(12, "ECOM-CROMA ELECTRONICS-HEADPHONES-55102", wd=18999)
        add(12, "UPI-NETFLIX.COM-3321@ybl", wd=649)   # duplicate charge
        add(16, "UPI-AUDIBLE INDIA-9981@ybl", wd=199)  # new subscription
        add(18, "UPI-IRCTC TICKET BOOKING-4410@ybl", wd=3840)  # first-time travel
        add(19, "UPI-OYO ROOMS DARJEELING-1099@ybl", wd=4800)
        add(22, "UPI-ZYNTHOS LABS PVT-7723@ybl", wd=2600)  # unknown merchant
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for i, m in enumerate(range(5, 11)):
        rows = sorted(month_rows(2026, m, last=(m == 10)), key=lambda x: x[0][3:5] + x[0][:2])
        rows.sort(key=lambda x: int(x[0][:2]))
        pd.DataFrame(rows, columns=["Date", "Narration", "Withdrawal", "Deposit"]).to_csv(OUT / f"bank_2026-{m:02d}.csv", index=False)
        print("wrote", f"bank_2026-{m:02d}.csv", len(rows), "rows")


if __name__ == "__main__":
    main()
