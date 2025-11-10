#!/bin/bash

# deploy.sh - Deploy Makistry using Cloud Build + buildpacks

set -e  # Exit on any error

# Configuration
PROJECT_ID="indigo-night-463419-r0"
REGION="us-central1"
REPO="cr"
SERVICE_NAME="makistry"
SHA=$(git rev-parse --short HEAD || date +%s)
IMAGE="us-central1-docker.pkg.dev/$PROJECT_ID/$REPO/makistry:$SHA"

echo "🚀 Starting Makistry deployment..."
echo "📦 Image: $IMAGE"

# Check required tools
command -v gcloud >/dev/null 2>&1 || { echo "❌ gcloud CLI required"; exit 1; }
command -v firebase >/dev/null 2>&1 || { echo "❌ firebase CLI required"; exit 1; }

# Set active project
echo "📋 Setting GCP project to $PROJECT_ID..."
gcloud config set project $PROJECT_ID

# Enable required APIs
echo "🔧 Enabling required APIs..."
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable artifactregistry.googleapis.com

# Create Artifact Registry repository if it doesn't exist
echo "🏗️  Ensuring Artifact Registry repository exists..."
gcloud artifacts repositories create $REPO \
  --repository-format=docker \
  --location=$REGION \
  --project=$PROJECT_ID 2>/dev/null || echo "Repository already exists"

# Build using Cloud Build + buildpacks
echo "🏗️  Building with Cloud Build..."
gcloud builds submit \
  --pack image=$IMAGE,builder=gcr.io/buildpacks/builder:google-22,env=GOOGLE_PYTHON_VERSION=3.10.13 \
  --project=$PROJECT_ID

# Deploy to Cloud Run with ALL required environment variables
echo "🚀 Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE \
  --region $REGION \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --concurrency 100 \
  --max-instances 10 \
  --set-env-vars "\
ENVIRONMENT=production,\
FIREBASE_HOSTING_DOMAIN=indigo-night-463419-r0,\
GCP_PROJECT_ID=$PROJECT_ID,\
GCS_BUCKET=${PROJECT_ID}-storage,\
RESEND_API_KEY=placeholder-key,\
AZURE_OAI_ENDPOINT=https://placeholder.openai.azure.com/,\
AZURE_OAI_KEY=placeholder-key,\
AZURE_BSTORM_MODEL=gpt-4,\
AZURE_BSTORM_API_VERSION=2024-02-01,\
AZURE_BSTORM_EDIT_MODEL=gpt-4,\
AZURE_BSTORM_EDIT_API_VERSION=2024-02-01,\
AZURE_SIM_MODEL=gpt-4,\
AZURE_SIM_API_VERSION=2024-02-01,\
AZURE_SIM_EDIT_MODEL=gpt-4,\
AZURE_SIM_EDIT_API_VERSION=2024-02-01,\
AZURE_CODE_MODEL=gpt-4,\
AZURE_CODE_API_VERSION=2024-02-01,\
AZURE_CODE_EDIT_MODEL=gpt-4,\
AZURE_CODE_EDIT_API_VERSION=2024-02-01,\
AZURE_INTENT_MODEL=gpt-4,\
AZURE_INTENT_API_VERSION=2024-02-01,\
AZURE_CHAT_MODEL=gpt-4,\
AZURE_CHAT_API_VERSION=2024-02-01,\
COSMOS_ENDPOINT=https://placeholder.documents.azure.com:443/,\
COSMOS_KEY=placeholder-key,\
AZURE_BLOB_ACCOUNT_NAME=placeholder,\
AZURE_BLOB_ACCOUNT_KEY=placeholder-key,\
AZURE_BLOB_CONTAINER=placeholder" \
  --project=$PROJECT_ID

# Get the Cloud Run service URL
CLOUD_RUN_URL=$(gcloud run services describe $SERVICE_NAME --region $REGION --format 'value(status.url)' --project=$PROJECT_ID)
echo "✅ Cloud Run deployed at: $CLOUD_RUN_URL"

# Test the Cloud Run service
echo "🧪 Testing Cloud Run service..."
curl -f "$CLOUD_RUN_URL/" || {
  echo "❌ Cloud Run service health check failed"
  echo "📋 Recent logs:"
  gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE_NAME" --project=$PROJECT_ID --limit=10 --format="table(timestamp,severity,textPayload)"
  exit 1
}

curl -f "$CLOUD_RUN_URL/api" || {
  echo "❌ Cloud Run API endpoint failed"
  echo "📋 Recent logs:"
  gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE_NAME" --project=$PROJECT_ID --limit=10 --format="table(timestamp,severity,textPayload)"
  exit 1
}

echo "✅ Cloud Run service is healthy"

# Build frontend with correct API URL
echo "🎨 Building frontend..."
export VITE_API_URL="/api"  # Use relative path for Firebase Hosting rewrites
npm ci
npm run build

# Deploy to Firebase Hosting
echo "🔥 Deploying to Firebase Hosting..."
firebase deploy --only hosting --project $PROJECT_ID

# Get Firebase Hosting URL
HOSTING_URL="https://$PROJECT_ID.web.app"
echo "✅ Firebase Hosting deployed at: $HOSTING_URL"

# Final verification
echo "🔍 Final verification..."
sleep 10  # Wait for deployment to stabilize

# Test the full stack through Firebase Hosting
echo "Testing API through Firebase Hosting..."
curl -f "$HOSTING_URL/api" || {
  echo "❌ Firebase Hosting -> Cloud Run connection failed"
  echo "🔧 Check firebase.json rewrites configuration"
  echo "📋 Recent Cloud Run logs:"
  gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE_NAME" --project=$PROJECT_ID --limit=10 --format="table(timestamp,severity,textPayload)"
  exit 1
}

echo ""
echo "🎉 Deployment successful!"
echo "🌐 Frontend: $HOSTING_URL"
echo "⚙️  Backend: $CLOUD_RUN_URL"
echo "📦 Image: $IMAGE"
echo ""
echo "🔧 If issues persist, check logs with:"
echo "   gcloud logging read \"resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE_NAME\" --project=$PROJECT_ID --limit=20"