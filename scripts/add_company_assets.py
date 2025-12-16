#!/usr/bin/env python3
"""
Migration Script: Add company_assets table
Purpose: Create company assets table for storing company-wide resources
Date: 2025-12-16
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

def run_migration():
    """Run the company assets migration"""
    with app.app_context():
        try:
            # Check if we're using SQLite or PostgreSQL
            is_sqlite = 'sqlite' in str(db.engine.url).lower()
            
            if is_sqlite:
                # SQLite version
                logger.info("📁 Using SQLite - creating table with direct SQL...")
                
                # Check if table already exists
                result = db.session.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='company_assets'"
                ))
                if result.fetchone():
                    logger.info("⏭️  Table 'company_assets' already exists, skipping creation")
                else:
                    # Create table for SQLite
                    db.session.execute(text("""
                        CREATE TABLE company_assets (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            title VARCHAR(200) NOT NULL,
                            description TEXT,
                            asset_type VARCHAR(50) NOT NULL,
                            category VARCHAR(100),
                            file_path VARCHAR(500),
                            file_name VARCHAR(255),
                            file_type VARCHAR(50),
                            file_size INTEGER,
                            link_url TEXT,
                            tags VARCHAR(500),
                            is_pinned BOOLEAN DEFAULT 0,
                            created_by_id INTEGER NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (created_by_id) REFERENCES users(id)
                        )
                    """))
                    logger.info("✅ Created company_assets table")
                
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
                        logger.info(f"✅ Created index")
                    except Exception as e:
                        logger.info(f"⏭️  Index already exists or error: {e}")
                
            else:
                # PostgreSQL version
                logger.info("📁 Using PostgreSQL - running migration from file...")
                sql_file = os.path.join(os.path.dirname(__file__), '..', 'migrations', 'add_company_assets.sql')
                
                with open(sql_file, 'r') as f:
                    sql_script = f.read()
                
                # Split into individual statements
                statements = [s.strip() for s in sql_script.split(';') if s.strip()]
                
                for statement in statements:
                    try:
                        db.session.execute(text(statement))
                        logger.info(f"✅ Executed: {statement[:100]}...")
                    except Exception as e:
                        if "already exists" in str(e).lower():
                            logger.info(f"⏭️  Skipped (already exists)")
                        else:
                            logger.error(f"❌ Error: {e}")
                            raise
            
            db.session.commit()
            logger.info("✅ Migration completed successfully!")
            logger.info("📁 Company Assets table is ready to use")
            
            # Create upload directory
            upload_dir = os.path.join(os.path.dirname(__file__), '..', 'capturecare', 'static', 'uploads', 'company_assets')
            os.makedirs(upload_dir, exist_ok=True)
            logger.info(f"✅ Created upload directory: {upload_dir}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            db.session.rollback()
            return False

if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)

