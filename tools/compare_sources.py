"""Compare the free data sources with the FMP-based numbers the calculator uses now. One-off check, run on GitHub Actions."""
import csv, io, json, re, statistics as st, urllib.request, datetime as dt, sys
UA = {"User-Agent": "Mozilla/5.0 (historical-investment-calculator source check)"}
def get(url, binary=False):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        b = r.read(); return b if binary else b.decode("utf-8", "replace")
out = []
def say(s=""): print(s); out.append(s)
cur = json.load(open("tools/returns.json"))
def series(k):
    s = cur[k]; y, m = map(int, s["start"].split("-")); d = {}
    for i, v in enumerate(s["levels"]):
        t = y * 12 + m - 1 + i; d[f"{t//12}-{t%12+1:02d}"] = v
    return d
def prevm(m): y, mo = int(m[:4]), int(m[5:]); t = y*12+mo-2; return f"{t//12}-{t%12+1:02d}"
def pct(x): return f"{x*100:+.2f}%"
def stats(name, pairs):
    """pairs: list of (month, cur_value, new_value) for monthly returns (growth factors)."""
    d = [(m, b - a) for m, a, b in pairs]
    ab = [abs(x) for _, x in d]
    worst = max(d, key=lambda t: abs(t[1]))
    gc = 1; gn = 1
    for _, a, b in pairs: gc *= a; gn *= b
    say(f"- Months compared: {len(d)} ({pairs[0][0]} to {pairs[-1][0]})")
    say(f"- Typical monthly return difference: {st.median(ab)*100:.2f} percentage points (average {st.mean(ab)*100:.2f})")
    say(f"- Biggest single-month difference: {worst[1]*100:+.2f} points, in {worst[0]}")
    say(f"- Growth over the whole period: current {pct(gc-1)}, free source {pct(gn-1)}")
    return gc, gn

# ---------- S&P 500: Shiller ----------
say("## S&P 500 (FMP's SPY since mid-2023 vs Shiller)")
try:
    import xlrd
    page = get("https://shillerdata.com/")
    link = re.search(r'href="([^"]*ie_data\.xls[^"]*)"', page).group(1).replace("&amp;", "&")
    if link.startswith("//"): link = "https:" + link
    wb = xlrd.open_workbook(file_contents=get(link, True)); sh = wb.sheet_by_name("Data")
    rows = {}
    for r in range(sh.nrows):
        v = sh.row_values(r)
        if isinstance(v[0], float) and 1870 < v[0] < 2100 and isinstance(v[1], float) and v[1] > 0:
            y = int(v[0]); mo = int(round((v[0] - y) * 100)); rows[f"{y}-{mo:02d}"] = (v[1], v[2] if isinstance(v[2], float) else 0.0)
    ms = sorted(rows); lastdiv = max(m for m in ms if rows[m][1] > 0)
    say(f"- Shiller's file has prices through {ms[-1]} and dividends through {lastdiv}")
    # carry the last known dividend forward
    D = {}; last = 0
    for m in ms:
        if rows[m][1] > 0: last = rows[m][1]
        D[m] = rows[m][1] if rows[m][1] > 0 else last
    fee_m = (1 - 0.0004) ** (1/12)
    sp = series("sp")
    pairs = [(m, sp[m] / sp[prevm(m)], (rows[m][0] + D[m]/12) / rows[prevm(m)][0] * fee_m) for m in ms if m >= "2023-07" and m in sp and prevm(m) in rows]
    stats("sp", pairs)
    pre = [(m, sp[m] / sp[prevm(m)], (rows[m][0] + D[m]/12) / rows[prevm(m)][0] * fee_m) for m in ms if "2000-01" <= m <= "2023-06" and prevm(m) in rows]
    say(f"- Sanity check, 2000 to mid-2023 (both Shiller, so should match): typical difference {st.median([abs(b-a) for _,a,b in pre])*100:.3f} points")
except Exception as e: say(f"- FAILED: {e!r}")

