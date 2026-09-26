#!/usr/bin/env bash
set -euo pipefail

# Configuration defaults
PROJECT_ID="${GCP_PROJECT_ID:-project-dd21ce0e-1dd3-476c-af0}"
REGION="${GCP_REGION:-europe-west4}"
SERVICE_NAME="${CLOUD_RUN_SERVICE:-tm-bingo}"
REPO_NAME="tm-bingo-repo"
IMAGE_TAG="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:latest"
SERVICE_ACCOUNT="tm-bingo-runner@${PROJECT_ID}.iam.gserviceaccount.com"

echo "=== Deploying ${SERVICE_NAME} to Google Cloud Run ==="
echo "Project:  ${PROJECT_ID}"
echo "Region:   ${REGION}"
echo "Image:    ${IMAGE_TAG}"
echo "Service:  ${SERVICE_NAME}"
echo ""

# 1. Build and push image via Cloud Build
echo "--> [1/2] Building container image with Cloud Build..."
CLOUDSDK_METRICS_ENVIRONMENT=datacloud.antigravity gcloud builds submit \
  --project="${PROJECT_ID}" \
  --tag="${IMAGE_TAG}" \
  --quiet

# 2. Deploy to Cloud Run
echo "--> [2/2] Deploying container image to Cloud Run..."
CLOUDSDK_METRICS_ENVIRONMENT=datacloud.antigravity gcloud run deploy "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --image="${IMAGE_TAG}" \
  --platform=managed \
  --region="${REGION}" \
  --allow-unauthenticated \
  --port=8080 \
  --max-instances=1 \
  --timeout=3600 \
  --service-account="${SERVICE_ACCOUNT}" \
  --set-secrets="BASIC_AUTH=tm-bingo-basic-auth:latest,APP_PASSWORD_HASH=tm-bingo-password-hash:latest" \
  --quiet

# Retrieve deployed service URL
SERVICE_URL=$(CLOUDSDK_METRICS_ENVIRONMENT=datacloud.antigravity gcloud run services describe "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format="value(status.url)")

echo ""
echo "=== Deployment Successful ==="
echo "Service URL: ${SERVICE_URL}"
echo "Short URL:   https://shorturl.fm/tm-bingo"
