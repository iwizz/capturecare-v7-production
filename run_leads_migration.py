#!/usr/bin/env python3
"""
Run the leads table migration on production Cloud SQL database
"""
import psycopg2
import subprocess
import time
import sys

def run_migration():
    print("╔════════════════════════════════════════════════════════════╗")
    print("║  CaptureCare - Add Leads Table Migration                  ║")
    print("╚════════════════════════════════════════════════════════════╝\n")
    
    # Database credentials
    db_password = "Capture2025$$"
    proxy_port = 5440
    
    print("🔗 Starting Cloud SQL Proxy...")
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
    
    time.sleep(5)
    
    try:
        # Connect to database
        print("🔌 Connecting to production database...")
        conn = psycopg2.connect(
            host='127.0.0.1',
            port=proxy_port,
            database='capturecare',
            user='Cap01',
            password=db_password,
            connect_timeout=10
        )
        
        print("✅ Connected successfully!\n")
        
        cursor = conn.cursor()
        
        # Read migration SQL
        print("📋 Reading migration script...")
        with open('migrations/add_leads_table.sql', 'r') as f:
            migration_sql = f.read()
        
        print("🔄 Executing migration...")
        cursor.execute(migration_sql)
        conn.commit()
        
        print("✅ Migration executed successfully!\n")
        
        # Verify table was created
        print("🔍 Verifying leads table...")
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'leads'
            ORDER BY ordinal_position
        """)
        
        columns = cursor.fetchall()
        if columns:
            print(f"✅ Leads table created with {len(columns)} columns:")
            for col_name, col_type in columns:
                print(f"   - {col_name}: {col_type}")
        else:
            print("❌ Leads table not found!")
            return False
        
        # Check for any existing leads
        cursor.execute("SELECT COUNT(*) FROM leads")
        count = cursor.fetchone()[0]
        print(f"\n📊 Current leads in database: {count}")
        
        cursor.close()
        conn.close()
        
        print("\n╔════════════════════════════════════════════════════════════╗")
        print("║  ✅ MIGRATION COMPLETED SUCCESSFULLY!                      ║")
        print("╚════════════════════════════════════════════════════════════╝")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Stop proxy
        print("\n🔌 Stopping Cloud SQL Proxy...")
        proxy_process.terminate()
        proxy_process.wait()

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)

