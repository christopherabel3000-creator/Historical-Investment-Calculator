"""Build monthly growth indexes for the calculator.

S&P 500 (as a fund charging 0.04%/yr, like Vanguard's VFIAX):
  - Through the last month Shiller reports dividends: Shiller monthly average
    prices + dividends reinvested.
  - After that: SPY dividend-adjusted closes (monthly averages), with SPY's
    0.0945%/yr fee added back so the series tracks the index itself.
  - 0.04%/yr fee taken out of every month.
  - Final value uses the latest SPY close.
T-bills: Damodaran annual 3-month T-bill returns 1928-2025, spread evenly
  across each year's months; 2026 uses ~3.9%.
"""
import csv, json, sys, datetime
from collections import defaultdict

sp_path, tb_path, spy_path, out_path, bond_path, yields_path, gold_path, gold_recent_path, cpi_recent_path, btc_monthly_path, btc_last_path = sys.argv[1:12]
FUND_FEE = 0.0004
SPY_FEE = 0.000945
MM_FEE = 0.0011  # Vanguard Federal Money Market (VMFXX)
BOND_FEE = 0.0003  # Vanguard Intermediate-Term Treasury ETF (VGIT)
GOLD_FEE = 0.0010  # SPDR Gold MiniShares (GLDM)
BTC_FEE = 0.0015  # Grayscale Bitcoin Mini Trust (BTC)
fee_m = (1 - FUND_FEE) ** (1 / 12)

# Shiller rows up to and including the last month with a reported dividend
rows = []
with open(sp_path) as f:
    for r in csv.DictReader(f):
        rows.append((r["Date"][:7], float(r["SP500"]), float(r["Dividend"])))
last_div = max(i for i, r in enumerate(rows) if r[2] > 0)
rows = rows[: last_div + 1]
splice_month = rows[-1][0]

months, levels = [rows[0][0]], [1.0]
level = 1.0
for i in range(1, len(rows)):
    m, p, d = rows[i]
    level *= (p + d / 12) / rows[i - 1][1] * fee_m
    months.append(m)
    levels.append(level)

# SPY dividend-adjusted closes
spy = sorted(json.load(open(spy_path)), key=lambda r: r["date"])
by_month = defaultdict(list)
for r in spy:
    by_month[r["date"][:7]].append(r["adjClose"])
avg = {m: sum(v) / len(v) for m, v in by_month.items()}
last = spy[-1]
last_date = last["date"]
last_month = last_date[:7]
spy_months = sorted(m for m in avg if m > splice_month and m < last_month)  # full months only
prev = splice_month
for m in spy_months:
    level *= avg[m] / avg[prev] * (1 + SPY_FEE) ** (1 / 12) * fee_m
    months.append(m)
    levels.append(level)
    prev = m

# Final value: latest close relative to last full month's average
d_last = datetime.date.fromisoformat(last_date)
mid_prev = datetime.date(int(prev[:4]), int(prev[5:]), 15)
frac_years = (d_last - mid_prev).days / 365.25
sp_final = level * last["adjClose"] / avg[prev] * ((1 + SPY_FEE) * (1 - FUND_FEE)) ** frac_years

# T-bills
tb_annual = {}
with open(tb_path) as f:
    for line in f:
        if line.strip():
            y, r = line.strip().split(",")
            tb_annual[int(y)] = float(r.rstrip("%")) / 100
tb_annual[2026] = 0.039
tb_levels, t = [], 1.0
tb_start = "1928-01"
for m in months:
    if m < tb_start:
        continue
    tb_levels.append(t)
    t *= ((1 + tb_annual[int(m[:4])]) * (1 - MM_FEE)) ** (1 / 12)
# t is now the level at the start of the month after `prev`; carry on to last_date
start_next = datetime.date(int(prev[:4]) + (prev[5:] == "12"), int(prev[5:]) % 12 + 1, 1)
tb_final = t * ((1 + tb_annual[d_last.year]) * (1 - MM_FEE)) ** ((d_last - start_next).days / 365.25)

# ---- 10-year Treasury bonds ----
bond_annual = {}
for line in open(bond_path):
    if line.strip():
        y, r = line.strip().split(",")
        bond_annual[int(y)] = float(r.rstrip("%")) / 100
yields = {}
for line in open(yields_path):
    if line.strip():
        k, v = line.strip().split(",")
        yields[k] = float(v) / 100
def bprice(c, y, n): return c / y * (1 - (1 + y) ** -n) + (1 + y) ** -n
def bret(y0, y1, dt): return y0 * dt + bprice(y0, y1, 10 - dt) - 1
bond_fee_m = (1 - BOND_FEE) ** (1 / 12)
bd_levels, bl = [], 1.0
bd_start = "1928-01"
for m in months:
    if m < bd_start:
        continue
    bd_levels.append(bl)
    y = int(m[:4])
    if y in bond_annual:
        bl *= (1 + bond_annual[y]) ** (1 / 12) * bond_fee_m
    else:  # 2026: month-end yields
        pm = f"{y-1}-12" if m.endswith("-01") else f"{y}-{int(m[5:])-1:02d}"
        bl *= (1 + bret(yields[pm], yields[m], 1 / 12)) * bond_fee_m
