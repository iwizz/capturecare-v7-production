#!/bin/bash
# Fix PostgreSQL sequences after migration from SQLite

read -s -p "Enter database password: " DB_PASSWORD
echo ""

PROXY_PORT=5433
while lsof -Pi :$PROXY_PORT -sTCP:LISTEN -t >/dev/null 2>&1; do
    PROXY_PORT=$((PROXY_PORT + 1))
done

cd "/Users/timhook/Library/Mobile Documents/com~apple~CloudDocs/GitCode/Capture Care Replit Version"
./cloud-sql-proxy capturecare-461801:australia-southeast2:capturecare-db --port=$PROXY_PORT > /tmp/cloud-sql-proxy.log 2>&1 &
PROXY_PID=$!
sleep 3

export DATABASE_URL="postgresql://capturecare:${DB_PASSWORD}@127.0.0.1:${PROXY_PORT}/capturecare"

python3 << 'PYTHON_SCRIPT'
import psycopg2
import os

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cursor = conn.cursor()

print("🔧 Fixing PostgreSQL sequences...")
print("=" * 60)

# Get max ID for each table and set sequence
tables = [
    'patient_correspondence',
    'communication_webhook_logs',
    'patient_notes',
    'appointments',
    'health_data',
    'invoices',
    'invoice_items',
    'users',
    'patients'
]

for table in tables:
    try:
        # Get current max ID
        cursor.execute(f'SELECT COALESCE(MAX(id), 0) FROM "{table}"')
        max_id = cursor.fetchone()[0]
        
        # Get sequence name (PostgreSQL convention: tablename_id_seq)
        sequence_name = f'{table}_id_seq'
        
        # Check if sequence exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = %s
            )
        """, (sequence_name,))
        seq_exists = cursor.fetchone()[0]
        
        if not seq_exists:
            print(f"⚠️  {table}: sequence {sequence_name} does not exist, skipping")
            continue
        
        # Set sequence to max_id + 1
        new_seq_value = max_id + 1
        cursor.execute(f'SELECT setval(\'{sequence_name}\', {new_seq_value}, false)')
        
        # Verify
        cursor.execute(f'SELECT last_value FROM {sequence_name}')
        last_value = cursor.fetchone()[0]
        
        print(f"✅ {table}: max_id={max_id}, sequence set to {last_value}")
    except Exception as e:
        print(f"⚠️  {table}: {e}")

conn.commit()
print("\n✅ All sequences fixed!")
conn.close()
PYTHON_SCRIPT

kill $PROXY_PID 2>/dev/null

