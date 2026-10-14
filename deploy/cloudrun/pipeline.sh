#!/usr/bin/env bash
# The monthly refit, mirroring .github/workflows/monthly-refit.yml, but run as a
# Cloud Run job instead of GitHub Actions. Runs inside a fresh clone (see
# bootstrap.sh). Prices are downloaded fresh; the parity tests must pass before
# anything is pushed or deployed.
set -euo pipefail

git config user.name "cloud-run-refit[bot]"
git config user.email "cloud-run-refit@users.noreply.github.com"
# Push auth is the SSH deploy key configured by bootstrap.sh (GIT_SSH_COMMAND);
# no token is ever written to a tracked file.

pip install --no-cache-dir -r requirements.txt pytest

python research/fetch.py
python research/backtest.py
python research/evaluate.py
python research/var_backtest.py
python research/stress_test.py
python research/export.py

( cd service && PYTHONPATH=..:. python -m pytest -q tests )

git add data/research.json research/results/*.json
if git diff --cached --quiet; then
  echo "No change in fits; nothing to commit."
else
  git commit -m "Monthly refit to $(jq -r '.latest_rebalance' data/research.json)"
  git push origin "HEAD:${GH_REF:-main}"
fi

# Deploy the dashboard. Azure trusts this job's Google identity token (workload
# identity federation), so no Azure secret is stored anywhere.
: "${AZURE_CLIENT_ID:?}" "${AZURE_TENANT_ID:?}" "${AZ_SUBSCRIPTION:?}"
audience="${AZURE_AUDIENCE:-api://AzureADTokenExchange}"
token="$(curl -sf -H 'Metadata-Flavor: Google' \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=${audience}")"
az login --service-principal -u "$AZURE_CLIENT_ID" -t "$AZURE_TENANT_ID" \
  --federated-token "$token" -o none
az account set --subscription "$AZ_SUBSCRIPTION"

TAG="refit-$(jq -r '.latest_rebalance' data/research.json)-$(date +%s)" \
  AZ_SUBSCRIPTION="$AZ_SUBSCRIPTION" bash deploy/azure.sh
