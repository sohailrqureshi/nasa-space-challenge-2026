#!/usr/bin/env bash
# SELENE SCOUT — Cloud Run deployment script
# Target: Google Cloud Run, asia-southeast1
# Usage: ./deploy.sh [PROJECT_ID]

set -euo pipefail

PROJECT_ID="${1:-$(gcloud config get-value project)}"
SERVICE_NAME="selene-scout"
REGION="asia-southeast1"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${SERVICE_NAME}/${SERVICE_NAME}"

echo "▶ Deploying ${SERVICE_NAME} to Cloud Run (${REGION})…"
echo "  Project: ${PROJECT_ID}"

# Build and push image using Cloud Build
gcloud builds submit \
  --project "${PROJECT_ID}" \
  --tag "${IMAGE}" \
  .

# Deploy to Cloud Run
gcloud run deploy "${SERVICE_NAME}" \
  --project  "${PROJECT_ID}" \
  --image    "${IMAGE}" \
  --region   "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --min-instances 1 \
  --max-instances 10 \
  --memory   2Gi \
  --cpu      2 \
  --timeout  300 \
  --set-env-vars "GCP_PROJECT=${PROJECT_ID},GCP_LOCATION=global"

echo ""
echo "✓ Deployed! URL:"
gcloud run services describe "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region  "${REGION}" \
  --format  "value(status.url)"
