#!/bin/bash
# Deploy CaptureCare with Lead Management functionality
# This script:
# 1. Runs the leads table migration on Cloud SQL
# 2. Deploys the application to Cloud Run

set -e  # Exit on error

PROJECT_DIR="/Users/timhook/Library/Mobile Documents/com~apple~CloudDocs/GitCode/Capture Care Replit Version"
cd "$PROJECT_DIR"

echo "╔════════════════════════════════════════════════════════════╗"
echo "║  CaptureCare Deployment with Lead Management              ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Step 1: Run database migration
echo "📊 Step 1: Running leads table migration..."
echo "─────────────────────────────────────────────────────────────"

# Check if database password is set
if [ -z "$DB_PASSWORD" ]; then
    echo "Enter database password for Cap01 user:"
    read -s DB_PASSWORD
    export DB_PASSWORD
fi

# Find available port for proxy
PROXY_PORT=5438
while lsof -Pi :$PROXY_PORT -sTCP:LISTEN -t >/dev/null 2>&1; do
    PROXY_PORT=$((PROXY_PORT + 1))
done

echo "Starting Cloud SQL Proxy on port $PROXY_PORT..."
./cloud-sql-proxy capturecare-461801:australia-southeast2:capturecare-db --port=$PROXY_PORT > /tmp/deploy-proxy.log 2>&1 &
PROXY_PID=$!

# Wait for proxy to start
sleep 5

if ! kill -0 $PROXY_PID 2>/dev/null; then
    echo "❌ Failed to start Cloud SQL Proxy"
    cat /tmp/deploy-proxy.log
    exit 1
fi

echo "✅ Cloud SQL Proxy started (PID: $PROXY_PID)"

# Run migration
echo "Running migration script..."
PGPASSWORD=$DB_PASSWORD psql -h 127.0.0.1 -p $PROXY_PORT -U Cap01 -d capturecare -f migrations/add_leads_table.sql 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Leads table migration completed successfully!"
else
    echo "❌ Migration failed!"
    kill $PROXY_PID 2>/dev/null
    exit 1
fi

# Stop proxy
kill $PROXY_PID 2>/dev/null
echo "🔌 Cloud SQL Proxy stopped"
echo ""

# Step 2: Deploy to Cloud Run
echo "🚀 Step 2: Deploying to Cloud Run..."
echo "─────────────────────────────────────────────────────────────"

# Build and deploy
gcloud builds submit --config cloudbuild.yaml

if [ $? -eq 0 ]; then
    echo ""
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║  ✅ DEPLOYMENT SUCCESSFUL!                                 ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""
    echo "🌐 Application URL:"
    echo "   https://capturecare-310697189983.australia-southeast2.run.app"
    echo ""
    echo "📋 Lead Management URLs:"
    echo "   - List Leads:    /leads"
    echo "   - Add Lead:      /leads/add"
    echo ""
    echo "✅ Lead Management is now fully functional!"
else
    echo ""
    echo "❌ Deployment failed! Check the logs above for details."
    exit 1
fi

