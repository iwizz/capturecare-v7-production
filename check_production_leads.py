#!/usr/bin/env python3
"""
Script to check leads in Cloud SQL production database
"""
import psycopg2
import os
import sys
from datetime import datetime, timedelta

def check_production_leads():
    # Get database password from environment variable or user input
    db_password = os.getenv('DB_PASSWORD', '').strip()
    if not db_password:
        db_password = input("Enter database password: ").strip()
    if not db_password:
        print("❌ No password provided")
        return

    # Set up cloud SQL proxy connection
    proxy_port = 5433
    import subprocess
    import time

    print("🔗 Starting Cloud SQL proxy...")
    proxy_cmd = [
        "./cloud-sql-proxy",
        "capturecare-461801:australia-southeast2:capturecare-db",
        f"--port={proxy_port}"
    ]

    proxy_process = subprocess.Popen(
        proxy_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd="/Users/timhook/Library/Mobile Documents/com~apple~CloudDocs/GitCode/Capture Care Replit Version"
    )

    time.sleep(3)  # Wait for proxy to start

    try:
        # Connect to database
        database_url = f"postgresql://capturecare:{db_password}@127.0.0.1:{proxy_port}/capturecare"
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()

        print("✅ Connected to production database")
        print("=" * 80)

        # Check total leads
        cursor.execute('SELECT COUNT(*) FROM leads')
        total_leads = cursor.fetchone()[0]
        print(f"📊 Total leads in production: {total_leads}")
        print()

        # Search for Vijay Solanki specifically
        print("🔍 Searching for Vijay Solanki...")
        cursor.execute("""
            SELECT id, first_name, last_name, email, mobile, source, status, created_at, notes
            FROM leads
            WHERE (first_name ILIKE '%Vijay%' AND last_name ILIKE '%Solanki%')
               OR (first_name ILIKE '%Solanki%' AND last_name ILIKE '%Vijay%')
               OR email ILIKE '%Vijay%'
               OR email ILIKE '%Solanki%'
            ORDER BY created_at DESC
        """)

        solanki_leads = cursor.fetchall()

        if solanki_leads:
            print(f"✅ Found {len(solanki_leads)} Vijay Solanki lead(s):")
            print("-" * 80)
            for lead in solanki_leads:
                lead_id, first_name, last_name, email, mobile, source, status, created_at, notes = lead
                print(f"ID: {lead_id}")
                print(f"Name: {first_name} {last_name}")
                print(f"Email: {email}")
                print(f"Mobile: {mobile}")
                print(f"Source: {source}")
                print(f"Status: {status}")
                print(f"Created: {created_at}")
                print(f"Notes: {notes or 'None'}")
                print("-" * 40)
        else:
            print("❌ No Vijay Solanki leads found")

        # Check recent leads (last 7 days)
        print(f"\n📅 Recent leads created in last 7 days:")
        seven_days_ago = datetime.now() - timedelta(days=7)
        cursor.execute("""
            SELECT id, first_name, last_name, email, status, created_at
            FROM leads
            WHERE created_at >= %s
            ORDER BY created_at DESC
        """, (seven_days_ago,))

        recent_leads = cursor.fetchall()

        if recent_leads:
            print(f"Found {len(recent_leads)} recent lead(s):")
            for lead in recent_leads:
                lead_id, first_name, last_name, email, status, created_at = lead
                print(f"  - {lead_id}: {first_name} {last_name} ({email}) - {status} - {created_at}")
        else:
            print("No leads created in the last 7 days")

        # Show all leads if there aren't too many
        if total_leads > 0 and total_leads <= 50:
            print(f"\n📋 All {total_leads} leads:")
            cursor.execute("""
                SELECT id, first_name, last_name, email, status, created_at
                FROM leads
                ORDER BY created_at DESC
            """)

            all_leads = cursor.fetchall()
            for lead in all_leads:
                lead_id, first_name, last_name, email, status, created_at = lead
                print(f"  {lead_id}: {first_name} {last_name} ({email}) - {status}")

        conn.close()

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        # Clean up proxy
        proxy_process.terminate()
        proxy_process.wait()
        print("\n🔌 Cloud SQL proxy stopped")

if __name__ == "__main__":
    check_production_leads()
