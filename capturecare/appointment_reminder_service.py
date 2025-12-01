"""
Appointment Reminder Service
Handles automated SMS reminders for appointments
"""

import logging
from datetime import datetime, timedelta
from capturecare.models import db, Appointment, Patient, NotificationTemplate
from capturecare.notification_service import NotificationService

logger = logging.getLogger(__name__)


class AppointmentReminderService:
    """Service for sending automated appointment reminders"""
    
    def __init__(self):
        self.notification_service = NotificationService()
    
    def check_and_send_reminders(self):
        """
        Main method to check all appointments and send reminders as needed
        Returns dict with statistics
        """
        stats = {
            'checked': 0,
            '24hr_sent': 0,
            'day_before_sent': 0,
            'errors': 0
        }
        
        try:
            # Get all scheduled appointments in the future
            now = datetime.utcnow()
            future_appointments = Appointment.query.filter(
                Appointment.status == 'scheduled',
                Appointment.start_time > now
            ).all()
            
            stats['checked'] = len(future_appointments)
            logger.info(f"Checking {stats['checked']} scheduled appointments for reminders")
            
            for appointment in future_appointments:
                try:
                    # Check and send 24hr reminder
                    if self.should_send_24hr_reminder(appointment):
                        if self.send_24hr_reminder(appointment):
                            stats['24hr_sent'] += 1
                    
                    # Check and send day-before reminder
                    if self.should_send_day_before_reminder(appointment):
                        if self.send_day_before_reminder(appointment):
                            stats['day_before_sent'] += 1
                            
                except Exception as e:
                    logger.error(f"Error processing reminder for appointment {appointment.id}: {e}")
                    stats['errors'] += 1
            
            logger.info(f"Reminder check complete: {stats['24hr_sent']} 24hr reminders, {stats['day_before_sent']} day-before reminders sent")
            return stats
            
        except Exception as e:
            logger.error(f"Error in check_and_send_reminders: {e}")
            stats['errors'] += 1
            return stats
    
    def should_send_24hr_reminder(self, appointment):
        """
        Check if 24hr reminder should be sent
        Returns True if appointment is 24-25 hours away and reminder not yet sent
        """
        if appointment.reminder_24hr_sent:
            return False
        
        if appointment.status != 'scheduled':
            return False
        
        now = datetime.utcnow()
        appointment_time = appointment.start_time
        
        # Calculate time difference
        time_diff = appointment_time - now
        
        # Should send if between 23.5 and 24.5 hours before (30 minute window)
        hours_until = time_diff.total_seconds() / 3600
        
        return 23.5 <= hours_until <= 24.5
    
    def should_send_day_before_reminder(self, appointment):
        """
        Check if day-before reminder should be sent
        Returns True if it's the day before and it's after 6pm, and reminder not yet sent
        """
        if appointment.reminder_day_before_sent:
            return False
        
        if appointment.status != 'scheduled':
            return False
        
        now = datetime.utcnow()
        appointment_time = appointment.start_time
        
        # Check if appointment is tomorrow
        tomorrow = now.date() + timedelta(days=1)
        appointment_date = appointment_time.date()
        
        if appointment_date != tomorrow:
            return False
        
        # Check if it's after 6pm (18:00)
        if now.hour < 18:
            return False
        
        return True
    
    def send_24hr_reminder(self, appointment):
        """
        Send 24-hour reminder SMS
        Returns True if sent successfully, False otherwise
        """
        try:
            patient = Patient.query.get(appointment.patient_id)
            if not patient:
                logger.warning(f"Patient not found for appointment {appointment.id}")
                return False
            
            # Check if patient has phone number
            phone = patient.mobile or patient.phone
            if not phone:
                logger.info(f"No phone number for patient {patient.id} - skipping 24hr reminder")
                return False
            
            # Prepare template variables
            start_time = appointment.start_time.strftime('%B %d, %Y at %I:%M %p')
            start_time_short = appointment.start_time.strftime('%d/%m/%Y at %I:%M %p')
            patient_name = f"{patient.first_name} {patient.last_name}"
            
            template_vars = {
                'first_name': patient.first_name,
                'last_name': patient.last_name,
                'full_name': patient_name,
                'date_time': start_time,
                'date_time_short': start_time_short,
                'location': appointment.location or 'TBD',
                'duration': f"{appointment.duration_minutes} minutes",
                'practitioner': appointment.practitioner or 'Your practitioner',
                'appointment_type': appointment.appointment_type or 'Appointment',
                'notes': appointment.notes or ''
            }
            
            # Try to load custom template
            sms_template = NotificationTemplate.query.filter_by(
                template_type='sms',
                template_name='appointment_reminder_24hr',
                is_active=True
            ).first()
            
            if sms_template and sms_template.message:
                sms_message = self.notification_service._substitute_template_variables(
                    sms_template.message, template_vars
                )
            else:
                # Default message
                sms_message = f"Hi {patient.first_name}, reminder: Your appointment is tomorrow at {start_time_short}. Location: {appointment.location or 'TBD'}. See you then!"
            
            # Send SMS
            result = self.notification_service.send_sms(
                phone, 
                sms_message, 
                patient_id=patient.id,
                log_correspondence=True
            )
            
            if result.get('success'):
                # Update appointment reminder status
                appointment.reminder_24hr_sent = True
                appointment.reminder_24hr_sent_at = datetime.utcnow()
                db.session.commit()
                logger.info(f"✅ Sent 24hr reminder for appointment {appointment.id} to patient {patient.id}")
                return True
            else:
                logger.error(f"Failed to send 24hr reminder for appointment {appointment.id}: {result.get('error')}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending 24hr reminder for appointment {appointment.id}: {e}")
            db.session.rollback()
            return False
    
    def send_day_before_reminder(self, appointment):
        """
        Send day-before reminder SMS (sent at 6pm the day before)
        Returns True if sent successfully, False otherwise
        """
        try:
            patient = Patient.query.get(appointment.patient_id)
            if not patient:
                logger.warning(f"Patient not found for appointment {appointment.id}")
                return False
            
            # Check if patient has phone number
            phone = patient.mobile or patient.phone
            if not phone:
                logger.info(f"No phone number for patient {patient.id} - skipping day-before reminder")
                return False
            
            # Prepare template variables
            start_time = appointment.start_time.strftime('%B %d, %Y at %I:%M %p')
            start_time_short = appointment.start_time.strftime('%d/%m/%Y at %I:%M %p')
            patient_name = f"{patient.first_name} {patient.last_name}"
            
            template_vars = {
                'first_name': patient.first_name,
                'last_name': patient.last_name,
                'full_name': patient_name,
                'date_time': start_time,
                'date_time_short': start_time_short,
                'location': appointment.location or 'TBD',
                'duration': f"{appointment.duration_minutes} minutes",
                'practitioner': appointment.practitioner or 'Your practitioner',
                'appointment_type': appointment.appointment_type or 'Appointment',
                'notes': appointment.notes or ''
            }
            
            # Try to load custom template
            sms_template = NotificationTemplate.query.filter_by(
                template_type='sms',
                template_name='appointment_reminder_day_before',
                is_active=True
            ).first()
            
            if sms_template and sms_template.message:
                sms_message = self.notification_service._substitute_template_variables(
                    sms_template.message, template_vars
                )
            else:
                # Default message
                sms_message = f"Hi {patient.first_name}, reminder: Your appointment is tomorrow at {start_time_short}. Location: {appointment.location or 'TBD'}. See you then!"
            
            # Send SMS
            result = self.notification_service.send_sms(
                phone, 
                sms_message, 
                patient_id=patient.id,
                log_correspondence=True
            )
            
            if result.get('success'):
                # Update appointment reminder status
                appointment.reminder_day_before_sent = True
                appointment.reminder_day_before_sent_at = datetime.utcnow()
                db.session.commit()
                logger.info(f"✅ Sent day-before reminder for appointment {appointment.id} to patient {patient.id}")
                return True
            else:
                logger.error(f"Failed to send day-before reminder for appointment {appointment.id}: {result.get('error')}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending day-before reminder for appointment {appointment.id}: {e}")
            db.session.rollback()
            return False

