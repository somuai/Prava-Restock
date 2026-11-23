#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project)}"
REGION="${GCP_REGION:-asia-south1}"
SERVICE_NAME="prava-restock"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest"

echo "============================================================"
echo "Deploying ${SERVICE_NAME} to Google Cloud Run"
echo "Project: ${PROJECT_ID} | Region: ${REGION}"
echo "============================================================"

# 1. Build and push container via Google Cloud Build
echo "[1/3] Building container image via Cloud Build..."
gcloud builds submit --project="${PROJECT_ID}" --tag="${IMAGE_NAME}" .

# 2. Render Knative deployment manifest
echo "[2/3] Preparing Knative Cloud Run manifest..."
TMP_MANIFEST=$(mktemp)
sed -e "s/\${GCP_PROJECT_ID}/${PROJECT_ID}/g" \
    -e "s/\${GCP_REGION}/${REGION}/g" \
    deploy/gcp/cloudrun-service.yaml > "${TMP_MANIFEST}"

# 3. Apply deployment manifest
echo "[3/3] Deploying to Cloud Run..."
gcloud run services replace "${TMP_MANIFEST}" --project="${PROJECT_ID}" --region="${REGION}"
rm -f "${TMP_MANIFEST}"

echo "Deployment complete."
gcloud run services describe "${SERVICE_NAME}" --project="${PROJECT_ID}" --region="${REGION}" --format="value(status.url)"
