#!/usr/bin/env bash
# One-off: stand up the monthly refit on Google Cloud Run instead of GitHub
# Actions. GitHub stays the home of the code and where results are pushed; this
# only moves the scheduled compute.
#
# Run it like github-identity.sh:
#   AZ_SUBSCRIPTION=<dev-subscription-id> bash deploy/cloudrun/provision.sh
#
# No GitHub token and no Azure secret are stored. Pushes use a per-repo SSH
# deploy key: generated here, the public half registered on this repo (write)
# and the private half kept in Secret Manager and mounted into the job. Azure
# trusts the job's Google identity token via federation, reusing the Contributor
# grant the existing refit app already has on the previews group.
set -euo pipefail

SUB="${AZ_SUBSCRIPTION:?set AZ_SUBSCRIPTION to the Sequrin - Development subscription ID}"
PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${GCP_REGION:-europe-west1}"

REPO=Sbusiso-Mdingi/jse-risk-management
APP_NAME=gh-jse-risk-refit            # existing app; reused, Contributor already granted
AR_REPO=portfolio-refit               # Artifact Registry docker repo
IMAGE_NAME=jse-risk-refit
JOB=jse-risk-refit
SA_NAME=jse-risk-refit
SECRET=jse-risk-deploy-key
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

echo "==> Cloud Build builder permissions"
# New projects run Cloud Build as the Compute Engine default service account; it
# needs the builder role to read the source upload and push to Artifact Registry.
PNUM="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${PNUM}-compute@developer.gserviceaccount.com" \
  --role=roles/cloudbuild.builds.builder >/dev/null

echo "==> Service account"
gcloud iam service-accounts describe "$SA" --project "$PROJECT" >/dev/null 2>&1 \
  || gcloud iam service-accounts create "$SA_NAME" --project "$PROJECT" \
       --display-name="JSE risk monthly refit (Cloud Run)"
# A freshly created SA is eventually consistent; wait for it to become visible.
SA_SUBJECT=""
for _ in 1 2 3 4 5 6; do
  SA_SUBJECT="$(gcloud iam service-accounts describe "$SA" --project "$PROJECT" --format='value(uniqueId)' 2>/dev/null || true)"
  [ -n "$SA_SUBJECT" ] && break
  sleep 5
done
[ -n "$SA_SUBJECT" ] || { echo "ERROR: service account $SA not visible yet; re-run." >&2; exit 1; }

echo "==> SSH deploy key (push auth; no token stored)"
if ! gcloud secrets describe "$SECRET" --project "$PROJECT" >/dev/null 2>&1; then
  k="$(mktemp -u)"
  ssh-keygen -t ed25519 -N '' -C cloud-run-refit -f "$k" >/dev/null
  gh api --method POST "repos/${REPO}/keys" -f title=cloud-run-refit \
    -f key="$(cat "$k.pub")" -F read_only=false >/dev/null
  gcloud secrets create "$SECRET" --project "$PROJECT" --replication-policy=automatic --data-file="$k"
  rm -f "$k" "$k.pub"
fi
gcloud secrets add-iam-policy-binding "$SECRET" --project "$PROJECT" \
  --member="serviceAccount:${SA}" --role=roles/secretmanager.secretAccessor >/dev/null

echo "==> Build image in Cloud Build"
cfg="$(mktemp).yaml"
cat > "$cfg" <<YAML
steps:
- name: gcr.io/cloud-builders/docker
  args: ["build","-t","${IMAGE}","-f","deploy/cloudrun/Dockerfile","."]
images: ["${IMAGE}"]
options:
  logging: CLOUD_LOGGING_ONLY
YAML
gcloud builds submit --project "$PROJECT" --region "$REGION" --config "$cfg" .
rm -f "$cfg"

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
  --set-secrets "/secrets/deploy_key=${SECRET}:latest"

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