part = (d_last - datetime.date(d_last.year, d_last.month, 1)).days / 365.25 + 1/365.25
bd_final = bl * (1 + bret(yields[prev], yields[last_date], part)) * (1 - BOND_FEE) ** part

# ---- Gold ----
gold = {}
for r in csv.DictReader(open(gold_path)):
    gold[r["Date"][:7]] = float(r["Price"])
recent = {}
for line in open(gold_recent_path):
    k, v = line.strip().split(",")
    p = [float(x) for x in v.split()]
    recent[k] = sum(p) / len(p)
gd_start = "1975-01"
gold_fee_m = (1 - GOLD_FEE) ** (1 / 12)
gd_levels, gl = [], 1.0
gm = [m for m in months if m >= gd_start]
for i, m in enumerate(gm):
    if i > 0:
        gl *= gold[m] / gold[gm[i - 1]] * gold_fee_m
    gd_levels.append(gl)
gd_final = gl * recent[last_date] / recent[prev] * (1 - GOLD_FEE) ** frac_years

# ---- CPI (inflation) ----
# Shiller CPI (CPI-U, not seasonally adjusted) through 2023-07, then BLS CPI-U.
# 2025-10 was never published (government shutdown) and is interpolated.
cpi = {}
for r in csv.DictReader(open(sp_path)):
    v = float(r["Consumer Price Index"])
    if v > 0 and r["Date"][:7] <= "2023-07":
        cpi[r["Date"][:7]] = v
for line in open(cpi_recent_path):
    if line.strip():
        k, v = line.strip().split(",")
        cpi[k] = float(v)
cpi_levels = [cpi[m] for m in months]

# ---- Bitcoin ----
btc = {}
for line in open(btc_monthly_path):
    if line.strip():
        k, v = line.strip().split(",")
        btc[k] = float(v)
bl_date, bl_price = open(btc_last_path).read().strip().split(",")
bc_start = "2011-01"
btc_fee_m = (1 - BTC_FEE) ** (1 / 12)
bc_levels, cl = [], 1.0
cm = [m for m in months if m >= bc_start]
for i, m in enumerate(cm):
    if i > 0:
        cl *= btc[m] / btc[cm[i - 1]] * btc_fee_m
    bc_levels.append(cl)
bc_final = cl * float(bl_price) / btc[prev] * (1 - BTC_FEE) ** frac_years

sig = lambda x: float(f"{x:.7g}")
out = {
    "lastMonth": months[-1],
    "asOfDate": last_date,
    "spliceMonth": splice_month,
    "fee": FUND_FEE,
    "sp": {"start": months[0], "levels": [sig(v) for v in levels], "final": sig(sp_final)},
    "tb": {"start": tb_start, "levels": [sig(v) for v in tb_levels], "final": sig(tb_final)},
    "bd": {"start": bd_start, "levels": [sig(v) for v in bd_levels], "final": sig(bd_final)},
    "bc": {"start": bc_start, "levels": [sig(v) for v in bc_levels], "final": sig(bc_final)},
    "cpi": {"start": months[0], "levels": [sig(v) for v in cpi_levels]},
    "gd": {"start": gd_start, "levels": [sig(v) for v in gd_levels], "final": sig(gd_final)},
}
json.dump(out, open(out_path, "w"), separators=(",", ":"))

i90 = months.index("1990-01")
print("splice after", splice_month, "| last full month", months[-1], "| as of", last_date)
print("S&P $10k Jan 1990 ->", round(10000 * sp_final / levels[i90]))
print("TB  $10k Jan 1990 ->", round(10000 * tb_final / tb_levels[months.index("1990-01") - months.index(tb_start)]))
i28 = months.index("1928-01")
yrs = (d_last - datetime.date(1928, 1, 15)).days / 365.25
print("S&P CAGR since 1928: %.2f%%" % (100 * ((sp_final / levels[i28]) ** (1 / yrs) - 1)))
for y in ("2023-07", "2024-01", "2025-01"):
    i = months.index(y)
    print(y, "-> 12mo growth %.2f%%" % (100 * (levels[i + 12] / levels[i] - 1)) if i + 12 < len(levels) else "")

i90b = months.index("1990-01") - months.index(bd_start)
print("Bonds $10k Jan 1990 ->", round(10000 * bd_final / bd_levels[i90b]))
i90g = months.index("1990-01") - months.index(gd_start)
print("Gold  $10k Jan 1990 ->", round(10000 * gd_final / gd_levels[i90g]))
yb=(d_last - datetime.date(1928,1,15)).days/365.25
print("Bonds CAGR since 1928: %.2f%%" % (100*((bd_final/bd_levels[0])**(1/yb)-1)))
yg=(d_last - datetime.date(1975,1,15)).days/365.25
print("Gold CAGR since 1975: %.2f%%" % (100*((gd_final/gd_levels[0])**(1/yg)-1)))
i26=months.index("2026-01")-months.index(bd_start)
print("Bonds 2026 YTD: %.2f%%" % (100*(bd_final/bd_levels[i26]-1)))
print("BTC $10k Jan 2015 ->", round(10000 * bc_final / bc_levels[months.index("2015-01") - months.index(bc_start)]))
