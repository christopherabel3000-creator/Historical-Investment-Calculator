"""Fetch the latest data and refresh the files in tools/data. No API keys needed.

Run from the repo root:  python tools/update.py   (needs the xlrd package: pip install xlrd)
Then rebuild with build_data.py and assemble.py (see the usage line in assemble.py).

Sources, all free for public use:
  data/sp.csv                S&P 500 monthly average prices, dividends and CPI from Robert Shiller's
                             ie_data.xls (shillerdata.com), full months only
  data/gold_monthly.csv      monthly gold prices: the World Bank's Pink Sheet, via the
                             datasets/gold-prices mirror
  data/btc_monthly.csv       monthly average bitcoin prices from Coin Metrics' free community data
                             (CC BY-NC 4.0), full months only
  data/yields_month_end.csv  month-end 10-year Treasury yields from the US Treasury, from 2023 on
  data/tbill_estimates.csv   this year's money market estimate (average 3-month T-bill yield so far,
                             US Treasury), used until the yearly T-bill data covers the year
  data/cpi_recent.csv        monthly inflation (CPI-U) from the Bureau of Labor Statistics, or FRED

Each source is checked on its own. If one can't be reached, its saved file is kept as it is and the
others still update, so a bad day at one source never breaks the page.
"""
import csv
import datetime as dt
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
UA = {"User-Agent": "Mozilla/5.0 (historical-investment-calculator data updater; github.com/christopherabel3000-creator)"}
today = dt.date.today()
this_month = today.strftime("%Y-%m")  # not finished yet, so never saved
problems = []


def get(url, binary=False, timeout=90):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return body if binary else body.decode("utf-8", "replace")


def read_pairs(path):
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                k, v = line.strip().split(",", 1)
                out[k] = v
    return out


def write_pairs(path, pairs):
    path.write_text("".join(f"{k},{v}\n" for k, v in pairs))


def step(name, fn):
    try:
        fn()
    except Exception as e:
        problems.append(name)
        print(f"Note: couldn't update {name} ({e!r}); keeping the saved copy.")


# ---- S&P 500: Robert Shiller ----
def shiller():
    import xlrd
    page = get("https://shillerdata.com/")
    m = re.search(r'href="([^"]*ie_data\.xls[^"]*)"', page)
    if not m:
        raise ValueError("no ie_data.xls link on shillerdata.com")
    link = m.group(1).replace("&amp;", "&")
    if link.startswith("//"):
        link = "https:" + link
    sheet = xlrd.open_workbook(file_contents=get(link, binary=True)).sheet_by_name("Data")
    rows = []
    for r in range(sheet.nrows):
        v = sheet.row_values(r)
        if isinstance(v[0], float) and 1870 < v[0] < 2200 and isinstance(v[1], float) and v[1] > 0:
            y = int(v[0])
            mo = int(round((v[0] - y) * 100))
            month = f"{y}-{mo:02d}"
            if month >= this_month:
                continue
            num = lambda x: x if isinstance(x, float) else 0.0
            rows.append((month, v[1], num(v[2]), num(v[4])))
    if len(rows) < 1800 or rows[0][0] != "1871-01":
        raise ValueError(f"unexpected layout ({len(rows)} rows from {rows[0][0] if rows else '?'})")
    with open(DATA / "sp.csv", "w", newline="") as f:
        f.write("Date,SP500,Dividend,Consumer Price Index\n")
        for month, p, d, c in rows:
            f.write(f"{month}-01,{p:g},{d:g},{c:g}\n")
    last_div = max(r[0] for r in rows if r[2] > 0)
    print(f"S&P 500: Shiller prices through {rows[-1][0]}, dividends through {last_div}.")


# ---- Gold: World Bank Pink Sheet, via datasets/gold-prices ----
def gold():
    text = get("https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly.csv")
    rows = [(r["Date"][:7], float(r["Price"])) for r in csv.DictReader(io.StringIO(text))]
    rows = [(m, p) for m, p in rows if m < this_month]
    if len(rows) < 1000:
        raise ValueError(f"only {len(rows)} rows")
    with open(DATA / "gold_monthly.csv", "w", newline="") as f:
        f.write("Date,Price\n")
        for m, p in rows:
            f.write(f"{m},{p:.3f}\n")
    print(f"Gold: World Bank prices through {rows[-1][0]}.")


