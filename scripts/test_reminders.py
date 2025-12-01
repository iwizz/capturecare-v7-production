#!/usr/bin/env python3
"""
Test script for appointment reminders
Creates test appointments and verifies reminder functionality
"""

import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from capturecare.models import db, Appointment, Patient
from capturecare.web_dashboard import create_app
from capturecare.appointment_reminder_service import AppointmentReminderService
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_test_appointment():
    """Create a test appointment 25 hours in the future"""
    app = create_app()
    
    with app.app_context():
        try:
            # Get first patient
            patient = Patient.query.first()
            if not patient:
                logger.error("❌ No patients found in database. Please create a patient first.")
                return None
            
            # Create appointment 25 hours in the future
            future_time = datetime.utcnow() + timedelta(hours=25)
            end_time = future_time + timedelta(minutes=30)
            
            appointment = Appointment(
                patient_id=patient.id,
                title=f"Test Appointment - {future_time.strftime('%Y-%m-%d %H:%M')}",
                appointment_type='Test',
                start_time=future_time,
                end_time=end_time,
                duration_minutes=30,
                location='Test Location',
                notes='This is a test appointment for reminder testing',
                status='scheduled'
            )
            
            db.session.add(appointment)
            db.session.commit()
            
            logger.info(f"✅ Created test appointment {appointment.id} for {future_time}")
            logger.info(f"   Patient: {patient.first_name} {patient.last_name}")
            logger.info(f"   Phone: {patient.mobile or patient.phone or 'No phone number'}")
            
            return appointment
            
        except Exception as e:
            logger.error(f"❌ Error creating test appointment: {e}")
            db.session.rollback()
            return None


def test_reminder_service():
    """Test the reminder service"""
    app = create_app()
    
    with app.app_context():
        try:
            logger.info("Testing AppointmentReminderService...")
            
            reminder_service = AppointmentReminderService()
            
            # Test should_send_24hr_reminder logic
            logger.info("\n--- Testing reminder eligibility checks ---")
            
            # Create test appointment 25 hours away
            test_appt = create_test_appointment()
            if not test_appt:
                return False
            
            # Check if it should send 24hr reminder (should be False, too far)
            should_send = reminder_service.should_send_24hr_reminder(test_appt)
            logger.info(f"Should send 24hr reminder for appointment {test_appt.id}: {should_send}")
            
            # Create appointment 24 hours away
            future_time = datetime.utcnow() + timedelta(hours=24)
            end_time = future_time + timedelta(minutes=30)
            
            patient = Patient.query.get(test_appt.patient_id)
            appt_24hr = Appointment(
                patient_id=patient.id,
                title=f"Test 24hr Appointment",
                appointment_type='Test',
                start_time=future_time,
                end_time=end_time,
                duration_minutes=30,
                status='scheduled'
            )
            db.session.add(appt_24hr)
            db.session.commit()
            
            should_send_24hr = reminder_service.should_send_24hr_reminder(appt_24hr)
            logger.info(f"Should send 24hr reminder for appointment {appt_24hr.id} (24hr away): {should_send_24hr}")
            
            # Test full reminder check
            logger.info("\n--- Running full reminder check ---")
            stats = reminder_service.check_and_send_reminders()
            logger.info(f"Reminder check stats: {stats}")
            
            # Verify reminder status was updated
            db.session.refresh(appt_24hr)
            if appt_24hr.reminder_24hr_sent:
                logger.info(f"✅ Reminder status updated correctly for appointment {appt_24hr.id}")
            else:
                logger.warning(f"⚠️  Reminder status not updated for appointment {appt_24hr.id}")
            
            logger.info("\n✅ Reminder service test complete")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error testing reminder service: {e}", exc_info=True)
            return False


if __name__ == "__main__":
    success = test_reminder_service()
    sys.exit(0 if success else 1)

