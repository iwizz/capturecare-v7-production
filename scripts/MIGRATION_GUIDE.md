# Database Migration Guide - SQLite to Cloud SQL

## Overview

This guide will help you migrate all data from your local SQLite database to Google Cloud SQL PostgreSQL.

## Prerequisites

1. **Cloud SQL Instance**: `capturecare-db` (already exists)
2. **Database**: `capturecare` (already exists)
3. **Database User**: `capturecare` (already exists)
4. **Local SQLite Database**: `capturecare/instance/capturecare.db`

## Current Data Counts

- **Users**: 7
- **Patients**: 7
- **Appointments**: 67
- **Health Data**: 34,136 records
- **Notes**: 31

## Migration Methods

### Method 1: Using Cloud SQL Proxy (Recommended)

1. **Install Cloud SQL Proxy** (if not already installed):
   ```bash
   # macOS
   curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.8.0/cloud-sql-proxy.darwin.arm64
   chmod +x cloud-sql-proxy
   ```

2. **Start Cloud SQL Proxy** (in a separate terminal):
   ```bash
   ./cloud-sql-proxy capturecare-461801:australia-southeast2:capturecare-db \
     --port=5432
   ```

3. **Get Database Password**:
   ```bash
   # You'll need the database password
   # It's stored in Secret Manager or you can reset it:
   gcloud sql users set-password capturecare \
     --instance=capturecare-db \
     --password=YOUR_NEW_PASSWORD
   ```

4. **Set Environment Variable**:
   ```bash
   export DATABASE_URL="postgresql://capturecare:YOUR_PASSWORD@127.0.0.1:5432/capturecare"
   ```

5. **Run Migration Script**:
   ```bash
   cd "/Users/timhook/Library/Mobile Documents/com~apple~CloudDocs/GitCode/Capture Care Replit Version"
   python3 scripts/migrate_to_cloud_sql.py
   ```

### Method 2: Using Cloud Run Job (Alternative)

1. **Create a Cloud Run Job** that runs the migration script
2. **Connect directly to Cloud SQL** from Cloud Run (no proxy needed)
3. **Execute the job** to migrate data

### Method 3: Manual SQL Export/Import

1. **Export from SQLite**:
   ```bash
   sqlite3 capturecare/instance/capturecare.db .dump > migration.sql
   ```

2. **Convert SQLite SQL to PostgreSQL** (requires manual editing)

3. **Import to PostgreSQL** via Cloud SQL

## Step-by-Step: Method 1 (Recommended)

### Step 1: Install Cloud SQL Proxy

```bash
# Download for macOS ARM64 (M1/M2)
curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.8.0/cloud-sql-proxy.darwin.arm64
chmod +x cloud-sql-proxy
sudo mv cloud-sql-proxy /usr/local/bin/
```

### Step 2: Get Database Password

If you don't know the password, you can reset it:

```bash
gcloud sql users set-password capturecare \
  --instance=capturecare-db \
  --password=YOUR_SECURE_PASSWORD
```

### Step 3: Start Proxy (Terminal 1)

```bash
cloud-sql-proxy capturecare-461801:australia-southeast2:capturecare-db \
  --port=5432
```

Keep this terminal running!

### Step 4: Run Migration (Terminal 2)

```bash
cd "/Users/timhook/Library/Mobile Documents/com~apple~CloudDocs/GitCode/Capture Care Replit Version"

# Set connection string
export DATABASE_URL="postgresql://capturecare:YOUR_PASSWORD@127.0.0.1:5432/capturecare"

# Activate virtual environment (if using one)
source venv/bin/activate

# Install psycopg2 if needed
pip install psycopg2-binary

# Run migration
python3 scripts/migrate_to_cloud_sql.py
```

### Step 5: Verify Migration

After migration completes, verify the data:

```bash
# Connect to Cloud SQL
gcloud sql connect capturecare-db --user=capturecare --database=capturecare

# Run queries to verify
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM patients;
SELECT COUNT(*) FROM appointments;
SELECT COUNT(*) FROM health_data;
SELECT COUNT(*) FROM patient_notes;
```

## Troubleshooting

### Connection Issues

- **"Connection refused"**: Make sure Cloud SQL Proxy is running
- **"Authentication failed"**: Check username and password
- **"Database does not exist"**: Verify database name is `capturecare`

### Data Issues

- **Foreign key violations**: The script handles dependencies, but if issues occur, check the migration order
- **Duplicate key errors**: The script uses `ON CONFLICT DO NOTHING` to skip duplicates
- **Data type mismatches**: Some SQLite types may need conversion

### Performance

- Large tables (like health_data with 34K+ rows) may take a few minutes
- The script processes in batches of 1000 rows
- Monitor progress in the console output

## Post-Migration

1. **Verify all data** migrated correctly
2. **Test the application** on Cloud Run
3. **Update any hardcoded references** to use Cloud SQL
4. **Backup the Cloud SQL database**:
   ```bash
   gcloud sql export sql capturecare-db \
     gs://capturecare-v7-storage/backups/migration-$(date +%Y%m%d).sql \
     --database=capturecare
   ```

## Rollback Plan

If something goes wrong:

1. **Stop Cloud Run service** (if needed)
2. **Restore from backup** or re-run migration
3. **Check logs** for specific errors
4. **Contact support** if needed

---

**Note**: Make sure to keep your local SQLite database as a backup until you've verified everything works correctly in production!

