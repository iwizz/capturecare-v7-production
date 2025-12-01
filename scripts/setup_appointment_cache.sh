#!/bin/bash
# Setup appointment cache table for fast calendar queries

echo "Setting up appointment cache table..."

# Get database connection from environment or prompt
if [ -z "$DATABASE_URL" ]; then
    echo "DATABASE_URL not set. Please set it or run:"
    echo "psql \$DATABASE_URL -f scripts/create_appointment_cache.sql"
    exit 1
fi

# Run the SQL script
psql "$DATABASE_URL" -f scripts/create_appointment_cache.sql

if [ $? -eq 0 ]; then
    echo "✅ Appointment cache table created successfully!"
    echo ""
    echo "The cache will automatically update when appointments are created/updated."
    echo "To manually refresh: POST /api/calendar/cache/refresh"
else
    echo "❌ Failed to create cache table"
    exit 1
fi

