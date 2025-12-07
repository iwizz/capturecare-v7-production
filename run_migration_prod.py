#!/usr/bin/env python3
"""
Run database migration on production Cloud SQL database
"""
import sys
import os

# Add capturecare directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'capturecare'))

from sqlalchemy import create_engine, text
from config import Config

def run_migration():
    """Run the database migration"""
    print("🔧 Running migration on production database...")
    
    # Get database URL from config
    config = Config()
    db_url = config.SQLALCHEMY_DATABASE_URI
    
    if not db_url or 'sqlite' in db_url:
        print("❌ Error: No PostgreSQL database configured")
        return False
    
    print(f"📍 Connecting to database...")
    
    try:
        engine = create_engine(db_url)
        
        with engine.connect() as conn:
            # Run migration
            print("⚙️  Adding created_by_id column...")
            conn.execute(text("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS created_by_id INTEGER;"))
            conn.commit()
            
            # Verify
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='appointments' AND column_name='created_by_id';
            """))
            
            if result.fetchone():
                print("✅ Migration successful! Column 'created_by_id' added.")
                return True
            else:
                print("❌ Migration may have failed - column not found")
                return False
                
    except Exception as e:
        print(f"❌ Error running migration: {e}")
        return False

if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)

