#!/usr/bin/env bash
# One-off: stand up the monthly refit on Google Cloud Run instead of GitHub
# Actions. GitHub stays the home of the code and where results are pushed; this
# only moves the scheduled compute.
#
# Run it like github-identity.sh:
#   AZ_SUBSCRIPTION=<dev-subscription-id> GH_TOKEN=<fine-grained-pat> \
#     bash deploy/cloudrun/provision.sh
#
# GH_TOKEN needs contents:read+write on this repo only. No Azure secret is
# stored: Azure trusts the job's Google identity token via federation, reusing
# the Contributor grant the existing refit app already has on the previews group.
set -euo pipefail

SUB="${AZ_SUBSCRIPTION:?set AZ_SUBSCRIPTION to the Sequrin - Development subscription ID}"
GH_TOKEN="${GH_TOKEN:?set GH_TOKEN to a fine-grained PAT (contents:read+write on this repo)}"
PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${GCP_REGION:-europe-west1}"

REPO=Sbusiso-Mdingi/jse-risk-management
APP_NAME=gh-jse-risk-refit            # existing app; reused, Contributor already granted
AR_REPO=portfolio-refit               # Artifact Registry docker repo
IMAGE_NAME=jse-risk-refit
JOB=jse-risk-refit
SA_NAME=jse-risk-refit
SECRET=jse-risk-github-pat
SCHEDULE="0 4 5 * *"                  # same cron as the old workflow
AUDIENCE="api://AzureADTokenExchange"

SA="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${AR_REPO}/${IMAGE_NAME}:latest"

echo "Project ${PROJECT} / region ${REGION}; deploying to subscription ${SUB}."

echo "==> Enabling APIs"
gcloud services enable --project "$PROJECT" \
  run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com secretmanager.googleapis.com iamcredentials.googleapis.com

echo "==> Artifact Registry"
gcloud artifacts repositories describe "$AR_REPO" --project "$PROJECT" --location "$REGION" >/dev/null 2>&1 \
  || gcloud artifacts repositories create "$AR_REPO" --project "$PROJECT" --location "$REGION" \
       --repository-format=docker --description="Portfolio monthly-refit images"

echo "==> Service account"
gcloud iam service-accounts describe "$SA" --project "$PROJECT" >/dev/null 2>&1 \
  || gcloud iam service-accounts create "$SA_NAME" --project "$PROJECT" \
       --display-name="JSE risk monthly refit (Cloud Run)"
SA_SUBJECT="$(gcloud iam service-accounts describe "$SA" --project "$PROJECT" --format='value(uniqueId)')"

echo "==> GitHub token secret"
if ! gcloud secrets describe "$SECRET" --project "$PROJECT" >/dev/null 2>&1; then
  printf '%s' "$GH_TOKEN" | gcloud secrets create "$SECRET" --project "$PROJECT" --data-file=- --replication-policy=automatic
else
  printf '%s' "$GH_TOKEN" | gcloud secrets versions add "$SECRET" --project "$PROJECT" --data-file=-
fi
gcloud secrets add-iam-policy-binding "$SECRET" --project "$PROJECT" \
  --member="serviceAccount:${SA}" --role=roles/secretmanager.secretAccessor >/dev/null

echo "==> Build image in Cloud Build"
gcloud builds submit --project "$PROJECT" --region "$REGION" \
  --tag "$IMAGE" --file deploy/cloudrun/Dockerfile .

echo "==> Azure identity details (not written to any tracked file)"
TENANT="$(az account show --subscription "$SUB" --query tenantId -o tsv)"
APP="$(az ad app list --display-name "$APP_NAME" --query '[0].appId' -o tsv)"
[ -n "$APP" ] || { echo "ERROR: run deploy/github-identity.sh first; app $APP_NAME not found." >&2; exit 1; }

echo "==> Azure federated credential for this job's Google identity"
if ! az ad app federated-credential list --id "$APP" --query "[?name=='gcp-cloud-run'] | [0].name" -o tsv | grep -q gcp-cloud-run; then
  az ad app federated-credential create --id "$APP" -o none --parameters "{
    \"name\": \"gcp-cloud-run\",
    \"issuer\": \"https://accounts.google.com\",
    \"subject\": \"${SA_SUBJECT}\",
    \"audiences\": [\"${AUDIENCE}\"]
  }"
fi

echo "==> Cloud Run job"
gcloud run jobs deploy "$JOB" --project "$PROJECT" --region "$REGION" \
  --image "$IMAGE" --service-account "$SA" \
  --max-retries 1 --task-timeout 3600 --cpu 2 --memory 4Gi \
  --set-env-vars "GH_REPO=${REPO},GH_REF=main,AZURE_CLIENT_ID=${APP},AZURE_TENANT_ID=${TENANT},AZ_SUBSCRIPTION=${SUB},AZURE_AUDIENCE=${AUDIENCE}" \
  --set-secrets "GH_TOKEN=${SECRET}:latest"

echo "==> Cloud Scheduler (monthly)"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${SA}" --role=roles/run.developer >/dev/null
RUN_URL="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/${JOB}:run"
if gcloud scheduler jobs describe "${JOB}-monthly" --project "$PROJECT" --location "$REGION" >/dev/null 2>&1; then
  VERB=update
else
  VERB=create
fi
gcloud scheduler jobs "$VERB" http "${JOB}-monthly" --project "$PROJECT" --location "$REGION" \
  --schedule="$SCHEDULE" --time-zone="Africa/Johannesburg" \
  --uri="$RUN_URL" --http-method=POST \
  --oauth-service-account-email="$SA"

echo
echo "Done. Trigger a run now with:"
echo "  gcloud run jobs execute ${JOB} --project ${PROJECT} --region ${REGION}"
