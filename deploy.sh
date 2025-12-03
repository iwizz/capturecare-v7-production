#!/bin/bash

# CaptureCare Deployment Script
# Always deploys to the correct project: capturecare-461801

set -e

PROJECT_ID="capturecare-461801"
REGION="australia-southeast2"
SERVICE_NAME="capturecare"

echo "🚀 Deploying CaptureCare to Cloud Run..."
echo "   Project: $PROJECT_ID"
echo "   Region: $REGION"
echo "   Service: $SERVICE_NAME"
echo ""

# Set the project
gcloud config set project $PROJECT_ID

# Deploy
gcloud run deploy $SERVICE_NAME \
  --source . \
  --region $REGION \
  --project $PROJECT_ID

echo ""
echo "✅ Deployment complete!"
echo "   Service URL: https://capturecare-310697189983.australia-southeast2.run.app"
echo ""

