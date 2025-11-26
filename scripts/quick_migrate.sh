#!/bin/bash
# Quick migration script - Run this to migrate your data to Cloud SQL

set -e

echo "🚀 CaptureCare Database Migration"
echo "=================================="
echo ""

# Check if Cloud SQL Proxy is available
if [ ! -f "./cloud-sql-proxy" ]; then
    echo "❌ Cloud SQL Proxy not found. Downloading..."
    curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.8.0/cloud-sql-proxy.darwin.arm64
    chmod +x cloud-sql-proxy
    echo "✅ Cloud SQL Proxy downloaded"
fi

# Get database password
echo ""
echo "📝 Database Password"
echo "-------------------"
echo "Enter the password for the 'capturecare' database user:"
read -s DB_PASSWORD

if [ -z "$DB_PASSWORD" ]; then
    echo "❌ Password cannot be empty"
    exit 1
fi

# Check if password is correct by testing connection (will be updated after proxy starts)
echo ""
echo "🔍 Preparing connection..."

# Find an available port
PROXY_PORT=5433
while lsof -Pi :$PROXY_PORT -sTCP:LISTEN -t >/dev/null 2>&1; do
    PROXY_PORT=$((PROXY_PORT + 1))
done

echo "   Using port: $PROXY_PORT (5432 is already in use)"

# Start Cloud SQL Proxy in background
echo ""
echo "🔌 Starting Cloud SQL Proxy on port $PROXY_PORT..."
./cloud-sql-proxy capturecare-461801:australia-southeast2:capturecare-db --port=$PROXY_PORT > /tmp/cloud-sql-proxy.log 2>&1 &
PROXY_PID=$!

# Wait for proxy to start
sleep 3

# Check if proxy is running
if ! kill -0 $PROXY_PID 2>/dev/null; then
    echo "❌ Failed to start Cloud SQL Proxy"
    cat /tmp/cloud-sql-proxy.log
    exit 1
fi

echo "✅ Cloud SQL Proxy started on port $PROXY_PORT (PID: $PROXY_PID)"
echo ""

# Update DATABASE_URL with the correct port
export DATABASE_URL="postgresql://capturecare:${DB_PASSWORD}@127.0.0.1:${PROXY_PORT}/capturecare"

# Test connection
echo "🧪 Testing database connection..."
python3 -c "
import psycopg2
import os
try:
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    print('✅ Connection successful!')
    conn.close()
except Exception as e:
    print(f'❌ Connection failed: {e}')
    exit(1)
" || {
    echo ""
    echo "❌ Connection test failed. Please check:"
    echo "   1. Database password is correct"
    echo "   2. Cloud SQL instance is running"
    echo "   3. You have proper IAM permissions"
    kill $PROXY_PID 2>/dev/null
    exit 1
}

# Run migration
echo ""
echo "🔄 Starting migration..."
echo ""

# Activate venv if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Install psycopg2 if needed
python3 -c "import psycopg2" 2>/dev/null || pip install psycopg2-binary

# Run migration script
python3 scripts/migrate_to_cloud_sql.py

# Stop proxy
echo ""
echo "🛑 Stopping Cloud SQL Proxy..."
kill $PROXY_PID 2>/dev/null
wait $PROXY_PID 2>/dev/null

echo ""
echo "✅ Migration complete!"
echo ""
echo "Next steps:"
echo "1. Verify data in Cloud SQL"
echo "2. Test the application on Cloud Run"
echo "3. Update Cloud Run to use Cloud SQL"

