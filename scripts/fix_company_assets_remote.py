#!/usr/bin/env python3
"""
Fix company_assets table by adding missing columns
Run this script to fix the production database
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from capturecare.web_dashboard import app, db
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_company_assets_table():
    """Add missing columns to company_assets table"""
    with app.app_context():
        try:
            # List of columns to add with their definitions
            columns_to_add = {
                'file_name': 'VARCHAR(255)',
                'file_type': 'VARCHAR(50)',
                'file_size': 'INTEGER',
                'link_url': 'TEXT',
                'tags': 'VARCHAR(500)',
                'is_pinned': 'BOOLEAN DEFAULT FALSE'
            }
            
            # Check if we're using PostgreSQL
            is_postgres = 'postgresql' in str(db.engine.url).lower()
            
            if is_postgres:
                logger.info("🔧 Fixing PostgreSQL table...")
                
                # For each column, try to add it
                for column_name, column_def in columns_to_add.items():
                    try:
                        sql = f"""
                        DO $$ 
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM information_schema.columns 
                                WHERE table_name='company_assets' AND column_name='{column_name}'
                            ) THEN
                                ALTER TABLE company_assets ADD COLUMN {column_name} {column_def};
                            END IF;
                        END $$;
                        """
                        db.session.execute(text(sql))
                        db.session.commit()
                        logger.info(f"✅ Added/verified column: {column_name}")
                    except Exception as e:
                        if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                            logger.info(f"⏭️  Column {column_name} already exists")
                            db.session.rollback()
                        else:
                            logger.error(f"❌ Error adding column {column_name}: {e}")
                            db.session.rollback()
                
                # Create indexes
                indexes = [
                    "CREATE INDEX IF NOT EXISTS idx_company_assets_category ON company_assets(category)",
                    "CREATE INDEX IF NOT EXISTS idx_company_assets_asset_type ON company_assets(asset_type)",
                    "CREATE INDEX IF NOT EXISTS idx_company_assets_is_pinned ON company_assets(is_pinned)",
                    "CREATE INDEX IF NOT EXISTS idx_company_assets_created_by ON company_assets(created_by_id)"
                ]
                
                for index_sql in indexes:
                    try:
                        db.session.execute(text(index_sql))
                        db.session.commit()
                        logger.info("✅ Created/verified index")
                    except Exception as e:
                        logger.info(f"⏭️  Index already exists or error: {e}")
                        db.session.rollback()
                
            else:
                logger.info("🔧 Fixing SQLite table...")
                # For SQLite, we need to check each column individually
                for column_name, column_def in columns_to_add.items():
                    try:
                        # Try to query the column - if it fails, it doesn't exist
                        db.session.execute(text(f"SELECT {column_name} FROM company_assets LIMIT 1"))
                        logger.info(f"⏭️  Column {column_name} already exists")
                    except Exception as e:
                        # Column doesn't exist, add it
                        try:
                            db.session.rollback()
                            db.session.execute(text(f"ALTER TABLE company_assets ADD COLUMN {column_name} {column_def}"))
                            db.session.commit()
                            logger.info(f"✅ Added column: {column_name}")
                        except Exception as e2:
                            logger.error(f"❌ Error adding column {column_name}: {e2}")
                            db.session.rollback()
            
            logger.info("✅ Company Assets table fixed successfully!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to fix table: {e}")
            db.session.rollback()
            return False

if __name__ == '__main__':
    success = fix_company_assets_table()
    sys.exit(0 if success else 1)

