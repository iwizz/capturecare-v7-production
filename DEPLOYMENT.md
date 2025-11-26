# CaptureCare V7 - Google Cloud Deployment Guide

## Prerequisites

1. **Google Cloud Project**: `capturecare-461801`
2. **GitHub Repository**: `https://github.com/iwizz/capturecare-v7-production`
3. **Required APIs Enabled**:
   - Cloud Build API
   - Cloud Run API
   - Cloud SQL Admin API
   - Secret Manager API
   - Cloud Storage API

## Deployment Steps

### 1. Set Up Cloud SQL Database

```bash
# Create Cloud SQL instance (if it doesn't exist)
gcloud sql instances create capturecare-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=australia-southeast2 \
  --root-password=YOUR_ROOT_PASSWORD

# Create database
gcloud sql databases create capturecare --instance=capturecare-db

# Create database user
gcloud sql users create capturecare \
  --instance=capturecare-db \
  --password=YOUR_DB_PASSWORD
```

### 2. Set Up Cloud Storage Bucket

```bash
# Create bucket (if it doesn't exist)
gsutil mb -p capturecare-461801 -l australia-southeast2 gs://capturecare-v7-storage

# Upload client_secrets.json (if needed)
gsutil cp client_secrets.json gs://capturecare-v7-storage/
```

### 3. Set Up Secret Manager

All API keys and credentials should be stored in Google Cloud Secret Manager:

```bash
# Set secrets (replace with your actual values)
gcloud secrets create withings-client-id --data-file=- <<< "YOUR_WITHINGS_CLIENT_ID"
gcloud secrets create withings-client-secret --data-file=- <<< "YOUR_WITHINGS_CLIENT_SECRET"
gcloud secrets create cliniko-api-key --data-file=- <<< "YOUR_CLINIKO_API_KEY"
gcloud secrets create cliniko-shard --data-file=- <<< "au4"
gcloud secrets create openai-api-key --data-file=- <<< "YOUR_OPENAI_API_KEY"
gcloud secrets create xai-api-key --data-file=- <<< "YOUR_XAI_API_KEY"
gcloud secrets create heygen-api-key --data-file=- <<< "YOUR_HEYGEN_API_KEY"
gcloud secrets create twilio-account-sid --data-file=- <<< "YOUR_TWILIO_ACCOUNT_SID"
gcloud secrets create twilio-auth-token --data-file=- <<< "YOUR_TWILIO_AUTH_TOKEN"
gcloud secrets create twilio-phone-number --data-file=- <<< "YOUR_TWILIO_PHONE_NUMBER"
gcloud secrets create smtp-server --data-file=- <<< "smtp.gmail.com"
gcloud secrets create smtp-port --data-file=- <<< "587"
gcloud secrets create smtp-username --data-file=- <<< "YOUR_SMTP_USERNAME"
gcloud secrets create smtp-password --data-file=- <<< "YOUR_SMTP_PASSWORD"
gcloud secrets create smtp-from-email --data-file=- <<< "YOUR_SMTP_FROM_EMAIL"
```

### 4. Set Up Cloud Build Trigger

```bash
# Connect GitHub repository to Cloud Build
gcloud builds triggers create github \
  --name="capturecare-deploy" \
  --repo-name="capturecare-v7-production" \
  --repo-owner="iwizz" \
  --branch-pattern="^main$" \
  --build-config="cloudbuild.yaml"
```

### 5. Manual Deployment (Alternative)

If you prefer to deploy manually:

```bash
# Build and push image
gcloud builds submit --config cloudbuild.yaml

# Or deploy directly
gcloud run deploy capturecare \
  --source . \
  --region australia-southeast2 \
  --platform managed \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --max-instances 10 \
  --set-env-vars "USE_SECRET_MANAGER=true,GCP_PROJECT_ID=capturecare-461801,USE_CLOUD_STORAGE=true,GCS_BUCKET_NAME=capturecare-v7-storage" \
  --add-cloudsql-instances "capturecare-461801:australia-southeast2:capturecare-db"
```

### 6. Set BASE_URL for Video Rooms

After deployment, set the BASE_URL environment variable to your Cloud Run URL:

```bash
gcloud run services update capturecare \
  --region australia-southeast2 \
  --update-env-vars "BASE_URL=https://capturecare-XXXXX.a.run.app"
```

Replace `XXXXX` with your actual Cloud Run service URL.

## Post-Deployment

1. **Initialize Database**: Run migrations to set up the database schema
2. **Create Admin User**: Use the admin creation script
3. **Test Video Rooms**: Verify that patient join links work with the public URL
4. **Monitor Logs**: Check Cloud Run logs for any errors

## Troubleshooting

- **Database Connection Issues**: Ensure Cloud SQL instance is running and Cloud Run has proper IAM permissions
- **Secret Manager Access**: Verify Cloud Run service account has Secret Manager access
- **Storage Access**: Ensure Cloud Run service account has Storage access
- **Video Room Links**: Make sure BASE_URL is set correctly in environment variables

## Useful Commands

```bash
# View Cloud Run service
gcloud run services describe capturecare --region australia-southeast2

# View logs
gcloud run services logs read capturecare --region australia-southeast2

# Update environment variables
gcloud run services update capturecare --region australia-southeast2 --update-env-vars "KEY=VALUE"

# Get service URL
gcloud run services describe capturecare --region australia-southeast2 --format="value(status.url)"
```

