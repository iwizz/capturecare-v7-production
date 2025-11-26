#!/bin/bash
# Update Cloud SQL schema to match the latest models

echo "🔄 Updating Cloud SQL Schema"
echo "============================="
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

# Add subject column to patient_notes if it doesn't exist
echo "📝 Adding missing columns..."
python3 << EOF
import psycopg2
import os

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cursor = conn.cursor()

# Check if subject column exists
cursor.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'patient_notes' AND column_name = 'subject'
""")

if not cursor.fetchone():
    print("   Adding 'subject' column to patient_notes...")
    cursor.execute("ALTER TABLE patient_notes ADD COLUMN subject VARCHAR(200)")
    conn.commit()
    print("   ✅ Added 'subject' column")
else:
    print("   ✅ 'subject' column already exists")

conn.close()
EOF

# Run Flask migrations
echo ""
echo "🔄 Running database migrations..."
cd "/Users/timhook/Library/Mobile Documents/com~apple~CloudDocs/GitCode/Capture Care Replit Version"

# Activate venv if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Set Flask app
export FLASK_APP=capturecare/web_dashboard.py

# Run migrations
flask db upgrade 2>&1 | tail -20

# Stop proxy
echo ""
echo "🛑 Stopping Cloud SQL Proxy..."
kill $PROXY_PID 2>/dev/null
wait $PROXY_PID 2>/dev/null

echo ""
echo "✅ Schema update complete!"

