#!/usr/bin/env python3
"""
Script to check for Liz/Loiz/Lois leads in Cloud SQL production database
"""
import psycopg2
import os
import sys

def check_liz_leads():
    # Database password
    db_password = "Capture2025$$"
    
    proxy_port = 5437
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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd="/Users/timhook/Library/Mobile Documents/com~apple~CloudDocs/GitCode/Capture Care Replit Version"
    )

    time.sleep(5)  # Wait for proxy to start

    try:
        # Connect to database with Cap01 user
        database_url = f"postgresql://Cap01:{db_password}@127.0.0.1:{proxy_port}/capturecare"
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()

        print("✅ Connected to production database")
        print("=" * 80)

        # Check if leads table exists
        cursor.execute("""
            SELECT tablename FROM pg_tables 
            WHERE schemaname='public' AND tablename='leads'
        """)
        if not cursor.fetchone():
            print("❌ Leads table does not exist in production database")
            conn.close()
            return

        print("✅ Leads table exists\n")

        # Check total leads
        cursor.execute('SELECT COUNT(*) FROM leads')
        total_leads = cursor.fetchone()[0]
        print(f"📊 Total leads in production: {total_leads}\n")

        # Search for Liz/Loiz/Lois
        print("🔍 Searching for leads with 'Liz', 'Loiz', 'Lois', or 'Lina'...")
        cursor.execute("""
            SELECT id, first_name, last_name, email, mobile, source, status, 
                   form_sent_at, form_completed_at, converted_to_patient_id, 
                   created_at, notes
            FROM leads
            WHERE first_name ILIKE '%liz%' OR last_name ILIKE '%liz%'
               OR first_name ILIKE '%loiz%' OR last_name ILIKE '%loiz%'
               OR first_name ILIKE '%lois%' OR last_name ILIKE '%lois%'
               OR first_name ILIKE '%lina%' OR last_name ILIKE '%lina%'
               OR email ILIKE '%liz%' OR email ILIKE '%loiz%' OR email ILIKE '%lois%'
            ORDER BY created_at DESC
        """)

        matching_leads = cursor.fetchall()

        if matching_leads:
            print(f"✅ Found {len(matching_leads)} matching lead(s):")
            print("=" * 80)
            for lead in matching_leads:
                lead_id, first_name, last_name, email, mobile, source, status, \
                form_sent_at, form_completed_at, converted_to_patient_id, \
                created_at, notes = lead
                
                print(f"\n🆔 Lead ID: {lead_id}")
                print(f"👤 Name: {first_name} {last_name}")
                print(f"📧 Email: {email}")
                print(f"📱 Mobile: {mobile or 'Not set'}")
                print(f"📍 Source: {source or 'Not set'}")
                print(f"📊 Status: {status}")
                
                if form_sent_at:
                    print(f"📤 Form Sent: {form_sent_at}")
                if form_completed_at:
                    print(f"✅ Form Completed: {form_completed_at}")
                if converted_to_patient_id:
                    print(f"✅ Converted to Patient ID: {converted_to_patient_id}")
                    
                print(f"📅 Created: {created_at}")
                
                if notes:
                    print(f"📝 Notes: {notes}")
                    
                print("-" * 80)
        else:
            print("❌ No matching leads found")

        # Show all leads if there aren't too many
        if total_leads > 0 and total_leads <= 50:
            print(f"\n\n📋 ALL {total_leads} LEADS IN DATABASE:")
            print("=" * 80)
            cursor.execute("""
                SELECT id, first_name, last_name, email, status, created_at
                FROM leads
                ORDER BY created_at DESC
            """)

            all_leads = cursor.fetchall()
            for lead in all_leads:
                lead_id, first_name, last_name, email, status, created_at = lead
                print(f"  {lead_id}: {first_name} {last_name} ({email}) - {status} - {created_at}")

        conn.close()

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up proxy
        proxy_process.terminate()
        proxy_process.wait()
        print("\n🔌 Cloud SQL proxy stopped")

if __name__ == "__main__":
    check_liz_leads()