# ---------- Bitcoin: Coin Metrics ----------
say("\n## Bitcoin (FMP monthly averages vs Coin Metrics)")
try:
    text = get("https://raw.githubusercontent.com/coinmetrics/data/master/csv/btc.csv")
    by = {}
    for r in csv.DictReader(io.StringIO(text)):
        if r.get("PriceUSD"): by.setdefault(r["time"][:7], []).append(float(r["PriceUSD"]))
    cm = {m: sum(v)/len(v) for m, v in by.items()}
    say(f"- Coin Metrics daily prices from {min(by)} through {max(by)}")
    fmp = {}
    for line in open("tools/data/btc_monthly.csv"):
        if line.strip(): k, v = line.strip().split(","); fmp[k] = float(v)
    common = sorted(set(cm) & set(fmp))
    lvl = [(m, abs(cm[m]/fmp[m]-1)) for m in common]
    for frm in ("2011-01", "2014-01", "2018-01"):
        sub = [x for m, x in lvl if m >= frm]; w = max((t for t in lvl if t[0] >= frm), key=lambda t: t[1])
        say(f"- Monthly average price difference from {frm}: typical {st.median(sub)*100:.2f}%, biggest {w[1]*100:.1f}% in {w[0]}")
    pairs = [(m, fmp[m]/fmp[prevm(m)], cm[m]/cm[prevm(m)]) for m in common if m >= "2014-01" and prevm(m) in fmp and prevm(m) in cm]
    stats("btc", pairs)
    for frm in ("2011-01", "2013-01"):
        to = common[-1]
        say(f"- Price growth {frm} to {to}: current {fmp[to]/fmp[frm]:,.0f}x, free source {cm[to]/cm[frm]:,.0f}x")
except Exception as e: say(f"- FAILED: {e!r}")

# ---------- Gold: World Bank ----------
say("\n## Gold (current file vs World Bank Pink Sheet)")
try:
    import openpyxl
    page = get("https://www.worldbank.org/en/research/commodity-markets")
    link = re.search(r'href="([^"]*CMO-Historical-Data-Monthly\.xlsx)"', page).group(1)
    wb = openpyxl.load_workbook(io.BytesIO(get(link, True)), read_only=True, data_only=True)
    ws = wb["Monthly Prices"]; col = None; wbg = {}
    for row in ws.iter_rows(values_only=True):
        if col is None:
            for i, c in enumerate(row):
                if isinstance(c, str) and c.strip().lower() == "gold": col = i
            continue
        if isinstance(row[0], str) and re.match(r"\d{4}M\d\d", row[0]) and isinstance(row[col], (int, float)):
            wbg[f"{row[0][:4]}-{row[0][5:7]}"] = float(row[col])
    say(f"- World Bank monthly gold from {min(wbg)} through {max(wbg)}")
    g = {}
    for r in csv.DictReader(open("tools/data/gold_monthly.csv")): g[r["Date"][:7]] = float(r["Price"])
    common = sorted(m for m in set(wbg) & set(g) if m >= "1975-01")
    d = [(m, g[m]/wbg[m]-1) for m in common]
    say(f"- Months compared since 1975: {len(d)}; typical difference {st.median([abs(x) for _,x in d])*100:.3f}%")
    for m, x in d[-14:]: say(f"  - {m}: current {g[m]:,.2f}, World Bank {wbg[m]:,.2f} ({x*100:+.2f}%)")
    try:
        mirror = get("https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly.csv").strip().splitlines()[-1]
        say(f"- The datasets/gold-prices mirror's latest row: {mirror}")
    except Exception as e: say(f"- mirror check failed: {e!r}")
except Exception as e: say(f"- FAILED: {e!r}")

# ---------- Treasury yields ----------
say("\n## Treasury yields (FMP vs US Treasury)")
try:
    ten, three = {}, {}
    for y in range(2023, 2027):
        t = get(f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{y}/all?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv")
        for r in csv.DictReader(io.StringIO(t)):
            mm, dd, yy = r["Date"].split("/"); day = f"{yy}-{mm}-{dd}"
            if r.get("10 Yr"): ten[day] = float(r["10 Yr"])
            if r.get("3 Mo"): three[day] = float(r["3 Mo"])
    me = {}
    for day in sorted(ten): me[day[:7]] = ten[day]
    f = {}
    for line in open("tools/data/yields_month_end.csv"):
        if line.strip(): k, v = line.strip().split(","); f[k] = float(v)
    common = sorted(m for m in me if m in f)
    dif = [(m, me[m]-f[m]) for m in common]
    say(f"- Month-end 10-year yields compared: {len(dif)} months; typical difference {st.median([abs(x) for _,x in dif]):.3f} points, biggest {max(dif,key=lambda t:abs(t[1]))}")
    y26 = [v for k, v in three.items() if k.startswith("2026")]
    est = open("tools/data/tbill_estimates.csv").read().strip().splitlines()[-1]
    say(f"- 2026 average 3-month yield so far: Treasury {sum(y26)/len(y26):.2f}% ({len(y26)} days) vs saved estimate {est}")
except Exception as e: say(f"- FAILED: {e!r}")
try:
    t = get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10")
    say(f"- FRED backup reachable, latest DGS10 row: {t.strip().splitlines()[-1]}")
except Exception as e: say(f"- FRED backup FAILED: {e!r}")

open("compare_report.md", "w").write("\n".join(out) + "\n")
