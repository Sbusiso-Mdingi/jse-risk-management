# JSE portfolio risk

A rebuild of an R Shiny app that built JSE share portfolios by drawing 5,000 random weight vectors and keeping the one with the best in-sample Sharpe ratio, then reported VaR, ES and a few stress tests. This version asks whether any of that holds up out of sample. Every rule rebalances monthly on data available at the time, costs and securities transfer tax are charged, the rules and pass marks were committed before the first backtest (`research/PROTOCOL.md`), and sessions since 1 October 2026 are scored live.

Live dashboard: https://mdingi-jse-risk.azurewebsites.net (embedded at mdingi.co.za).

## What is tested

1. **Universe.** The 267 tickers from the original app. At each month end, the 40 most traded by median 63-day traded value among shares with at least two years of prices.
2. **Rules.** R0 the original method (random weights, weekly log returns, three years); R1 equal weight; R2 inverse volatility; R3 minimum variance; R4 equal risk contribution; R5 maximum Sharpe. R3 to R5 use Ledoit-Wolf covariance and a 10% cap. Lookback (one or two years) chosen per rule on the design period.
3. **Costs.** 10 bps a side plus 0.25% securities transfer tax on purchases. Weights drift between rebalances.
4. **Risk models.** One-day 99% and 97.5% VaR and ES from historical simulation, a normal model, EWMA and filtered historical simulation on a GJR-GARCH-t, backtested with Kupiec, Christoffersen, the Basel traffic light and the Acerbi-Szekely ES test.
5. **Stress.** The 2008 crisis, December 2015, Covid and the April 2025 tariff shock replayed on today's portfolios, plus correlation, volatility, rand and single-name shocks.

## Results

Validation January 2017 to September 2026, after costs. Full detail in `research/RESULTS.md`.

| Rule | CAGR | Volatility | Sharpe | Max drawdown |
| --- | --- | --- | --- | --- |
| R0 Original method | 3.1% | 18.6% | −0.09 | −48.1% |
| R1 Equal weight | 6.7% | 18.5% | 0.09 | −45.7% |
| R3 Minimum variance | −0.6% | 14.8% | −0.41 | −45.8% |
| R5 Maximum Sharpe | 8.4% | 20.0% | 0.18 | −37.0% |
| Satrix 40 ETF | 9.3% | 18.8% | 0.22 | −37.3% |

- Minimum variance did cut volatility (P1 passed), but its Sharpe ratio was significantly below equal weight's.
- Maximum Sharpe beat equal weight by an amount indistinguishable from noise (P2, t = 0.42).
- The original method lost to equal weight (P3 failed, t = −2.36). No rule beat the Satrix 40.
- Only filtered historical simulation passed the VaR and ES backtests for all three portfolios tested; the normal, EWMA and plain historical models all failed.

The universe is today's list of tickers, so shares that delisted before 2026 are missing; this flatters every rule roughly equally. Research output, not investment advice.

## Layout

- `jserisk/` the shared library: data cleaning, weight rules, risk models and backtests, stress scenarios, portfolio bookkeeping.
- `research/` the pipeline (`fetch.py`, `backtest.py`, `evaluate.py`, `var_backtest.py`, `stress_test.py`, `export.py`) and the protocol and results.
- `service/` FastAPI app serving the research record, the live record since the freeze, and an on-demand portfolio builder. `tests/test_parity.py` checks the live record against the research pipeline.
- `dashboard/` React and Vite front end, themed to match mdingi.co.za and designed to be embedded.
- `deploy/azure.sh` builds the image in Azure Container Registry and deploys it to App Service.

## Running locally

```sh
python -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python research/fetch.py          # downloads prices into data/raw/
.venv/bin/python research/backtest.py && .venv/bin/python research/evaluate.py
.venv/bin/python research/var_backtest.py && .venv/bin/python research/stress_test.py
.venv/bin/python research/export.py         # writes data/research.json
cd dashboard && bun install && bun run build && cd ..
cd service && PYTHONPATH=..:. ../.venv/bin/python -m pytest -q tests
PYTHONPATH=..:. APP_ROOT=.. ../.venv/bin/uvicorn app.main:app --port 8000
```

## Deploying

```sh
AZ_SUBSCRIPTION=<subscription id> TAG=v2 deploy/azure.sh
```

An App Service F1 (free) Linux plan pulling from ACR Basic through a managed identity. Responses allow framing only from mdingi.co.za and localhost. `.github/workflows/monthly-refit.yml` downloads fresh prices, reruns the pipeline and redeploys on the 5th of every month, once `deploy/github-identity.sh` has been run.

## Data

Prices and volumes come from Yahoo Finance and the three-month Treasury bill rate from FRED; neither is redistributed here. `research/fetch.py` downloads them into `data/raw/`, which is not committed. `data/research.json` holds only derived portfolio returns and test results.
