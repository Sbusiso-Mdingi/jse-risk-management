#!/usr/bin/env bash
# Build the image in ACR and roll it out to the App Service web app.
#
# Hosting is Linux App Service (Free F1 plan) because the Container Apps provider
# never finished registering on the subscription. The web app pulls from ACR with
# its managed identity (AcrPull), so no registry password is stored.
set -euo pipefail
SUB="${AZ_SUBSCRIPTION:?set AZ_SUBSCRIPTION to the Azure subscription ID}"
RG=rg-mdingi-previews
LOC=southafricanorth
ACR=mdingipreviews
PLAN=asp-mdingi-previews
WEB=mdingi-jse-risk
IMAGE=jse-risk
TAG="${TAG:-$(date +%Y%m%d%H%M)}"
TAGS="owner=sbusiso purpose=portfolio-previews billing=personal"
cd "$(dirname "$0")/.."

az acr build --registry "$ACR" --subscription "$SUB" --image "$IMAGE:$TAG" --image "$IMAGE:latest" . -o none

if ! az webapp show -n "$WEB" -g "$RG" --subscription "$SUB" -o none 2>/dev/null; then
  az appservice plan create -n "$PLAN" -g "$RG" -l "$LOC" --subscription "$SUB" --is-linux --sku F1 --tags $TAGS -o none
  az webapp create -n "$WEB" -g "$RG" -p "$PLAN" --subscription "$SUB" --tags $TAGS \
    --container-image-name "$ACR.azurecr.io/$IMAGE:$TAG" -o none
  principal=$(az webapp identity assign -n "$WEB" -g "$RG" --subscription "$SUB" --query principalId -o tsv)
  az role assignment create --assignee-object-id "$principal" --assignee-principal-type ServicePrincipal \
    --role AcrPull --scope "$(az acr show -n "$ACR" --subscription "$SUB" --query id -o tsv)" -o none
  az webapp config set -n "$WEB" -g "$RG" --subscription "$SUB" --generic-configurations '{"acrUseManagedIdentityCreds": true}' -o none
  az webapp config appsettings set -n "$WEB" -g "$RG" --subscription "$SUB" --settings WEBSITES_PORT=8000 -o none
  az webapp update -n "$WEB" -g "$RG" --subscription "$SUB" --https-only true -o none
fi

az webapp config container set -n "$WEB" -g "$RG" --subscription "$SUB" \
  --container-image-name "$ACR.azurecr.io/$IMAGE:$TAG" --container-registry-url "https://$ACR.azurecr.io" -o none
az webapp restart -n "$WEB" -g "$RG" --subscription "$SUB"
echo "https://$(az webapp show -n "$WEB" -g "$RG" --subscription "$SUB" --query defaultHostName -o tsv)"
