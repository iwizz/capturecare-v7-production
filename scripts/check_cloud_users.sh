#!/bin/bash
# Check users in Cloud SQL database

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

print("👥 Users in Cloud SQL:")
print("=" * 60)
cursor.execute('SELECT id, username, email, first_name, last_name, role, is_admin, is_active FROM "users" ORDER BY id')
users = cursor.fetchall()

for user in users:
    print(f"ID {user[0]}: {user[1]} ({user[2]})")
    print(f"   Name: {user[3]} {user[4]}")
    print(f"   Role: {user[5]}, Admin: {user[6]}, Active: {user[7]}")
    print()

print("\n🏥 Patients in Cloud SQL:")
print("=" * 60)
cursor.execute('SELECT id, first_name, last_name, email FROM "patients" ORDER BY id')
patients = cursor.fetchall()

print(f"Total: {len(patients)} patients")
for patient in patients[:5]:
    print(f"  - {patient[1]} {patient[2]} ({patient[3]})")

conn.close()
PYTHON_SCRIPT

kill $PROXY_PID 2>/dev/null

