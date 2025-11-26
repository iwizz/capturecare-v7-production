#!/bin/bash
# Verify Cloud SQL data matches local SQLite database

echo "🔍 Verifying Cloud SQL Data"
echo "============================"
echo ""

# Get database password
echo "Enter the database password:"
read -s DB_PASSWORD

# Find available port
PROXY_PORT=5433
while lsof -Pi :$PROXY_PORT -sTCP:LISTEN -t >/dev/null 2>&1; do
    PROXY_PORT=$((PROXY_PORT + 1))
done

echo ""
echo "🔌 Starting Cloud SQL Proxy on port $PROXY_PORT..."
cd "/Users/timhook/Library/Mobile Documents/com~apple~CloudDocs/GitCode/Capture Care Replit Version"
./cloud-sql-proxy capturecare-461801:australia-southeast2:capturecare-db --port=$PROXY_PORT > /tmp/cloud-sql-proxy.log 2>&1 &
PROXY_PID=$!

sleep 3

if ! kill -0 $PROXY_PID 2>/dev/null; then
    echo "❌ Failed to start Cloud SQL Proxy"
    cat /tmp/cloud-sql-proxy.log
    exit 1
fi

export DATABASE_URL="postgresql://capturecare:${DB_PASSWORD}@127.0.0.1:${PROXY_PORT}/capturecare"

echo "✅ Cloud SQL Proxy started"
echo ""

# Compare data counts
echo "📊 Comparing Data Counts"
echo "-------------------------"
echo ""

python3 << 'PYTHON_SCRIPT'
import sqlite3
import psycopg2
import os

# Connect to SQLite
sqlite_db = "/Users/timhook/Library/Mobile Documents/com~apple~CloudDocs/GitCode/Capture Care Replit Version/capturecare/instance/capturecare.db"
sqlite_conn = sqlite3.connect(sqlite_db)
sqlite_cursor = sqlite_conn.cursor()

# Connect to PostgreSQL
postgres_conn = psycopg2.connect(os.getenv('DATABASE_URL'))
postgres_cursor = postgres_conn.cursor()

# Tables to check
tables = [
    'users',
    'patients', 
    'appointments',
    'health_data',
    'patient_notes',
    'devices',
    'target_ranges',
    'invoices',
    'patient_correspondence',
    'availability_patterns',
    'availability_exceptions'
]

print(f"{'Table':<25} {'SQLite':<10} {'PostgreSQL':<12} {'Status':<10}")
print("-" * 60)

all_match = True
for table in tables:
    try:
        # Count SQLite
        sqlite_cursor.execute(f"SELECT COUNT(*) FROM {table}")
        sqlite_count = sqlite_cursor.fetchone()[0]
        
        # Count PostgreSQL
        postgres_cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
        postgres_count = postgres_cursor.fetchone()[0]
        
        status = "✅ MATCH" if sqlite_count == postgres_count else "❌ DIFF"
        if sqlite_count != postgres_count:
            all_match = False
        
        print(f"{table:<25} {sqlite_count:<10} {postgres_count:<12} {status:<10}")
    except Exception as e:
        print(f"{table:<25} {'ERROR':<10} {'ERROR':<12} ❌ {str(e)[:30]}")

print("-" * 60)

if all_match:
    print("\n✅ All data counts match!")
else:
    print("\n⚠️  Some data counts don't match - migration may be incomplete")

# Check specific data
print("\n📋 Sample Data Verification")
print("---------------------------")

# Check users
print("\n👥 Users:")
sqlite_cursor.execute("SELECT id, username, email, first_name, last_name, role FROM users ORDER BY id")
sqlite_users = sqlite_cursor.fetchall()

postgres_cursor.execute('SELECT id, username, email, first_name, last_name, role FROM "users" ORDER BY id')
postgres_users = postgres_cursor.fetchall()

print(f"   SQLite: {len(sqlite_users)} users")
print(f"   PostgreSQL: {len(postgres_users)} users")

if len(sqlite_users) == len(postgres_users):
    print("   ✅ User count matches")
    for i, (sq_user, pg_user) in enumerate(zip(sqlite_users, postgres_users)):
        if sq_user != pg_user:
            print(f"   ⚠️  User {i+1} differs: SQLite={sq_user}, PostgreSQL={pg_user}")
else:
    print("   ❌ User count mismatch")

# Check patients
print("\n🏥 Patients:")
sqlite_cursor.execute("SELECT id, first_name, last_name, email FROM patients ORDER BY id")
sqlite_patients = sqlite_cursor.fetchall()

postgres_cursor.execute('SELECT id, first_name, last_name, email FROM "patients" ORDER BY id')
postgres_patients = postgres_cursor.fetchall()

print(f"   SQLite: {len(sqlite_patients)} patients")
print(f"   PostgreSQL: {len(postgres_patients)} patients")

if len(sqlite_patients) == len(postgres_patients):
    print("   ✅ Patient count matches")
    # Show first few
    print("   Sample patients:")
    for patient in postgres_patients[:3]:
        print(f"      - {patient[1]} {patient[2]} ({patient[3]})")
else:
    print("   ❌ Patient count mismatch")

sqlite_conn.close()
postgres_conn.close()

PYTHON_SCRIPT

# Stop proxy
echo ""
echo "🛑 Stopping Cloud SQL Proxy..."
kill $PROXY_PID 2>/dev/null
wait $PROXY_PID 2>/dev/null

echo ""
echo "✅ Verification complete!"

