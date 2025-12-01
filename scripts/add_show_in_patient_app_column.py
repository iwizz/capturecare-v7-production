#!/usr/bin/env python3
"""
Add show_in_patient_app column to target_ranges table
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from capturecare.web_dashboard import app, db
from sqlalchemy import text

def add_column():
    """Add show_in_patient_app column to target_ranges table"""
    with app.app_context():
        try:
            # Check if column already exists
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='target_ranges' 
                AND column_name='show_in_patient_app'
            """))
            
            if result.fetchone():
                print("✅ Column 'show_in_patient_app' already exists")
                return
            
            # Add column with default value True
            db.session.execute(text("""
                ALTER TABLE target_ranges 
                ADD COLUMN show_in_patient_app BOOLEAN DEFAULT TRUE
            """))
            
            db.session.commit()
            print("✅ Successfully added 'show_in_patient_app' column to target_ranges table")
            
            # Update all existing rows to True (default)
            db.session.execute(text("""
                UPDATE target_ranges 
                SET show_in_patient_app = TRUE 
                WHERE show_in_patient_app IS NULL
            """))
            
            db.session.commit()
            print("✅ Set all existing target ranges to show_in_patient_app = TRUE")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    add_column()

