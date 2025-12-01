# Appointment Cache Setup - For Instant Calendar Loading

## Overview

A dedicated cache table (`appointment_date_cache`) has been created to dramatically speed up calendar queries. Instead of querying the appointments table millions of times, we use a pre-indexed cache table.

## Setup Instructions

### Step 1: Run the Cache Table Creation Script

**Option A: Using the setup script (recommended)**
```bash
./scripts/setup_appointment_cache.sh
```

**Option B: Manual SQL execution**
```bash
# Connect to your Cloud SQL database
gcloud sql connect capturecare-db --user=postgres --database=capturecare

# Then run:
\i scripts/create_appointment_cache.sql
```

**Option C: Via API (after deployment)**
The cache will be automatically created on first use, or you can trigger it manually:
```bash
curl -X POST https://capturecare-310697189983.australia-southeast2.run.app/api/calendar/cache/refresh \
  -H "Content-Type: application/json" \
  -d '{"start_date": "2025-11-01", "end_date": "2026-02-28"}'
```

## How It Works

1. **Cache Table**: `appointment_date_cache` stores appointments indexed by date
2. **Auto-Update**: Database triggers automatically update the cache when appointments are created/updated/deleted
3. **Fast Queries**: Calendar queries use the cache table instead of scanning the full appointments table
4. **Indexes**: Multiple indexes ensure instant lookups by date, practitioner, patient, etc.

## Performance Benefits

- **Before**: Queries scan entire appointments table (slow with many appointments)
- **After**: Queries use indexed cache table (instant, even with thousands of appointments)

## Cache Maintenance

The cache automatically updates via database triggers. However, you can manually refresh it:

```bash
POST /api/calendar/cache/refresh
Body: {
  "start_date": "2025-11-01",
  "end_date": "2026-02-28"
}
```

## Verification

Check if cache table exists:
```sql
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_name = 'appointment_date_cache'
);
```

Check cache size:
```sql
SELECT COUNT(*) FROM appointment_date_cache;
```

## Troubleshooting

If calendar is still slow:
1. Verify cache table exists: `SELECT * FROM appointment_date_cache LIMIT 1;`
2. Check if triggers are active: `SELECT * FROM pg_trigger WHERE tgname LIKE '%appointment_cache%';`
3. Manually refresh cache: `POST /api/calendar/cache/refresh`
4. Check indexes: `\d appointment_date_cache` in psql

## Rollback

If you need to remove the cache:
```sql
DROP TRIGGER IF EXISTS trigger_appointment_cache_insert ON appointments;
DROP TRIGGER IF EXISTS trigger_appointment_cache_update ON appointments;
DROP TRIGGER IF EXISTS trigger_appointment_cache_delete ON appointments;
DROP FUNCTION IF EXISTS update_appointment_cache();
DROP FUNCTION IF EXISTS refresh_appointment_cache(date, date);
DROP TABLE IF EXISTS appointment_date_cache;
```

