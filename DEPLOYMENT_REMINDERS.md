# Appointment Reminders Deployment Guide

## Overview
This guide covers deploying the automated appointment reminder system to production.

## Prerequisites
- Database access (Cloud SQL)
- Twilio SMS configured
- Cloud Run service deployed

## Step 1: Run Database Migration

### Option A: Via API Endpoint (Recommended)
Call the setup endpoint to run migration and create templates:

```bash
curl -X POST https://capturecare-310697189983.australia-southeast2.run.app/api/reminders/setup \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Or visit in browser (if logged in):
```
https://capturecare-310697189983.australia-southeast2.run.app/api/reminders/setup
```

### Option B: Direct SQL (Alternative)
If you have direct database access, run:

```sql
ALTER TABLE appointments 
ADD COLUMN IF NOT EXISTS reminder_24hr_sent BOOLEAN DEFAULT FALSE;

ALTER TABLE appointments 
ADD COLUMN IF NOT EXISTS reminder_24hr_sent_at TIMESTAMP;

ALTER TABLE appointments 
ADD COLUMN IF NOT EXISTS reminder_day_before_sent BOOLEAN DEFAULT FALSE;

ALTER TABLE appointments 
ADD COLUMN IF NOT EXISTS reminder_day_before_sent_at TIMESTAMP;

ALTER TABLE appointments 
ADD COLUMN IF NOT EXISTS reminder_1hr_sent BOOLEAN DEFAULT FALSE;

ALTER TABLE appointments 
ADD COLUMN IF NOT EXISTS reminder_1hr_sent_at TIMESTAMP;
```

## Step 2: Create Reminder Templates

The setup endpoint (Step 1) also creates the default SMS templates. If you need to create them manually:

1. Log into the admin interface
2. Go to Settings
3. Navigate to Notification Templates
4. Create templates:
   - `appointment_reminder_24hr` (SMS type)
   - `appointment_reminder_day_before` (SMS type)

Or they will be created automatically by the `/api/reminders/setup` endpoint.

## Step 3: Set Up Cloud Scheduler

### Automatic Setup (Recommended)
Run the setup script:

```bash
./scripts/setup_cloud_scheduler.sh
```

### Manual Setup
Create Cloud Scheduler job:

```bash
gcloud scheduler jobs create http appointment-reminders-check \
  --project=capturecare-461801 \
  --location=australia-southeast2 \
  --schedule="*/15 * * * *" \
  --uri="https://capturecare-310697189983.australia-southeast2.run.app/api/reminders/check" \
  --http-method=POST \
  --headers="Content-Type=application/json" \
  --time-zone="Australia/Sydney" \
  --description="Check and send appointment reminders every 15 minutes" \
  --attempt-deadline=300s
```

**Note:** The endpoint requires authentication. You may need to:
1. Make the endpoint publicly accessible (not recommended for production)
2. Use Cloud Scheduler with service account authentication
3. Add authentication token to the request

### Update Endpoint to Support Cloud Scheduler

If you need to allow Cloud Scheduler to call without authentication, you can add a special header check:

```python
# In web_dashboard.py, modify check_reminders endpoint
# Add check for Cloud Scheduler service account or special header
```

## Step 4: Test the System

### Manual Test
1. Create a test appointment 25 hours in the future
2. Call the reminder check endpoint:
   ```bash
   curl -X POST https://capturecare-310697189983.australia-southeast2.run.app/api/reminders/check \
     -H "Content-Type: application/json"
   ```
3. Verify SMS was sent
4. Check reminder status:
   ```bash
   curl https://capturecare-310697189983.australia-southeast2.run.app/api/reminders/status/APPOINTMENT_ID
   ```

### Verify Reminder Status
Check an appointment's reminder status:
```
GET /api/reminders/status/<appointment_id>
```

## Step 5: Monitor

### Check Cloud Scheduler Logs
```bash
gcloud scheduler jobs describe appointment-reminders-check \
  --location=australia-southeast2 \
  --project=capturecare-461801
```

### Check Application Logs
View Cloud Run logs for reminder activity:
```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=capturecare" \
  --limit 50 \
  --format json \
  --project=capturecare-461801
```

## Configuration

### Reminder Timing
- **24-hour reminder**: Sent 24 hours before appointment (23.5-24.5 hour window)
- **Day-before reminder**: Sent at 6:00 PM the day before appointment
- **Check frequency**: Every 15 minutes

### Reminder Rules
- Only sends for appointments with `status='scheduled'`
- Skips if patient has no phone number
- Skips if reminder already sent
- Skips if appointment is in the past

## Troubleshooting

### Reminders Not Sending
1. Check Twilio configuration in Settings
2. Verify patient has phone number
3. Check appointment status is 'scheduled'
4. Verify Cloud Scheduler job is running
5. Check application logs for errors

### Cloud Scheduler Authentication Issues
If Cloud Scheduler can't authenticate:
1. Grant Cloud Scheduler service account access to Cloud Run
2. Or add authentication bypass for scheduler requests (with security header)

### Database Migration Issues
If migration fails:
1. Check database connection
2. Verify you have ALTER TABLE permissions
3. Check if columns already exist (safe to run multiple times)

## Rollback

If you need to rollback:
1. Disable Cloud Scheduler job:
   ```bash
   gcloud scheduler jobs pause appointment-reminders-check \
     --location=australia-southeast2 \
     --project=capturecare-461801
   ```
2. The reminder fields in the database are safe to leave (they don't affect existing functionality)
3. To fully remove, drop the columns (not recommended - data loss)

## Support

For issues or questions:
- Check application logs
- Verify Twilio SMS is working
- Test reminder endpoint manually
- Check Cloud Scheduler job status

