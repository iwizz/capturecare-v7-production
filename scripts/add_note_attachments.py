#!/usr/bin/env python3
"""
Add attachment support to patient notes table
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from capturecare.models import db
from capturecare.web_dashboard import app
from sqlalchemy import text

def add_note_attachment_columns():
    """Add attachment fields to patient_notes table"""
    
    print("📝 Adding attachment support to patient notes...")
    
    with app.app_context():
        try:
            # Check if columns already exist
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'patient_notes' 
                AND column_name = 'attachment_filename'
            """))
            
            if result.fetchone():
                print("✅ Columns already exist - skipping migration")
                return
            
            # Add columns
            print("Adding attachment_filename column...")
            db.session.execute(text("""
                ALTER TABLE patient_notes 
                ADD COLUMN IF NOT EXISTS attachment_filename VARCHAR(255)
            """))
            
            print("Adding attachment_path column...")
            db.session.execute(text("""
                ALTER TABLE patient_notes 
                ADD COLUMN IF NOT EXISTS attachment_path VARCHAR(500)
            """))
            
            print("Adding attachment_type column...")
            db.session.execute(text("""
                ALTER TABLE patient_notes 
                ADD COLUMN IF NOT EXISTS attachment_type VARCHAR(50)
            """))
            
            print("Adding attachment_size column...")
            db.session.execute(text("""
                ALTER TABLE patient_notes 
                ADD COLUMN IF NOT EXISTS attachment_size INTEGER
            """))
            
            # Create indexes
            print("Creating indexes...")
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_patient_notes_patient_id 
                ON patient_notes(patient_id)
            """))
            
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_patient_notes_has_attachment 
                ON patient_notes(attachment_filename) 
                WHERE attachment_filename IS NOT NULL
            """))
            
            db.session.commit()
            
            print("✅ Successfully added attachment support to patient notes!")
            print("📁 Columns added:")
            print("   - attachment_filename (VARCHAR 255)")
            print("   - attachment_path (VARCHAR 500)")
            print("   - attachment_type (VARCHAR 50)")
            print("   - attachment_size (INTEGER)")
            print("🔍 Indexes created for better performance")
            
        except Exception as e:
            print(f"❌ Error adding columns: {e}")
            db.session.rollback()
            raise

if __name__ == '__main__':
    add_note_attachment_columns()