# ---- Bitcoin: Coin Metrics community data ----
def bitcoin():
    url = ("https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc&metrics=PriceUSD"
           "&frequency=1d&start_time=2010-07-01&page_size=10000")
    days = {}
    while url:
        j = json.loads(get(url))
        for r in j["data"]:
            if r.get("PriceUSD"):
                days[r["time"][:10]] = float(r["PriceUSD"])
        url = j.get("next_page_url")
    by = {}
    for d, p in days.items():
        by.setdefault(d[:7], []).append(p)
    months = sorted(m for m in by if "2011-01" <= m < this_month)
    if len(months) < 150:
        raise ValueError(f"only {len(months)} months")
    write_pairs(DATA / "btc_monthly.csv", [(m, f"{sum(by[m]) / len(by[m]):.6g}") for m in months])
    print(f"Bitcoin: Coin Metrics prices through {max(days)}; full months through {months[-1]}.")


# ---- Treasury yields: US Treasury daily par yield curve ----
def treasury():
    ten, three = {}, {}
    for y in range(2023, today.year + 1):
        text = get("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
                   f"daily-treasury-rates.csv/{y}/all?type=daily_treasury_yield_curve"
                   f"&field_tdr_date_value={y}&page&_format=csv")
        for r in csv.DictReader(io.StringIO(text)):
            mm, dd, yy = r["Date"].split("/")
            day = f"{yy}-{mm}-{dd}"
            if r.get("10 Yr"):
                ten[day] = float(r["10 Yr"])
            if r.get("3 Mo"):
                three[day] = float(r["3 Mo"])
    month_end = {}
    for day in sorted(ten):  # in date order, so each month keeps its last trading day
        if day[:7] < this_month:
            month_end[day[:7]] = ten[day]
    if len(month_end) < 30:
        raise ValueError(f"only {len(month_end)} months of 10-year yields")
    write_pairs(DATA / "yields_month_end.csv", [(m, f"{v:g}") for m, v in sorted(month_end.items())])
    print(f"Treasury: month-end 10-year yields through {max(month_end)}.")

    tbills = read_pairs(DATA / "tbills.csv")
    est_path = DATA / "tbill_estimates.csv"
    estimates = {k: v for k, v in read_pairs(est_path).items() if k not in tbills}
    year = str(today.year)
    ytd = [v for d, v in three.items() if d.startswith(year)]
    if year not in tbills and ytd:
        estimates[year] = f"{sum(ytd) / len(ytd):.2f}%"
        print(f"Money market estimate for {year}: {estimates[year]} (average 3-month T-bill yield so far).")
    write_pairs(est_path, sorted(estimates.items()))


# ---- Inflation: CPI-U, not seasonally adjusted (BLS, with FRED as a backup) ----
def inflation():
    cpi = read_pairs(DATA / "cpi_recent.csv")
    found = {}
    try:
        j = json.loads(get("https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0"))
        for r in j["Results"]["series"][0]["data"]:
            if r["period"].startswith("M") and r["period"] != "M13" and r["value"] not in ("-", ""):
                found[f"{r['year']}-{r['period'][1:]}"] = float(r["value"])
    except Exception as e:
        print(f"Note: BLS didn't answer ({e!r}); trying FRED.")
        text = get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCNS", timeout=60)
        for row in csv.reader(io.StringIO(text)):
            if len(row) >= 2 and row[0][:4].isdigit() and row[1].strip() not in ("", "."):
                found[row[0][:7]] = float(row[1])
    added = [m for m in sorted(found) if m > max(cpi)]
    for m in added:
        cpi[m] = f"{found[m]:.3f}"
    write_pairs(DATA / "cpi_recent.csv", sorted(cpi.items()))
    print("Inflation: new months " + (", ".join(added) if added else "none yet") + f"; latest {max(cpi)}.")


step("the S&P 500 (Shiller)", shiller)
step("gold (World Bank)", gold)
step("bitcoin (Coin Metrics)", bitcoin)
step("Treasury yields (US Treasury)", treasury)
step("inflation (BLS)", inflation)
if len(problems) == 5:
    sys.exit("ERROR: none of the sources could be reached.")
print("Data files updated." + (" Kept saved copies for: " + ", ".join(problems) + "." if problems else ""))
