"""Fetch the latest prices and refresh the files in tools/data.

Run from the repo root:  python tools/update.py
Needs the FMP_API_KEY environment variable (a Financial Modeling Prep key).
Then rebuild with build_data.py and assemble.py (see the usage line in assemble.py).

What it updates:
  data/spy_adj.json          SPY dividend-adjusted daily closes since May 2023 (not committed)
  data/gold_monthly.csv      monthly gold prices; months the source hasn't published yet
                             are estimated from daily prices and replaced once it does
  data/gold_fmp_recent.csv   last full month's daily gold prices and the latest close
  data/btc_monthly.csv       monthly average bitcoin prices
  data/btc_last.txt          the latest bitcoin price
  data/yields_month_end.csv  month-end 10-year Treasury yields and the latest yield
  data/tbill_estimates.csv   this year's money market estimate (average 3-month T-bill yield
                             so far), used until the yearly T-bill data covers the year
  data/cpi_recent.csv        new monthly inflation (CPI-U) figures, if any were published

Only new or unfinished months are written; published history is left as it is.
"""
import csv
import datetime as dt
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
FMP = "https://financialmodelingprep.com/stable/"
GOLD_MONTHLY_URL = "https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly.csv"
CPI_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCNS"
FIXTURES = os.environ.get("UPDATE_FIXTURES")  # offline testing: a folder of saved responses
UA = {"User-Agent": "historical-investment-calculator data updater"}


def fail(msg):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(1)


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def fmp(name, path, params):
    """Call a Financial Modeling Prep endpoint and return its list of rows."""
    if FIXTURES:
        rows = json.loads((Path(FIXTURES) / f"{name}.json").read_text())
        lo, hi = params.get("from", ""), params.get("to", "9999")
        return [r for r in rows if lo <= r["date"][:10] <= hi]
    key = os.environ.get("FMP_API_KEY", "").strip()
    if not key:
        fail("The FMP_API_KEY secret is missing. Add it under Settings, Secrets and variables, Actions.")
    url = FMP + path + "?" + urllib.parse.urlencode({**params, "apikey": key})
    try:
        body = get(url)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        fail(f"Financial Modeling Prep refused the {name} request (HTTP {e.code}). "
             f"Your plan may not include this data, or the key may be wrong. Details: {detail}")
    data = json.loads(body)
    if isinstance(data, dict):
        fail(f"Financial Modeling Prep returned an error for {name}: {str(data)[:300]}")
    return data


def month_add(m, n):
    y, mo = int(m[:4]), int(m[5:7])
    t = y * 12 + mo - 1 + n
    return f"{t // 12}-{t % 12 + 1:02d}"


def chunks(start, end, days=85):
    """Split a date range into pieces small enough for one request."""
    a = dt.date.fromisoformat(start)
    b = dt.date.fromisoformat(end)
    while a <= b:
        c = min(a + dt.timedelta(days=days), b)
        yield a.isoformat(), c.isoformat()
        a = c + dt.timedelta(days=1)


def monthly_avg(rows, field):
    by = {}
    for r in rows:
        by.setdefault(r["date"][:7], []).append(float(r[field]))
    return {m: sum(v) / len(v) for m, v in by.items()}, by


def on_or_before(rows, day, field):
    best = None
    for r in sorted(rows, key=lambda r: r["date"]):
        if r["date"][:10] <= day and r.get(field) is not None:
            best = float(r[field])
    if best is None:
        fail(f"No {field} price on or before {day}.")
    return best


def read_pairs(path):
    out = {}
    for line in path.read_text().splitlines():
        if line.strip():
            k, v = line.strip().split(",", 1)
            out[k] = v
    return out


def write_pairs(path, pairs):
    path.write_text("".join(f"{k},{v}\n" for k, v in pairs))


today = dt.date.today().isoformat()

# ---- S&P 500 fund (SPY), which also sets the "as of" date ----
spy = fmp("spy", "historical-price-eod/dividend-adjusted",
          {"symbol": "SPY", "from": "2023-05-01", "to": today})
spy = sorted(({"date": r["date"][:10], "adjClose": float(r["adjClose"])} for r in spy
              if r.get("adjClose") is not None), key=lambda r: r["date"])
if len(spy) < 200:
    fail(f"Only {len(spy)} SPY prices came back; expected years of daily data.")
(DATA / "spy_adj.json").write_text(json.dumps(spy))
last_date = spy[-1]["date"]
prev = month_add(last_date[:7], -1)  # last full month
print(f"Latest market close: {last_date}; last full month: {prev}")

# ---- Gold ----
gold_rows = None
try:
    text = FIXTURES and (Path(FIXTURES) / "gold_monthly.csv").read_text() or get(GOLD_MONTHLY_URL)
    gold_rows = [(r["Date"][:7], r["Price"]) for r in csv.DictReader(io.StringIO(text))]
    if len(gold_rows) < 1000:
        raise ValueError(f"only {len(gold_rows)} rows")
