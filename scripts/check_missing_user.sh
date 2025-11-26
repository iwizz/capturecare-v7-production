#!/bin/bash
# Check which user is missing in Cloud SQL

echo "🔍 Checking Missing User"
echo "========================"
echo ""

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
import sqlite3
import psycopg2
import os

sqlite_db = "/Users/timhook/Library/Mobile Documents/com~apple~CloudDocs/GitCode/Capture Care Replit Version/capturecare/instance/capturecare.db"
sqlite_conn = sqlite3.connect(sqlite_db)
sqlite_cursor = sqlite_conn.cursor()

postgres_conn = psycopg2.connect(os.getenv('DATABASE_URL'))
postgres_cursor = postgres_conn.cursor()

# Get all users from SQLite
sqlite_cursor.execute("SELECT id, username, email, first_name, last_name, role FROM users ORDER BY id")
sqlite_users = {row[0]: row for row in sqlite_cursor.fetchall()}

# Get all users from PostgreSQL
postgres_cursor.execute('SELECT id, username, email, first_name, last_name, role FROM "users" ORDER BY id')
postgres_users = {row[0]: row for row in postgres_cursor.fetchall()}

print("SQLite Users:")
for user_id, user in sqlite_users.items():
    print(f"  ID {user_id}: {user[1]} ({user[2]}) - {user[3]} {user[4]} - {user[5]}")

print("\nPostgreSQL Users:")
for user_id, user in postgres_users.items():
    print(f"  ID {user_id}: {user[1]} ({user[2]}) - {user[3]} {user[4]} - {user[5]}")

print("\nMissing Users:")
missing = set(sqlite_users.keys()) - set(postgres_users.keys())
if missing:
    for user_id in missing:
        user = sqlite_users[user_id]
        print(f"  ❌ ID {user_id}: {user[1]} ({user[2]}) - {user[3]} {user[4]} - {user[5]}")
else:
    print("  ✅ No missing users (IDs might differ)")

sqlite_conn.close()
postgres_conn.close()
PYTHON_SCRIPT

kill $PROXY_PID 2>/dev/null

