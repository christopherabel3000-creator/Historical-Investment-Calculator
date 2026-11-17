"""One-off: check sources for recent bitcoin prices."""
import json, urllib.request, statistics as st
UA = {"User-Agent": "Mozilla/5.0 (historical-investment-calculator source check)"}
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60) as r: return json.loads(r.read())
out = []
def say(s=""): print(s); out.append(s)
fmp = {}
for line in open("tools/data/btc_monthly.csv"):
    if line.strip(): k, v = line.strip().split(","); fmp[k] = float(v)
def compare(name, daily):
    by = {}
    for d, p in daily: by.setdefault(d[:7], []).append(p)
    say(f"- {name}: daily prices from {min(by)} through {max(d for d,_ in daily)}")
    for m in sorted(by):
        if m in fmp and m >= "2025-11": say(f"  - {m}: FMP {fmp[m]:,.0f}, {name} {sum(by[m])/len(by[m]):,.0f} ({(sum(by[m])/len(by[m]))/fmp[m]*100-100:+.2f}%)")
say("## Recent bitcoin sources")
try:
    j = get("https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc&metrics=PriceUSD&frequency=1d&start_time=2025-11-01&page_size=10000")
    compare("Coin Metrics community API", [(r["time"][:10], float(r["PriceUSD"])) for r in j["data"]])
except Exception as e: say(f"- Coin Metrics community API FAILED: {e!r}")
try:
    j = get("https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=365&interval=daily")
    import datetime as dt
    compare("CoinGecko keyless", [(dt.datetime.utcfromtimestamp(t/1000).strftime("%Y-%m-%d"), p) for t, p in j["prices"]])
except Exception as e: say(f"- CoinGecko FAILED: {e!r}")
try:
    import datetime as dt
    rows = []
    start = dt.datetime(2025, 11, 1)
    while start < dt.datetime.utcnow():
        end = start + dt.timedelta(days=299)
        j = get(f"https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=86400&start={start:%Y-%m-%dT00:00:00Z}&end={end:%Y-%m-%dT00:00:00Z}")
        rows += [(dt.datetime.utcfromtimestamp(c[0]).strftime("%Y-%m-%d"), float(c[4])) for c in j]
        start = end
    compare("Coinbase", rows)
except Exception as e: say(f"- Coinbase FAILED: {e!r}")
open("compare_report.md", "w").write("\n".join(out) + "\n")
