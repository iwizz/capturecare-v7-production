#!/usr/bin/env python3
"""
Script to create PatientAuth table in the database
Run this to add the PatientAuth table for iOS app authentication
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from capturecare.web_dashboard import app, db
from capturecare.models import PatientAuth
from sqlalchemy import inspect

def table_exists(table_name):
    """Check if a table exists in the database"""
    inspector = inspect(db.engine)
    return table_name in inspector.get_table_names()

def create_patient_auth_table():
    """Create PatientAuth table if it doesn't exist"""
    with app.app_context():
        try:
            if table_exists('patient_auth'):
                print("✅ PatientAuth table already exists")
                return True
            
            print("Creating PatientAuth table...")
            db.create_all()
            
            # Verify it was created
            if table_exists('patient_auth'):
                print("✅ PatientAuth table created successfully!")
                return True
            else:
                print("❌ Failed to create PatientAuth table")
                return False
                
        except Exception as e:
            print(f"❌ Error creating PatientAuth table: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == '__main__':
    success = create_patient_auth_table()
    sys.exit(0 if success else 1)

