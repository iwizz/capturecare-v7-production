#!/usr/bin/env python3
"""
Add reminder tracking fields to appointments table
This script can be run to add the reminder fields to an existing database
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from capturecare.models import db, Appointment
from capturecare.web_dashboard import create_app
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_reminder_fields():
    """Add reminder fields to appointments table if they don't exist"""
    app = create_app()
    
    with app.app_context():
        try:
            # Check if columns already exist by trying to query them
            try:
                Appointment.query.with_entities(Appointment.reminder_24hr_sent).first()
                logger.info("✅ Reminder fields already exist in appointments table")
                return True
            except Exception:
                # Columns don't exist, need to add them
                logger.info("Adding reminder fields to appointments table...")
                
                # Use raw SQL to add columns
                from sqlalchemy import text
                
                connection = db.engine.connect()
                trans = connection.begin()
                
                try:
                    # Add reminder fields
                    connection.execute(text("""
                        ALTER TABLE appointments 
                        ADD COLUMN IF NOT EXISTS reminder_24hr_sent BOOLEAN DEFAULT FALSE;
                    """))
                    
                    connection.execute(text("""
                        ALTER TABLE appointments 
                        ADD COLUMN IF NOT EXISTS reminder_24hr_sent_at TIMESTAMP;
                    """))
                    
                    connection.execute(text("""
                        ALTER TABLE appointments 
                        ADD COLUMN IF NOT EXISTS reminder_day_before_sent BOOLEAN DEFAULT FALSE;
                    """))
                    
                    connection.execute(text("""
                        ALTER TABLE appointments 
                        ADD COLUMN IF NOT EXISTS reminder_day_before_sent_at TIMESTAMP;
                    """))
                    
                    connection.execute(text("""
                        ALTER TABLE appointments 
                        ADD COLUMN IF NOT EXISTS reminder_1hr_sent BOOLEAN DEFAULT FALSE;
                    """))
                    
                    connection.execute(text("""
                        ALTER TABLE appointments 
                        ADD COLUMN IF NOT EXISTS reminder_1hr_sent_at TIMESTAMP;
                    """))
                    
                    trans.commit()
                    logger.info("✅ Successfully added reminder fields to appointments table")
                    return True
                    
                except Exception as e:
                    trans.rollback()
                    logger.error(f"❌ Error adding reminder fields: {e}")
                    raise
                finally:
                    connection.close()
                    
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return False

if __name__ == "__main__":
    success = add_reminder_fields()
    sys.exit(0 if success else 1)


