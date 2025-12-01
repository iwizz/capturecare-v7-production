#!/bin/bash
# Setup Cloud Scheduler for appointment reminders
# This script creates a Cloud Scheduler job to call the reminder check endpoint every 15 minutes

PROJECT_ID="capturecare-461801"
REGION="asia-southeast2"  # Cloud Scheduler uses asia-southeast2, not australia-southeast2
SERVICE_URL="https://capturecare-310697189983.australia-southeast2.run.app"
JOB_NAME="appointment-reminders-check"
SCHEDULE="*/15 * * * *"  # Every 15 minutes
ENDPOINT="/api/reminders/check"

echo "Setting up Cloud Scheduler for appointment reminders..."

# Create Cloud Scheduler job
gcloud scheduler jobs create http ${JOB_NAME} \
  --project=${PROJECT_ID} \
  --location=${REGION} \
  --schedule="${SCHEDULE}" \
  --uri="${SERVICE_URL}${ENDPOINT}" \
  --http-method=POST \
  --headers="Content-Type=application/json" \
  --time-zone="Australia/Sydney" \
  --description="Check and send appointment reminders every 15 minutes" \
  --attempt-deadline=300s \
  || echo "Job may already exist. Use 'gcloud scheduler jobs update' to modify."

echo "✅ Cloud Scheduler job created: ${JOB_NAME}"
echo "   Schedule: Every 15 minutes"
echo "   Endpoint: ${SERVICE_URL}${ENDPOINT}"
echo ""
echo "To manually trigger: gcloud scheduler jobs run ${JOB_NAME} --location=${REGION} --project=${PROJECT_ID}"
echo "To view logs: gcloud scheduler jobs describe ${JOB_NAME} --location=${REGION} --project=${PROJECT_ID}"

