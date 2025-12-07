#!/bin/bash

# CaptureCare Database Upgrade Script
# This script upgrades your Cloud SQL instance from db-f1-micro to db-g1-small
# 
# Cost: +$15/month
# Time: ~3 minutes
# Downtime: A few seconds of connection interruption

echo "🔧 CaptureCare Database Upgrade"
echo "================================"
echo ""
echo "Current instance: db-f1-micro (0.6 GB RAM, ~25 max connections)"
echo "Target instance:  db-g1-small (1.7 GB RAM, ~100 max connections)"
echo ""
echo "⚠️  This will:"
echo "   - Upgrade your database from 0.6 GB → 1.7 GB RAM"
echo "   - Increase max connections from ~25 → ~100"
echo "   - Cost an additional ~\$15/month"
echo "   - Take approximately 3 minutes"
echo "   - Cause a few seconds of connection interruption"
echo ""
read -p "Continue with upgrade? (y/N) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    echo "❌ Upgrade cancelled"
    exit 1
fi

echo ""
echo "🚀 Starting database upgrade..."
echo ""

# Perform the upgrade
gcloud sql instances patch capturecare-db \
    --tier=db-g1-small \
    --project=capturecare-461801 \
    --quiet

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Database upgrade successful!"
    echo ""
    echo "📊 New Configuration:"
    gcloud sql instances describe capturecare-db \
        --project=capturecare-461801 \
        --format="table(settings.tier,settings.dataDiskSizeGb)"
    echo ""
    echo "🧪 Next Steps:"
    echo "   1. Visit: https://capturecare-310697189983.australia-southeast2.run.app/patients/1"
    echo "   2. Verify all sections load without 500 errors"
    echo "   3. Monitor logs: gcloud logging read 'severity>=ERROR' --limit=20 --project=capturecare-461801"
    echo ""
    echo "🎉 Your database is now production-ready!"
else
    echo ""
    echo "❌ Upgrade failed. Please check the error message above."
    echo ""
    echo "💡 Try manually with:"
    echo "   gcloud sql instances patch capturecare-db --tier=db-g1-small --project=capturecare-461801"
    exit 1
fi

