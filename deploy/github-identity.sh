#!/usr/bin/env bash
# One-off: let the monthly-refit workflow deploy, without storing a password.
#
# Creates an Entra app whose only credential is GitHub's OIDC token for this repo's main
# branch, gives it Contributor on the previews resource group alone, and stores the IDs
# as repository secrets.
set -euo pipefail
SUB="${AZ_SUBSCRIPTION:?set AZ_SUBSCRIPTION to the Azure subscription ID}"
RG=rg-mdingi-previews
REPO=Sbusiso-Mdingi/jse-risk-management
NAME=gh-jse-risk-refit

APP=$(az ad app list --display-name "$NAME" --query "[0].appId" -o tsv)
if [ -z "$APP" ]; then
  APP=$(az ad app create --display-name "$NAME" --query appId -o tsv)
  az ad sp create --id "$APP" -o none
  az ad app federated-credential create --id "$APP" -o none --parameters "{
    \"name\": \"github-main\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"repo:$REPO:ref:refs/heads/main\",
    \"audiences\": [\"api://AzureADTokenExchange\"]
  }"
fi

SCOPE=$(az group show -n "$RG" --subscription "$SUB" --query id -o tsv)
# A new service principal can take a few seconds to become assignable.
for _ in 1 2 3 4 5 6; do
  az role assignment create --assignee "$APP" --role Contributor --scope "$SCOPE" -o none && break
  sleep 15
done

gh secret set AZURE_CLIENT_ID -R "$REPO" --body "$APP"
gh secret set AZURE_TENANT_ID -R "$REPO" --body "$(az account show --subscription "$SUB" --query tenantId -o tsv)"
gh secret set AZURE_SUBSCRIPTION_ID -R "$REPO" --body "$SUB"
echo "Done. Run the workflow once with: gh workflow run monthly-refit.yml -R $REPO"
