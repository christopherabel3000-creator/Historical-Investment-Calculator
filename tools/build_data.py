"""Build monthly growth indexes for the calculator from the files in tools/data.

Usage (from the tools folder):
  python3 build_data.py data/sp.csv data/tbills.csv returns.json data/tbonds.csv \
      data/yields_month_end.csv data/gold_monthly.csv data/cpi_recent.csv data/btc_monthly.csv

Everything is monthly. The data runs through the latest full month that the S&P 500, gold, bitcoin and
bond data all cover, and each fund's value in that month is its final value.

S&P 500 (as a fund charging 0.04%/yr, like Vanguard's VFIAX): Shiller monthly average prices with
  dividends reinvested. Shiller reports dividends a few months late; until a month's dividend is
  published, it reuses the latest reported one.
T-bills: Damodaran annual 3-month T-bill returns, spread evenly across each year's months; a year that
  data doesn't cover yet uses tbill_estimates.csv.
Bonds: Damodaran annual 10-year Treasury returns, spread evenly; later years are calculated from
  month-end 10-year yields.
Gold: World Bank monthly prices from 1975. Bitcoin: Coin Metrics monthly averages from 2011.
Each fund's fee is taken out of every month.
"""
import csv, json, sys
from pathlib import Path

sp_path, tb_path, out_path, bond_path, yields_path, gold_path, cpi_recent_path, btc_monthly_path = sys.argv[1:9]
FUND_FEE = 0.0004  # Vanguard 500 Index Admiral (VFIAX)
MM_FEE = 0.0011  # Vanguard Federal Money Market (VMFXX)
BOND_FEE = 0.0003  # Vanguard Intermediate-Term Treasury ETF (VGIT)
GOLD_FEE = 0.0010  # SPDR Gold MiniShares (GLDM)
BTC_FEE = 0.0015  # Grayscale Bitcoin Mini Trust (BTC)


def monthly_fee(fee):
    return (1 - fee) ** (1 / 12)


def pairs(path):
    out = {}
    for line in open(path):
        if line.strip() and not line.startswith("Date"):
            k, v = line.strip().split(",")[:2]
            out[k[:7]] = v
    return out


def prev_month(m):
    y, mo = int(m[:4]), int(m[5:])
    return f"{y - 1}-12" if mo == 1 else f"{y}-{mo - 1:02d}"


# ---- Inputs ----
shiller = [(r["Date"][:7], float(r["SP500"]), float(r["Dividend"]), float(r["Consumer Price Index"]))
           for r in csv.DictReader(open(sp_path))]
gold = {k: float(v) for k, v in pairs(gold_path).items()}
btc = {k: float(v) for k, v in pairs(btc_monthly_path).items()}
yields = {k: float(v) / 100 for k, v in pairs(yields_path).items()}
annual = lambda path: {int(k): float(v.rstrip("%")) / 100 for k, v in pairs(path).items()}
bond_annual = annual(bond_path)
tb_annual = annual(tb_path)
est_path = Path(tb_path).with_name("tbill_estimates.csv")
if est_path.exists():
    for y, r in annual(est_path).items():
        tb_annual.setdefault(y, r)

# The last month every series covers
last_month = min(shiller[-1][0], max(gold), max(btc), max(yields))
months = [r[0] for r in shiller if r[0] <= last_month]
print("Data runs through", last_month)

# ---- S&P 500 ----
fee_m = monthly_fee(FUND_FEE)
levels, level, div = [1.0], 1.0, shiller[0][2]
last_div_month = max(r[0] for r in shiller if r[2] > 0)
for i in range(1, len(months)):
    m, p, d, _ = shiller[i]
    div = d if d > 0 else div
    level *= (p + div / 12) / shiller[i - 1][1] * fee_m
    levels.append(level)

# ---- T-bills (money market) ----
for y in range(min(tb_annual), int(last_month[:4]) + 1):
    if y not in tb_annual:  # no estimate yet: carry the latest rate forward
        tb_annual[y] = tb_annual[y - 1]
