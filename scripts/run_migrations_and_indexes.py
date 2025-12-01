#!/usr/bin/env python3
"""
Run database migrations and create indexes for Cloud SQL
Connects directly to the database using DATABASE_URL
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

def get_database_url():
    """Get database URL from environment or Secret Manager"""
    # Try environment variable first
    db_url = os.getenv('DATABASE_URL', '')
    
    if not db_url:
        # Try to load from Secret Manager (same as app does)
        try:
            from google.cloud import secretmanager
            import json
            
            project_id = os.getenv('GCP_PROJECT_ID', 'capturecare-461801')
            client = secretmanager.SecretManagerServiceClient()
            secret_name = f"projects/{project_id}/secrets/capturecare-db-connection/versions/latest"
            response = client.access_secret_version(request={"name": secret_name})
            db_url = response.payload.data.decode('UTF-8')
            print("✅ Loaded DATABASE_URL from Secret Manager")
        except Exception as e:
            print(f"⚠️  Could not load from Secret Manager: {e}")
            print("   Trying to use local SQLite fallback...")
            # Fallback to local SQLite (won't work for Cloud SQL, but will show error)
            config_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(config_dir, 'capturecare', 'instance', 'capturecare.db')
            db_url = f'sqlite:///{db_path}'
    
    # Fix postgres:// to postgresql:// for SQLAlchemy
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    
    return db_url

def run_migration(engine):
    """Add show_in_patient_app column to target_ranges table"""
    print("🔄 Running migration: Adding show_in_patient_app column...")
    
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            # Check if column already exists
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='target_ranges' 
                AND column_name='show_in_patient_app'
            """))
            
            if result.fetchone():
                print("✅ Column 'show_in_patient_app' already exists")
                trans.commit()
                return True
            
            # Add column with default value True
            print("   Adding column...")
            conn.execute(text("""
                ALTER TABLE target_ranges 
                ADD COLUMN show_in_patient_app BOOLEAN DEFAULT TRUE
            """))
            
            # Update all existing rows to True (default)
            print("   Setting existing rows to True...")
            conn.execute(text("""
                UPDATE target_ranges 
                SET show_in_patient_app = TRUE 
                WHERE show_in_patient_app IS NULL
            """))
            
            trans.commit()
            print("✅ Successfully added 'show_in_patient_app' column and updated existing rows")
            return True
            
        except Exception as e:
            trans.rollback()
            print(f"❌ Migration error: {e}")
            import traceback
            traceback.print_exc()
            return False

def create_indexes(engine):
    """Create performance indexes"""
    print("\n🔄 Creating database indexes...")
    
    indexes = [
        ("idx_health_data_patient_timestamp", """
            CREATE INDEX IF NOT EXISTS idx_health_data_patient_timestamp 
            ON health_data(patient_id, timestamp DESC)
        """),
        ("idx_health_data_measurement_type", """
            CREATE INDEX IF NOT EXISTS idx_health_data_measurement_type 
            ON health_data(measurement_type)
        """),
        ("idx_health_data_patient_type_timestamp", """
            CREATE INDEX IF NOT EXISTS idx_health_data_patient_type_timestamp 
            ON health_data(patient_id, measurement_type, timestamp DESC)
        """),
        ("idx_target_ranges_patient_measurement", """
            CREATE INDEX IF NOT EXISTS idx_target_ranges_patient_measurement 
            ON target_ranges(patient_id, measurement_type)
        """),
        ("idx_target_ranges_show_in_app", """
            CREATE INDEX IF NOT EXISTS idx_target_ranges_show_in_app 
            ON target_ranges(show_in_patient_app) 
            WHERE show_in_patient_app = TRUE
        """),
        ("idx_appointments_patient_date", """
            CREATE INDEX IF NOT EXISTS idx_appointments_patient_date 
            ON appointments(patient_id, start_time DESC)
        """),
        ("idx_devices_patient_id", """
            CREATE INDEX IF NOT EXISTS idx_devices_patient_id 
            ON devices(patient_id)
        """),
    ]
    
    # Try to create patient_auth indexes if table exists
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM patient_auth LIMIT 1"))
        indexes.extend([
            ("idx_patient_auth_patient_id", """
                CREATE INDEX IF NOT EXISTS idx_patient_auth_patient_id 
                ON patient_auth(patient_id)
            """),
            ("idx_patient_auth_email", """
                CREATE INDEX IF NOT EXISTS idx_patient_auth_email 
                ON patient_auth(email)
            """),
        ])
        print("   Found patient_auth table, will create indexes for it")
    except Exception:
        print("   patient_auth table not found, skipping those indexes")
    
    created = 0
    skipped = 0
    errors = 0
    
    for index_name, sql in indexes:
        try:
            with engine.connect() as conn:
                trans = conn.begin()
                try:
                    conn.execute(text(sql))
                    trans.commit()
                    print(f"   ✅ Created index: {index_name}")
                    created += 1
                except Exception as e:
                    trans.rollback()
                    # Check if index already exists
                    if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                        print(f"   ⊙ Index already exists: {index_name}")
                        skipped += 1
                    else:
                        raise
        except Exception as e:
            print(f"   ⚠️  Error creating {index_name}: {e}")
            errors += 1
    
    print(f"\n✅ Index creation complete: {created} created, {skipped} already existed, {errors} errors")
    return errors == 0

def main():
    """Run all migrations and index creation"""
    print("=" * 60)
    print("Database Migration and Index Creation")
    print("=" * 60)
    
    # Get database URL
    db_url = get_database_url()
    print(f"\n📊 Connecting to database...")
    print(f"   URL: {db_url[:50]}..." if len(db_url) > 50 else f"   URL: {db_url}")
    
    try:
        # Create engine with connection pool settings
        engine = create_engine(
            db_url,
            pool_pre_ping=True,
            connect_args={'connect_timeout': 10} if 'postgresql' in db_url else {}
        )
        
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Database connection successful\n")
        
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        print("\n💡 Make sure:")
        print("   1. DATABASE_URL environment variable is set, OR")
        print("   2. You have gcloud configured and Secret Manager access")
        sys.exit(1)
    
    # Run migration
    migration_success = run_migration(engine)
    
    if not migration_success:
        print("\n❌ Migration failed. Stopping.")
        sys.exit(1)
    
    # Create indexes
    indexes_success = create_indexes(engine)
    
    if migration_success and indexes_success:
        print("\n" + "=" * 60)
        print("✅ All migrations and indexes completed successfully!")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("⚠️  Completed with some warnings (see above)")
        print("=" * 60)

if __name__ == '__main__':
    main()
