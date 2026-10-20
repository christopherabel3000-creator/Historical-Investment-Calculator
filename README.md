# Historical Investment Calculator

See what a past investment would be worth today. Enter an amount, choose one-time, monthly, or yearly investing, and pick a starting month. The calculator compares four low-cost funds side by side:

| Asset | Modeled as | Yearly fee | Data starts |
|---|---|---|---|
| S&P 500 | Index fund like Vanguard 500 Index Admiral (VFIAX), dividends reinvested | 0.04% | 1871 |
| Treasury bonds | 10-year Treasuries, fee of Vanguard Intermediate-Term Treasury ETF (VGIT) | 0.03% | 1928 |
| Gold | Gold fund like SPDR Gold MiniShares (GLDM) | 0.10% | 1975 |
| Money market | 3-month Treasury bills, fee of Vanguard Federal Money Market (VMFXX) | 0.11% | 1928 |

The page is a single file, `index.html`, with all data built in. It is designed to work with screen readers: results are written out as a sentence, the chart has a matching year-by-year table, and all controls are labeled.

## Data sources

- **S&P 500:** Robert Shiller's monthly price and dividend data (via the [datasets/s-and-p-500](https://github.com/datasets/s-and-p-500) mirror) through June 2023, then SPY dividend-adjusted prices from Financial Modeling Prep, with SPY's fee added back.
- **Bonds and T-bills:** Aswath Damodaran's [annual historical returns](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/histretSP.html) through 2025, spread evenly across each year's months. 2026 bonds use month-end 10-year Treasury yields; 2026 T-bills use an estimate of 3.9% a year.
- **Gold:** Monthly prices from [datasets/gold-prices](https://github.com/datasets/gold-prices), with recent daily prices from Financial Modeling Prep.

Results ignore taxes and inflation. This is a historical illustration, not investment advice.

## Updating the data

The `tools` folder rebuilds the page:

1. Refresh the files in `tools/data`. The SPY price file (`spy_adj.json`) comes from a Financial Modeling Prep account and isn't stored in the repo.
2. From the `tools` folder, run `build_data.py` (see the usage line in `assemble.py`), then `python3 assemble.py`.
3. Commit the new `index.html`.
