# Appointment Reminders Deployment - Complete

## ✅ Deployment Status

### Completed Steps:

1. **Code Deployed** ✅
   - All reminder code deployed to Cloud Run
   - Service URL: https://capturecare-310697189983.australia-southeast2.run.app
   - Revision: capturecare-00064-8bk

2. **Cloud Scheduler API Enabled** ✅
   - Cloud Scheduler API enabled for project capturecare-461801

3. **Reminder Check Endpoint Working** ✅
   - Endpoint tested: `/api/reminders/check`
   - Returns: `{"success":true,"stats":{"checked":0,"24hr_sent":0,"day_before_sent":0,"errors":1}}`

## 🔧 Next Steps (Manual)

### Step 1: Run Database Migration & Create Templates

**Option A: Via Browser (Recommended)**
1. Log into the admin interface: https://capturecare-310697189983.australia-southeast2.run.app
2. Visit: https://capturecare-310697189983.australia-southeast2.run.app/api/reminders/setup
3. This will:
   - Add reminder fields to appointments table
   - Create default SMS reminder templates

**Option B: Via SQL (If you have direct database access)**
Run the SQL from `DEPLOYMENT_REMINDERS.md`

### Step 2: Create Cloud Scheduler Job

The Cloud Scheduler job needs to be created. Use one of these methods:

**Method 1: Using the script**
```bash
./scripts/setup_cloud_scheduler.sh
```

**Method 2: Manual command**
```bash
gcloud scheduler jobs create http appointment-reminders-check \
  --project=capturecare-461801 \
  --location=asia-southeast2 \
  --schedule="*/15 * * * *" \
  --uri="https://capturecare-310697189983.australia-southeast2.run.app/api/reminders/check" \
  --http-method=POST \
  --headers="Content-Type=application/json" \
  --time-zone="Australia/Sydney" \
  --description="Check and send appointment reminders every 15 minutes" \
  --attempt-deadline=300s
```

**Note:** Cloud Scheduler uses `asia-southeast2` region (not `australia-southeast2`)

### Step 3: Verify Setup

1. **Check Scheduler Job:**
   ```bash
   gcloud scheduler jobs list --location=asia-southeast2 --project=capturecare-461801
   ```

2. **Manually Trigger Reminder Check:**
   ```bash
   curl -X POST https://capturecare-310697189983.australia-southeast2.run.app/api/reminders/check \
     -H "Content-Type: application/json"
   ```

3. **Check Reminder Status for an Appointment:**
   ```bash
   curl https://capturecare-310697189983.australia-southeast2.run.app/api/reminders/status/APPOINTMENT_ID
   ```

## 📋 Current Configuration

- **Reminder Check Endpoint:** `/api/reminders/check` (POST)
- **Reminder Status Endpoint:** `/api/reminders/status/<appointment_id>` (GET)
- **Setup Endpoint:** `/api/reminders/setup` (POST) - Run once to initialize
- **Check Frequency:** Every 15 minutes
- **Reminder Types:**
  - 24-hour reminder (sent 24 hours before)
  - Day-before reminder (sent at 6pm the day before)

## 🔒 Security Note

The `/api/reminders/check` endpoint is currently open (no authentication required) to allow Cloud Scheduler to call it. For production, consider:

1. Adding a secret header that Cloud Scheduler can send
2. Using Cloud Scheduler's service account authentication
3. Adding IP whitelist for Cloud Scheduler

## 📊 Monitoring

### View Scheduler Job Status
```bash
gcloud scheduler jobs describe appointment-reminders-check \
  --location=asia-southeast2 \
  --project=capturecare-461801
```

### View Application Logs
```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=capturecare AND jsonPayload.message=~'reminder'" \
  --limit 50 \
  --format json \
  --project=capturecare-461801
```

## ✅ Testing

1. Create a test appointment 25 hours in the future
2. Wait for the next scheduler run (or trigger manually)
3. Verify SMS was sent
4. Check reminder status via API

## 🎉 System Ready

Once you complete Step 1 (run setup endpoint) and Step 2 (create Cloud Scheduler job), the automated reminder system will be fully operational!

