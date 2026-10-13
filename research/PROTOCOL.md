# Protocol

Written on 13 October 2026, before any backtest in this repository was run. Prices were downloaded and their coverage checked (which tickers exist and since when); no return, weight or risk figure had been computed.

The original project (an R Shiny app, 2024) let a user pick JSE shares, drew 5,000 random weight vectors, kept the one with the best mean-to-volatility ratio and reported its risk. Every figure it showed was in sample: the weights were chosen on the same returns they were then scored on. This rebuild asks whether any of that survives out of sample.

## Data

- Universe: the 267 tickers in the original app, of which 265 are still on Yahoo Finance. Daily adjusted closes and volumes since 2005. Benchmark: Satrix 40 ETF (STX40.JO, adjusted for distributions); the Top 40 price index (^J200.JO) is shown for reference. Risk-free rate: South African 91-day Treasury bill (FRED INTGSTZAM193N, monthly, carried forward).
- Cleaning: a one-day move of more than 40% that reverses the next day is a bad print and is dropped, as in the stat-arb project. Days with no trade (zero volume and an unchanged close) are treated as missing.
- **Survivorship bias.** Only firms still listed in 2024 are in the list, and Yahoo's history for some (Sibanye-Stillwater, Richemont, BHP) starts at a relisting rather than the first listing. Delistings such as Steinhoff are absent. Every absolute return here is therefore biased upwards. Comparisons between rules on the same universe are less affected, and they are what the tests are about.

## Investable set at each rebalance

At each month end, the 40 tickers with the highest median daily traded value (close times volume) over the previous 63 sessions, among those with at least 504 sessions of history (the longest window) and no more than 10% missing days in the last 504 sessions. Every rule and window therefore sees the same 40 names. Ranking uses only data up to that close.

## Rules

All rules are long only, rebalance at month-end closes and hold for the next month. Costs: 10 bps per side on traded value plus 25 bps securities transfer tax on purchases.

| Rule | Weights |
| --- | --- |
| R0, original | The app's method: 5,000 uniform random weight vectors (normalised), keep the highest mean / volatility on weekly (Wednesday) log returns, no risk-free rate, sample covariance |
| R1, equal weight | 1/40 |
| R2, inverse volatility | Proportional to 1 / daily volatility |
| R3, minimum variance | Minimise w'Σw with Ledoit-Wolf shrinkage of Σ, each weight at most 10% |
| R4, equal risk contribution | Every holding contributes the same share of variance (Ledoit-Wolf Σ) |
| R5, maximum Sharpe | Maximise (w'μ − r_f) / √(w'Σw), μ the sample mean, Ledoit-Wolf Σ, each weight at most 10% |

Estimation window: 252 or 504 sessions, chosen once per rule by design-period Sharpe. R0 uses 156 weeks (3 years) and its random draws are seeded. Nothing else is tuned.

## Periods

- Design: January 2008 to December 2016. Used to choose the window and to debug.
- Validation: January 2017 to September 2026. Run once after the design choices are fixed.
- Live: from 1 October 2026. Weights set at the 30 September 2026 close are frozen and scored daily by the dashboard; later months use the same frozen rules on the data available at each month end.

## Tests (validation period, after costs)

- **P1, risk.** R3 has lower annualised volatility than both R1 and the Satrix 40. This is what minimum variance is for; failing it would mean the covariance estimate is not working.
- **P2, return per unit of risk.** At least one of R3, R4 and R5 has a higher Sharpe ratio than R1. Reported with the Ledoit-Wolf (2008) HAC test of the Sharpe difference; a difference with |t| < 2 is called within noise.
- **P3, the original method.** R0 has a higher Sharpe ratio than R1. Expected to fail: the original weights maximise an in-sample estimate of the mean, which is the noisiest input there is.

## Value at risk and expected shortfall

Daily one-day VaR at 99% and 97.5%, and expected shortfall at 97.5%, for the R1 and R3 portfolios and the Satrix 40, over the validation period. Each forecast uses only returns up to the previous close.

| Model | Estimate |
| --- | --- |
| Historical simulation | Last 250 sessions |
| Normal | Mean and volatility of the last 250 sessions |
| EWMA | RiskMetrics, λ = 0.94, normal quantile |
| Filtered historical simulation | GJR-GARCH(1,1) with Student t innovations on the last 1,000 sessions, refitted each month end; quantile of the standardised residuals |

Backtests: Kupiec proportion of failures, Christoffersen independence and conditional coverage (5% level), Basel traffic light on 250-day windows, and the Acerbi-Szekely Z2 statistic for expected shortfall (rejection below −0.70, their 5% figure for the 97.5% level). Expected before running: the normal model fails at 99% for all three portfolios and filtered historical simulation passes.

## Stress scenarios

Applied to the frozen 30 September 2026 portfolios.

- Historical: the Top 40's peak-to-trough fall in the 2008 crisis (within May 2008 to March 2009), the December 2015 finance minister change (8 to 11 December 2015), the 2020 Covid crash (within February to March 2020) and the April 2025 US tariff shock (within April 2025). Each holding takes its own return over the window; a holding without prices in the window takes its beta to the Top 40 times the index return, and is flagged.
- Hypothetical: every correlation raised to 0.9 with volatilities unchanged, and volatilities doubled with correlations unchanged; each reported as the change in 99% normal VaR. A 20% fall in the rand (USD/ZAR up 25%), applied through each holding's beta to USD/ZAR. The largest holding going to zero.

These are illustrations, not tests.

## Amendments

- 13 October 2026, before any backtest: the history requirement was raised from 252 to 504 sessions so that the 504-session window never fills a missing year with averages, and every rule trades the same 40 names.
- 13 October 2026, after the first stress run (an illustration, not a test): the rand scenario uses betas from 104 weekly (Wednesday) returns instead of daily ones. Yahoo's daily USD/ZAR close is not taken at the JSE close, and daily betas came out near zero for every share, including rand hedges.
