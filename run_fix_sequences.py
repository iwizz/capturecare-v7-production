#!/usr/bin/env python3
"""
Fix database sequences that are out of sync
Run this script to fix the "duplicate key value" error
"""

import os
import psycopg2
from urllib.parse import urlparse

def fix_sequences():
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        print("❌ DATABASE_URL not found in environment")
        print("Please set DATABASE_URL or run this from Cloud Shell with access to secrets")
        return False
    
    # Fix postgres:// to postgresql://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    print(f"🔧 Connecting to database...")
    
    try:
        # Connect to database
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        
        print("✅ Connected successfully")
        print("\n🔧 Fixing sequences...")
        
        # Read and execute the SQL file
        with open('fix_sequences.sql', 'r') as f:
            sql = f.read()
        
        cur.execute(sql)
        conn.commit()
        
        print("✅ All sequences fixed!")
        print("\n📊 Current sequence values:")
        
        # Show current values
        sequences = [
            'availability_patterns_id_seq',
            'availability_exceptions_id_seq',
            'appointments_id_seq',
            'patients_id_seq',
            'users_id_seq'
        ]
        
        for seq in sequences:
            cur.execute(f"SELECT last_value FROM {seq}")
            value = cur.fetchone()[0]
            print(f"  {seq}: {value}")
        
        cur.close()
        conn.close()
        
        print("\n✅ Sequences are now synchronized with table data")
        print("You can now add office hours without errors!")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == '__main__':
    fix_sequences()
