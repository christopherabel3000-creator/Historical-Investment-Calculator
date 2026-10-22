"""Build index.html from template.html and returns.json.

Usage (from the tools folder):
  python3 build_data.py data/sp.csv data/tbills.csv data/spy_adj.json returns.json \
      data/tbonds.csv data/yields_month_end.csv data/gold_monthly.csv data/gold_fmp_recent.csv data/cpi_recent.csv data/btc_monthly.csv data/btc_last.txt
  python3 assemble.py
"""
from pathlib import Path

here = Path(__file__).parent
page = (here / "template.html").read_text().replace("__DATA__", (here / "returns.json").read_text())
head, rest = page.split("<style>", 1)
full = (
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    + head + "<style>" + rest.replace("</style>\n", "</style>\n</head>\n<body>\n", 1)
    + "\n</body>\n</html>\n"
)
(here.parent / "index.html").write_text(full)
print("Wrote index.html")