except Exception as e:  # keep what we have and estimate from daily prices instead
    print(f"Note: couldn't read the monthly gold dataset ({e}); keeping the saved copy.")
    gold_rows = [(r["Date"][:7], r["Price"]) for r in csv.DictReader(open(DATA / "gold_monthly.csv"))]
gold = dict(gold_rows)
published_last = max(gold)
start = min(published_last, prev) + "-01"
gd = fmp("gold", "historical-price-eod/light", {"symbol": "GCUSD", "from": start, "to": last_date})
g_avg, g_days = monthly_avg(gd, "price")
m = published_last
while m < prev:
    nxt = month_add(m, 1)
    if m not in g_avg or nxt not in g_avg:
        fail(f"Missing daily gold prices for {m} or {nxt}.")
    gold[nxt] = f"{float(gold[m]) * g_avg[nxt] / g_avg[m]:.3f}"
    print(f"Gold {nxt} estimated from daily prices (monthly dataset ends {published_last}).")
    m = nxt
with open(DATA / "gold_monthly.csv", "w", newline="") as f:
    f.write("Date,Price\n")
    for k in sorted(gold):
        f.write(f"{k},{gold[k]}\n")
if prev not in g_days:
    fail(f"No daily gold prices for {prev}.")
prev_days = [float(r["price"]) for r in sorted(gd, key=lambda r: r["date"]) if r["date"][:7] == prev]
write_pairs(DATA / "gold_fmp_recent.csv", [
    (prev, " ".join(f"{p:g}" for p in prev_days)),
    (last_date, f"{on_or_before(gd, last_date, 'price'):g}"),
])

# ---- Bitcoin ----
btc = read_pairs(DATA / "btc_monthly.csv")
saved_last = max(btc)
bt = fmp("btc", "historical-price-eod/light",
         {"symbol": "BTCUSD", "from": min(saved_last, prev) + "-01", "to": last_date})
b_avg, _ = monthly_avg(bt, "price")
for mo, v in b_avg.items():
    if saved_last <= mo <= prev:
        btc[mo] = f"{v:.1f}"
missing = [mo for mo in (month_add(saved_last, i) for i in range(1, 40)) if mo <= prev and mo not in btc]
if missing:
    fail(f"Missing bitcoin prices for {missing}.")
write_pairs(DATA / "btc_monthly.csv", sorted(btc.items()))
(DATA / "btc_last.txt").write_text(f"{last_date},{on_or_before(bt, last_date, 'price'):.2f}\n")

# ---- Treasury yields: 10-year for bonds, 3-month for the money market estimate ----
yields = {k: v for k, v in read_pairs(DATA / "yields_month_end.csv").items() if len(k) == 7}
saved_last = max(yields)
year = last_date[:4]
start = min(saved_last + "-01", year + "-01-01")
tr = []
for a, b in chunks(start, last_date):
    tr += fmp("treasury", "treasury-rates", {"from": a, "to": b})
tr = sorted({r["date"][:10]: r for r in tr}.values(), key=lambda r: r["date"])
for r in tr:  # rows are in date order, so each month keeps its last trading day
    mo = r["date"][:7]
    if saved_last <= mo <= prev and r.get("year10") is not None:
        yields[mo] = f"{float(r['year10']):g}"
pairs = sorted(yields.items()) + [(last_date, f"{on_or_before(tr, last_date, 'year10'):g}")]
write_pairs(DATA / "yields_month_end.csv", pairs)

tbills = read_pairs(DATA / "tbills.csv")
est_path = DATA / "tbill_estimates.csv"
estimates = read_pairs(est_path) if est_path.exists() else {}
if year not in tbills:
    ytd = [float(r["month3"]) for r in tr if r["date"][:4] == year and r.get("month3") is not None]
    if ytd:
        estimates[year] = f"{sum(ytd) / len(ytd):.2f}%"
        print(f"Money market estimate for {year}: {estimates[year]} (average 3-month T-bill yield so far).")
write_pairs(est_path, sorted(estimates.items()))

# ---- Inflation (CPI-U, not seasonally adjusted) ----
cpi = read_pairs(DATA / "cpi_recent.csv")
try:
    text = (Path(FIXTURES) / "cpi.csv").read_text() if FIXTURES else get(CPI_URL)
    added = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 2 or not row[0][:4].isdigit() or row[1].strip() in ("", "."):
            continue
        mo = row[0][:7]
        if mo > max(cpi):
            cpi[mo] = f"{float(row[1]):.3f}"
            added.append(mo)
    write_pairs(DATA / "cpi_recent.csv", sorted(cpi.items()))
    print("New inflation data: " + (", ".join(added) if added else "none yet"))
except Exception as e:
    print(f"Note: couldn't check for new inflation data ({e}); keeping what's saved.")

print("Data files updated.")
