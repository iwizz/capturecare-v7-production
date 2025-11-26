# ✅ Database Migration Ready!

## What's Been Set Up

✅ **Migration Script**: `scripts/migrate_to_cloud_sql.py`  
✅ **Migration Guide**: `scripts/MIGRATION_GUIDE.md`  
✅ **Quick Migration Script**: `scripts/quick_migrate.sh`  
✅ **Cloud SQL Proxy**: Downloaded and ready

## Your Data to Migrate

- **7 Users** (doctors, practitioners, etc.)
- **7 Patients**
- **67 Appointments**
- **34,136 Health Data records**
- **31 Patient Notes**
- Plus: devices, target ranges, invoices, correspondence, etc.

## Quick Start - Run Migration Now

### Option 1: Quick Script (Easiest)

```bash
cd "/Users/timhook/Library/Mobile Documents/com~apple~CloudDocs/GitCode/Capture Care Replit Version"
./scripts/quick_migrate.sh
```

This script will:
1. Start Cloud SQL Proxy automatically
2. Prompt for database password
3. Test the connection
4. Run the migration
5. Clean up when done

### Option 2: Manual Steps

1. **Get Database Password**:
   - If you don't know it, reset it:
   ```bash
   gcloud sql users set-password capturecare \
     --instance=capturecare-db \
     --password=YOUR_NEW_PASSWORD
   ```

2. **Start Cloud SQL Proxy** (Terminal 1):
   ```bash
   cd "/Users/timhook/Library/Mobile Documents/com~apple~CloudDocs/GitCode/Capture Care Replit Version"
   ./cloud-sql-proxy capturecare-461801:australia-southeast2:capturecare-db --port=5432
   ```
   Keep this running!

3. **Run Migration** (Terminal 2):
   ```bash
   cd "/Users/timhook/Library/Mobile Documents/com~apple~CloudDocs/GitCode/Capture Care Replit Version"
   
   # Set connection string (replace YOUR_PASSWORD)
   export DATABASE_URL="postgresql://capturecare:YOUR_PASSWORD@127.0.0.1:5432/capturecare"
   
   # Install psycopg2 if needed
   pip install psycopg2-binary
   
   # Run migration
   python3 scripts/migrate_to_cloud_sql.py
   ```

## What Gets Migrated

The migration script will transfer all data from SQLite to PostgreSQL, including:

- ✅ Users (doctors, practitioners, admins)
- ✅ Patients (all patient records)
- ✅ Appointments (67 appointments)
- ✅ Health Data (34,136+ records)
- ✅ Patient Notes (31 notes)
- ✅ Devices (Withings devices)
- ✅ Target Ranges (health targets)
- ✅ Invoices & Invoice Items
- ✅ Patient Correspondence
- ✅ Availability Patterns & Exceptions
- ✅ Webhook Logs

All relationships and foreign keys are preserved!

## After Migration

1. **Verify Data**:
   ```bash
   gcloud sql connect capturecare-db --user=capturecare --database=capturecare
   # Then run: SELECT COUNT(*) FROM users; etc.
   ```

2. **Test Application**:
   - Visit: https://capturecare-310697189983.australia-southeast2.run.app
   - Login with your existing credentials
   - Verify all data is visible

3. **Update Cloud Run** (if needed):
   - The Cloud Run service should already be configured to use Cloud SQL
   - Verify the DATABASE_URL environment variable is set correctly

## Troubleshooting

### "Connection refused"
- Make sure Cloud SQL Proxy is running
- Check that it's listening on port 5432

### "Authentication failed"
- Verify the password is correct
- Try resetting the password:
  ```bash
  gcloud sql users set-password capturecare --instance=capturecare-db --password=NEW_PASSWORD
  ```

### "psycopg2 not found"
- Install it: `pip install psycopg2-binary`

### Migration takes a long time
- This is normal! With 34K+ health data records, it may take 5-10 minutes
- The script shows progress for each table

## Backup

Your local SQLite database is safe and will remain unchanged. The migration only **copies** data, it doesn't delete anything from SQLite.

---

**Ready to migrate?** Run: `./scripts/quick_migrate.sh`

