# PatientAuth Table Migration

The `PatientAuth` table is required for the iOS app invite feature. If you're getting "Service Unavailable" errors when sending invites, the table likely doesn't exist.

## Quick Fix: Run Migration Script

```bash
cd "/Users/timhook/Library/Mobile Documents/com~apple~CloudDocs/GitCode/Capture Care Replit Version"
python3 scripts/create_patient_auth_table.py
```

## Manual SQL (Cloud SQL PostgreSQL)

If the script doesn't work, run this SQL directly on your Cloud SQL database:

```sql
CREATE TABLE IF NOT EXISTS patient_auth (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER NOT NULL UNIQUE REFERENCES patients(id),
    auth_provider VARCHAR(20) NOT NULL,
    provider_user_id VARCHAR(200),
    email VARCHAR(120),
    password_hash VARCHAR(200),
    refresh_token VARCHAR(500),
    token_expires_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_patient_auth_patient_id ON patient_auth(patient_id);
CREATE INDEX IF NOT EXISTS idx_patient_auth_email ON patient_auth(email);
```

## How to Run SQL on Cloud SQL

1. **Via Cloud Console:**
   - Go to Cloud SQL > Your Instance > Databases
   - Click on your database
   - Use the SQL editor

2. **Via gcloud:**
   ```bash
   gcloud sql connect capturecare-db --user=capturecare --database=capturecare
   ```
   Then paste the SQL above.

3. **Via Cloud Shell:**
   ```bash
   gcloud sql connect capturecare-db --user=capturecare
   ```

## Verify Table Exists

After running the migration, verify:
```sql
SELECT * FROM patient_auth LIMIT 1;
```

If this query works, the table exists!

