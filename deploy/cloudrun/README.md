# Monthly refit on Cloud Run

The code lives here on GitHub; only the **scheduled compute** runs on Google
Cloud Run instead of GitHub Actions. Each month a Cloud Run job clones this repo
fresh, downloads prices, refits, runs the parity tests, pushes the new results
back to GitHub, and redeploys the Azure dashboard — exactly what
`.github/workflows/monthly-refit.yml` used to do.

## How it fits together

```
Cloud Scheduler ──monthly──> Cloud Run job
                               ├─ git clone this repo @ main   (bootstrap.sh)
                               ├─ fetch · backtest · evaluate · var · stress · export
                               ├─ pytest parity gate
                               ├─ git push results back to GitHub   (PAT from Secret Manager)
                               └─ az login via GCP→Azure federation, then deploy/azure.sh
```

- **No Azure secret is stored.** Azure trusts the job's Google identity token
  (workload identity federation) on the existing `gh-jse-risk-refit` app, which
  already holds Contributor on `rg-mdingi-previews`.
- **The only secret** is a GitHub fine-grained PAT (`contents: read+write` on
  this repo) in Secret Manager, used to push results back.
- The image is a generic runtime; application dependencies come from the clone,
  so ordinary code changes need no image rebuild.

## One-time setup

Prerequisite: `deploy/github-identity.sh` has already run (creates the Azure
app). Then:

```bash
AZ_SUBSCRIPTION=<Sequrin - Development subscription id> \
GH_TOKEN=<fine-grained PAT> \
  bash deploy/cloudrun/provision.sh
```

Override `GCP_PROJECT` / `GCP_REGION` if needed (defaults: current gcloud
project, `europe-west1`).

## Run it manually

```bash
gcloud run jobs execute jse-risk-refit --region europe-west1
```

## Cost

A monthly job plus one scheduler entry and a small image sit inside the Cloud
Run / Scheduler / Artifact Registry free tiers — effectively zero.
