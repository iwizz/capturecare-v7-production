#!/usr/bin/env python3
"""
Create default reminder SMS templates
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from capturecare.models import db, NotificationTemplate
from capturecare.web_dashboard import create_app
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_reminder_templates():
    """Create default reminder templates if they don't exist"""
    app = create_app()
    
    with app.app_context():
        try:
            # Check if templates already exist
            existing_24hr = NotificationTemplate.query.filter_by(
                template_type='sms',
                template_name='appointment_reminder_24hr'
            ).first()
            
            existing_day_before = NotificationTemplate.query.filter_by(
                template_type='sms',
                template_name='appointment_reminder_day_before'
            ).first()
            
            # Create 24hr reminder template
            if not existing_24hr:
                template_24hr = NotificationTemplate(
                    template_type='sms',
                    template_name='appointment_reminder_24hr',
                    is_predefined=True,
                    is_active=True,
                    message="Hi {first_name}, reminder: Your appointment is in 24 hours at {date_time_short}. Location: {location}. See you then!",
                    description="24-hour appointment reminder SMS"
                )
                db.session.add(template_24hr)
                logger.info("✅ Created 24hr reminder template")
            else:
                logger.info("ℹ️  24hr reminder template already exists")
            
            # Create day-before reminder template
            if not existing_day_before:
                template_day_before = NotificationTemplate(
                    template_type='sms',
                    template_name='appointment_reminder_day_before',
                    is_predefined=True,
                    is_active=True,
                    message="Hi {first_name}, reminder: Your appointment is tomorrow at {date_time_short}. Location: {location}. See you then!",
                    description="Day-before appointment reminder SMS (sent at 6pm)"
                )
                db.session.add(template_day_before)
                logger.info("✅ Created day-before reminder template")
            else:
                logger.info("ℹ️  Day-before reminder template already exists")
            
            db.session.commit()
            logger.info("✅ Reminder templates setup complete")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error creating reminder templates: {e}")
            db.session.rollback()
            return False


if __name__ == "__main__":
    success = create_reminder_templates()
    sys.exit(0 if success else 1)