tb_start = "1928-01"
tb_levels, t = [], 1.0
for m in months:
    if m < tb_start:
        continue
    if m > tb_start:
        t *= ((1 + tb_annual[int(prev_month(m)[:4])]) * (1 - MM_FEE)) ** (1 / 12)
    tb_levels.append(t)

# ---- 10-year Treasury bonds ----
def bprice(c, y, n): return c / y * (1 - (1 + y) ** -n) + (1 + y) ** -n
def bret(y0, y1, dt): return y0 * dt + bprice(y0, y1, 10 - dt) - 1
bond_fee_m = monthly_fee(BOND_FEE)
bd_start = "1928-01"
bd_levels, bl = [], 1.0
for m in months:
    if m < bd_start:
        continue
    if m > bd_start:
        pm = prev_month(m)
        y = int(pm[:4])
        if y in bond_annual:
            bl *= (1 + bond_annual[y]) ** (1 / 12) * bond_fee_m
        else:  # a year the annual data doesn't cover yet: month-end yields
            bl *= (1 + bret(yields[prev_month(pm)], yields[pm], 1 / 12)) * bond_fee_m
    bd_levels.append(bl)

# ---- Gold ----
gd_start = "1975-01"
gold_fee_m = monthly_fee(GOLD_FEE)
gm = [m for m in months if m >= gd_start]
gd_levels, gl = [], 1.0
for i, m in enumerate(gm):
    if i > 0:
        gl *= gold[m] / gold[gm[i - 1]] * gold_fee_m
    gd_levels.append(gl)

# ---- Bitcoin ----
bc_start = "2011-01"
btc_fee_m = monthly_fee(BTC_FEE)
cm = [m for m in months if m >= bc_start]
bc_levels, cl = [], 1.0
for i, m in enumerate(cm):
    if i > 0:
        cl *= btc[m] / btc[cm[i - 1]] * btc_fee_m
    bc_levels.append(cl)

# ---- CPI (inflation) ----
# Shiller CPI (CPI-U, not seasonally adjusted) through 2023-07, then BLS CPI-U.
# 2025-10 was never published (government shutdown) and is interpolated in cpi_recent.csv.
cpi = {m: c for m, _, _, c in shiller if c > 0 and m <= "2023-07"}
cpi.update({k: float(v) for k, v in pairs(cpi_recent_path).items()})
# The newest month or two of CPI may not be published yet; the page uses the latest available.
# Stop at the first missing month so the series never has a gap.
cpi_levels = []
for m in months:
    if m not in cpi:
        break
    cpi_levels.append(cpi[m])
if len(months) - len(cpi_levels) > 3:
    raise SystemExit(f"Inflation data stops at {months[len(cpi_levels) - 1]}; check cpi_recent.csv.")

sig = lambda x: float(f"{x:.7g}")
ser = lambda start, lv: {"start": start, "levels": [sig(v) for v in lv], "final": sig(lv[-1])}
out = {
    "lastMonth": last_month,
    "asOfDate": last_month + "-15",  # monthly data: values are the month's average price
    "fee": FUND_FEE,
    "sp": ser(months[0], levels),
    "tb": ser(tb_start, tb_levels),
    "bd": ser(bd_start, bd_levels),
    "bc": ser(bc_start, bc_levels),
    "cpi": {"start": months[0], "levels": [sig(v) for v in cpi_levels]},
    "gd": ser(gd_start, gd_levels),
}
json.dump(out, open(out_path, "w"), separators=(",", ":"))

at = lambda lv, start, m: lv[months.index(m) - months.index(start)]
print("S&P dividends reported through", last_div_month)
print("S&P   $10k Jan 1990 ->", round(10000 * levels[-1] / at(levels, months[0], "1990-01")))
print("Bonds $10k Jan 1990 ->", round(10000 * bd_levels[-1] / at(bd_levels, bd_start, "1990-01")))
print("T-bills $10k Jan 1990 ->", round(10000 * tb_levels[-1] / at(tb_levels, tb_start, "1990-01")))
print("Gold  $10k Jan 1990 ->", round(10000 * gd_levels[-1] / at(gd_levels, gd_start, "1990-01")))
print("BTC   $10k Jan 2015 ->", round(10000 * bc_levels[-1] / at(bc_levels, bc_start, "2015-01")))
