# Historical Investment Calculator

See what a past investment would be worth. Enter an amount, choose one-time, monthly, or yearly investing, and pick start and end dates. The calculator compares five low-cost funds side by side, plus a custom mix of them with optional yearly rebalancing. It shows each fund's best and worst year in your time range and can show every result in today's dollars. A "Will my money last?" section tests a withdrawal plan, like taking 4% a year from $1,000,000, or works out how much you need to save for a given monthly withdrawal, against every real stretch of history and 10,000 simulated futures built from real 12-month periods:

| Asset | Modeled as | Yearly fee | Data starts |
|---|---|---|---|
| S&P 500 | Index fund like Vanguard 500 Index Admiral (VFIAX), dividends reinvested | 0.04% | 1871 |
| Treasury bonds | 10-year Treasuries, fee of Vanguard Intermediate-Term Treasury ETF (VGIT) | 0.03% | 1928 |
| Gold | Gold fund like SPDR Gold MiniShares (GLDM) | 0.10% | 1975 |
| Bitcoin | Bitcoin fund like Grayscale Bitcoin Mini Trust (BTC) | 0.15% | 2011 |
| Money market | 3-month Treasury bills, fee of Vanguard Federal Money Market (VMFXX) | 0.11% | 1928 |

The page is a single file, `index.html`, with all data built in. It is designed to work with screen readers: results are written out as a sentence, the chart has a matching year-by-year table, and all controls are labeled. `preview.png` is the image sites like LinkedIn show when the link is shared.

## Data sources

- **S&P 500:** Robert Shiller's monthly price and dividend data (via the [datasets/s-and-p-500](https://github.com/datasets/s-and-p-500) mirror) through June 2023, then SPY dividend-adjusted prices from Financial Modeling Prep, with SPY's fee added back.
- **Bonds and T-bills:** Aswath Damodaran's [annual historical returns](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/histretSP.html) spread evenly across each year's months. For a year that data doesn't cover yet, bonds use month-end 10-year Treasury yields and T-bills use the average 3-month T-bill yield so far that year.
- **Gold:** Monthly prices from [datasets/gold-prices](https://github.com/datasets/gold-prices), with recent daily prices from Financial Modeling Prep.
- **Bitcoin:** Daily prices from Financial Modeling Prep, averaged by month. Bitcoin funds only launched in 2024; earlier prices come from a small, thinly traded market.
- **Inflation:** CPI-U from Robert Shiller's dataset through July 2023, then Bureau of Labor Statistics figures. October 2025 was never published and is estimated.

Results ignore taxes. This is a historical illustration, not investment advice.

## Updating the data

The data updates itself. A GitHub Action (`.github/workflows/update-data.yml`) runs every weekday evening after the market closes: it fetches the latest prices, rebuilds the page and commits the result. On days with no new prices, it changes nothing. You can also start it by hand from the Actions tab with "Run workflow".

It needs a Financial Modeling Prep API key saved as a repository secret named `FMP_API_KEY` (Settings, then Secrets and variables, then Actions). Gold's monthly history comes from the datasets/gold-prices repo and inflation from FRED (CPIAUCNS); neither needs a key.

To run it yourself, from the repo root:

1. `FMP_API_KEY=your-key python3 tools/update.py`
2. From the `tools` folder, run `build_data.py` (see the usage line in `assemble.py`), then `python3 assemble.py`.
3. Commit the changes.

Once a year, after Aswath Damodaran publishes the previous year's returns (usually in January), add that year's row to `tools/data/tbills.csv` and `tools/data/tbonds.csv`. Until then, the estimates described above fill in.

## The iPhone app

The App Store version, "What If I'd Invested" (`com.playbyear.whatifinvested`), wraps the same page with [Capacitor](https://capacitorjs.com). `scripts/build-www.js` copies `index.html`, `privacy.html`, `support.html`, `fonts/` and `icons/` into `www/`, and `npx cap sync ios` puts them in the Xcode project in `ios/`.

The page has prices built in, but the app also downloads `data.json` from this site each time it opens, and keeps the newest copy for offline use. `assemble.py` writes `data.json` alongside `index.html`, so the daily update publishes both. If new prices arrive while the app is open, it offers to switch to them. On the website nothing changes: the page is rebuilt every weekday anyway.

There's no Mac needed: `.github/workflows/ios.yml` builds the app on GitHub's Macs. Every push that touches the calculator checks that it still builds; running the workflow by hand (Actions, iPhone app, Run workflow) signs it and sends it to TestFlight. Signing needs four repo secrets, listed at the top of the workflow.

Other files for the app:

- `privacy.html`, `support.html`: the privacy policy and support page, linked from the bottom of the calculator and used as the App Store's Privacy Policy URL and Support URL
- `fonts/`: the three fonts, bundled so the app works offline (SIL Open Font License)
- `icons/`, `tools/icon.html`, `tools/icon.py`: the app icon, launch image and website icons. `tools/screenshots.py` takes the App Store screenshots. Both use Python and Playwright; the notes at the top of each say how.
- `appstore/`: the App Store listing text and screenshots. Not part of the calculator or the app.
