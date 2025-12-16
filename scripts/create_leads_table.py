#!/usr/bin/env python3
"""
Create leads table in production database
"""
import psycopg2
import os
import sys

def create_leads_table():
    # Get database password from environment variable
    db_password = os.getenv('DB_PASSWORD', '').strip()
    if not db_password:
        print("❌ No DB_PASSWORD environment variable set")
        print("Set it with: export DB_PASSWORD='your_password'")
        return

    # Cloud SQL connection details
    db_params = {
        'host': '127.0.0.1',
        'port': '5434',
        'database': 'capturecare',
        'user': 'capturecare',
        'password': db_password
    }

    # Start Cloud SQL proxy
    import subprocess
    import time

    print("🔗 Starting Cloud SQL proxy...")
    proxy_cmd = [
        "./cloud-sql-proxy",
        "capturecare-461801:australia-southeast2:capturecare-db",
        "--port=5434"
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
        print("🔌 Connecting to production database...")
        conn = psycopg2.connect(**db_params)
        cursor = conn.cursor()

        print("✅ Connected to production database")

        # Create leads table
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS leads (
            id SERIAL PRIMARY KEY,
            first_name VARCHAR(100) NOT NULL,
            last_name VARCHAR(100) NOT NULL,
            email VARCHAR(120) NOT NULL,
            mobile VARCHAR(20),
            source VARCHAR(100),
            status VARCHAR(50),
            form_sent_at TIMESTAMP,
            form_sent_via VARCHAR(20),
            form_completed_at TIMESTAMP,
            form_url TEXT,
            converted_to_patient_id INTEGER REFERENCES patients(id),
            converted_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """

        print("📋 Creating leads table...")
        cursor.execute(create_table_sql)
        conn.commit()

        print("✅ Leads table created successfully!")

        # Verify table was created
        cursor.execute("SELECT tablename FROM pg_tables WHERE tablename = 'leads';")
        result = cursor.fetchone()

        if result:
            print("✅ Leads table verified in database")
        else:
            print("❌ Leads table creation failed")

        conn.close()

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        # Clean up proxy
        proxy_process.terminate()
        proxy_process.wait()
        print("\n🔌 Cloud SQL proxy stopped")

if __name__ == "__main__":
    create_leads_table()
