#!/usr/bin/env python3
"""
Backup production Cloud SQL database before migration
"""
import subprocess
import time
import sys
from datetime import datetime

def backup_database():
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = f"capturecare_backup_{timestamp}.sql"
    
    print("╔════════════════════════════════════════════════════════════╗")
    print("║  CaptureCare - Production Database Backup                 ║")
    print("╚════════════════════════════════════════════════════════════╝\n")
    
    # Database credentials
    db_password = "Capture2025$$"
    proxy_port = 5441
    
    print(f"📅 Backup timestamp: {timestamp}")
    print(f"💾 Backup file: {backup_file}\n")
    
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
    
    if not proxy_process.poll() is None:
        print("❌ Failed to start Cloud SQL Proxy")
        return False
    
    print("✅ Cloud SQL Proxy started\n")
    
    try:
        # Run pg_dump to backup database
        print("📦 Creating database backup...")
        print("   This may take a few minutes...\n")
        
        env = {
            'PGPASSWORD': db_password
        }
        
        backup_cmd = [
            'pg_dump',
            '-h', '127.0.0.1',
            '-p', str(proxy_port),
            '-U', 'Cap01',
            '-d', 'capturecare',
            '-F', 'p',  # Plain text format
            '-f', backup_file,
            '--verbose'
        ]
        
        result = subprocess.run(
            backup_cmd,
            env=env,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"❌ Backup failed: {result.stderr}")
            return False
        
        print("✅ Backup completed!\n")
        
        # Verify backup file
        import os
        if os.path.exists(backup_file):
            size = os.path.getsize(backup_file)
            size_mb = size / (1024 * 1024)
            print(f"✅ Backup file created: {backup_file}")
            print(f"   Size: {size_mb:.2f} MB ({size:,} bytes)\n")
            
            # Show first few lines
            print("📋 Backup preview (first 10 lines):")
            print("─" * 60)
            with open(backup_file, 'r') as f:
                for i, line in enumerate(f):
                    if i >= 10:
                        break
                    print(line.rstrip())
            print("─" * 60)
            
            # Count tables in backup
            with open(backup_file, 'r') as f:
                content = f.read()
                table_count = content.count('CREATE TABLE')
                insert_count = content.count('INSERT INTO')
            
            print(f"\n📊 Backup statistics:")
            print(f"   - Tables: {table_count}")
            print(f"   - Insert statements: {insert_count}")
            
            print("\n╔════════════════════════════════════════════════════════════╗")
            print("║  ✅ BACKUP COMPLETED SUCCESSFULLY!                         ║")
            print("╚════════════════════════════════════════════════════════════╝")
            print(f"\n💾 Backup saved to: {backup_file}")
            print("\n⚠️  IMPORTANT: Keep this backup file safe!")
            print("   You can restore it using:")
            print(f"   psql -h 127.0.0.1 -p PORT -U Cap01 -d capturecare < {backup_file}")
            
            return True
        else:
            print("❌ Backup file not found!")
            return False
        
    except Exception as e:
        print(f"\n❌ Error during backup: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Stop proxy
        print("\n🔌 Stopping Cloud SQL Proxy...")
        proxy_process.terminate()
        proxy_process.wait()

if __name__ == "__main__":
    success = backup_database()
    sys.exit(0 if success else 1)

