#!/usr/bin/env python3
"""
Migrate data from local SQLite database to Google Cloud SQL PostgreSQL database.
This script preserves all relationships and data integrity.
"""

import os
import sys
import sqlite3
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Database paths
SQLITE_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                         'capturecare', 'instance', 'capturecare.db')

# Cloud SQL connection (will be set from environment or command line)
POSTGRES_CONNECTION_STRING = os.getenv('DATABASE_URL', '')

def get_sqlite_connection():
    """Connect to local SQLite database"""
    if not os.path.exists(SQLITE_DB):
        raise FileNotFoundError(f"SQLite database not found at: {SQLITE_DB}")
    return sqlite3.connect(SQLITE_DB)

def get_postgres_connection():
    """Connect to Cloud SQL PostgreSQL database"""
    if not POSTGRES_CONNECTION_STRING:
        raise ValueError("DATABASE_URL environment variable not set")
    return psycopg2.connect(POSTGRES_CONNECTION_STRING)

def migrate_table(sqlite_conn, postgres_conn, table_name, columns, order_by=None):
    """Migrate a single table from SQLite to PostgreSQL"""
    print(f"\n📦 Migrating table: {table_name}")
    
    # Get data from SQLite
    cursor_sqlite = sqlite_conn.cursor()
    order_clause = f"ORDER BY {order_by}" if order_by else ""
    cursor_sqlite.execute(f"SELECT * FROM {table_name} {order_clause}")
    rows = cursor_sqlite.fetchall()
    
    if not rows:
        print(f"   ⚠️  No data to migrate")
        return 0
    
    print(f"   📊 Found {len(rows)} rows")
    
    # Get column names
    column_names = [description[0] for description in cursor_sqlite.description]
    
    # Prepare data for PostgreSQL
    # Convert None to NULL, handle datetime objects
    processed_rows = []
    for row in rows:
        processed_row = []
        for i, value in enumerate(row):
            if value is None:
                processed_row.append(None)
            elif isinstance(value, datetime):
                processed_row.append(value)
            elif isinstance(value, str) and value == '':
                processed_row.append(None)
            else:
                processed_row.append(value)
        processed_rows.append(tuple(processed_row))
    
    # Insert into PostgreSQL
    cursor_postgres = postgres_conn.cursor()
    
    # Build INSERT statement
    placeholders = ','.join(['%s'] * len(column_names))
    columns_str = ','.join([f'"{col}"' for col in column_names])
    
    # Use execute_values for bulk insert
    insert_query = f'INSERT INTO {table_name} ({columns_str}) VALUES %s ON CONFLICT DO NOTHING'
    
    try:
        execute_values(cursor_postgres, insert_query, processed_rows, page_size=1000)
        postgres_conn.commit()
        print(f"   ✅ Migrated {len(rows)} rows successfully")
        return len(rows)
    except Exception as e:
        postgres_conn.rollback()
        print(f"   ❌ Error migrating {table_name}: {e}")
        raise

def migrate_with_foreign_keys(sqlite_conn, postgres_conn):
    """Migrate tables in order to respect foreign key constraints"""
    
    # Define migration order (respecting foreign key dependencies)
    migration_order = [
        # Base tables first (no foreign keys)
        ('users', None),
        ('patients', None),
        
        # Tables that depend on users/patients
        ('devices', 'patient_id'),
        ('health_data', 'patient_id'),
        ('target_ranges', 'patient_id'),
        ('appointments', 'patient_id'),
        ('patient_notes', 'patient_id'),
        ('invoices', 'patient_id'),
        ('invoice_items', 'invoice_id'),
        ('patient_correspondence', 'patient_id'),
        
        # Availability tables
        ('availability_patterns', 'user_id'),
        ('availability_exceptions', 'user_id'),
        ('user_availability', 'user_id'),
        
        # Other tables
        ('notification_templates', None),
        ('communication_webhook_logs', None),
        ('webhook_logs', None),
    ]
    
    total_migrated = 0
    
    for table_name, order_by in migration_order:
        try:
            # Check if table exists in SQLite
            cursor = sqlite_conn.cursor()
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            if not cursor.fetchone():
                print(f"\n⚠️  Table {table_name} does not exist in SQLite, skipping")
                continue
            
            # Get column names
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in cursor.fetchall()]
            
            count = migrate_table(sqlite_conn, postgres_conn, table_name, columns, order_by)
            total_migrated += count
        except Exception as e:
            print(f"\n❌ Failed to migrate {table_name}: {e}")
            # Continue with other tables
            continue
    
    return total_migrated

def verify_migration(sqlite_conn, postgres_conn):
    """Verify that data was migrated correctly"""
    print("\n🔍 Verifying migration...")
    
    tables_to_check = [
        'users', 'patients', 'appointments', 'health_data', 
        'patient_notes', 'devices', 'target_ranges'
    ]
    
    cursor_sqlite = sqlite_conn.cursor()
    cursor_postgres = postgres_conn.cursor()
    
    for table_name in tables_to_check:
        try:
            # Count SQLite
            cursor_sqlite.execute(f"SELECT COUNT(*) FROM {table_name}")
            sqlite_count = cursor_sqlite.fetchone()[0]
            
            # Count PostgreSQL
            cursor_postgres.execute(f'SELECT COUNT(*) FROM "{table_name}"')
            postgres_count = cursor_postgres.fetchone()[0]
            
            status = "✅" if sqlite_count == postgres_count else "⚠️"
            print(f"   {status} {table_name}: SQLite={sqlite_count}, PostgreSQL={postgres_count}")
        except Exception as e:
            print(f"   ❌ Error checking {table_name}: {e}")

def main():
    """Main migration function"""
    print("=" * 60)
    print("🚀 CaptureCare Database Migration to Cloud SQL")
    print("=" * 60)
    
    # Check connections
    if not POSTGRES_CONNECTION_STRING:
        print("\n❌ Error: DATABASE_URL environment variable not set")
        print("\nUsage:")
        print("  export DATABASE_URL='postgresql://user:pass@host/dbname'")
        print("  python scripts/migrate_to_cloud_sql.py")
        sys.exit(1)
    
    sqlite_conn = None
    postgres_conn = None
    
    try:
        # Connect to databases
        print("\n📡 Connecting to databases...")
        sqlite_conn = get_sqlite_connection()
        print(f"   ✅ Connected to SQLite: {SQLITE_DB}")
        
        postgres_conn = get_postgres_connection()
        print(f"   ✅ Connected to PostgreSQL: {POSTGRES_CONNECTION_STRING.split('@')[1] if '@' in POSTGRES_CONNECTION_STRING else 'Cloud SQL'}")
        
        # Start migration
        print("\n🔄 Starting migration...")
        total = migrate_with_foreign_keys(sqlite_conn, postgres_conn)
        
        # Verify
        verify_migration(sqlite_conn, postgres_conn)
        
        print("\n" + "=" * 60)
        print(f"✅ Migration completed! Total rows migrated: {total}")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if sqlite_conn:
            sqlite_conn.close()
        if postgres_conn:
            postgres_conn.close()

if __name__ == '__main__':
    main()

