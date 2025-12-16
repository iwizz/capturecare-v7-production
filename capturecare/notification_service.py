import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from .config import Config

logger = logging.getLogger(__name__)

class NotificationService:
    """Service for sending SMS and email notifications"""
    
    def __init__(self):
        self._initialize_services()
    
    def _initialize_services(self):
        """Initialize or reinitialize services with current config"""
        # Reload config from environment
        from importlib import reload
        from . import config
        reload(config)
        from .config import Config
        
        self.twilio_configured = bool(Config.TWILIO_ACCOUNT_SID and Config.TWILIO_AUTH_TOKEN and Config.TWILIO_PHONE_NUMBER)
        self.smtp_configured = bool(Config.SMTP_USERNAME and Config.SMTP_PASSWORD)
        
        if self.twilio_configured:
            try:
                from twilio.rest import Client
                self.twilio_client = Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)
                self.twilio_phone = Config.TWILIO_PHONE_NUMBER
                logger.info("✅ Twilio SMS service initialized")
            except ImportError:
                logger.warning("⚠️  Twilio library not installed. Run: pip install twilio")
                self.twilio_configured = False
            except Exception as e:
                logger.error(f"❌ Error initializing Twilio: {e}")
                self.twilio_configured = False
        else:
            logger.info("ℹ️  Twilio not configured - SMS notifications disabled")
        
        if self.smtp_configured:
            logger.info("✅ SMTP email service configured")
        else:
            logger.info("ℹ️  SMTP not configured - Email notifications disabled")
    
    def reload_credentials(self):
        """Reload credentials from environment without restarting the app"""
        logger.info("🔄 Reloading notification service credentials...")
        self._initialize_services()
        logger.info("✅ Notification service credentials reloaded")
    
    def _format_phone_number(self, phone):
        """
        Format phone number for Twilio (E.164 format)
        Handles Australian numbers intelligently
        
        Examples:
            0417518940 -> +61417518940
            61417518940 -> +61417518940
            +61417518940 -> +61417518940
            417518940 -> +61417518940
        """
        if not phone:
            return None
        
        # Clean the number - remove spaces, dashes, parentheses
        phone = str(phone).strip().replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        
        # Already in E.164 format
        if phone.startswith('+'):
            return phone
        
        # Remove leading zeros
        phone = phone.lstrip('0')
        
        # If it starts with country code (61 for Australia)
        if phone.startswith('61'):
            return '+' + phone
        
        # Otherwise assume Australian mobile/landline - add +61
        return '+61' + phone
    
    def send_sms(self, to_phone, message, patient_id=None, user_id=None, log_correspondence=True):
        """
        Send SMS via Twilio
        
        Args:
            to_phone (str): Recipient phone number (format: +1234567890)
            message (str): Message text
            patient_id (int, optional): Patient ID for logging correspondence
            user_id (int, optional): User ID for logging correspondence
            log_correspondence (bool): Whether to log to correspondence table (default: True)
            
        Returns:
            dict: {'success': bool, 'sid': str, 'status': str, 'error': str}
        """
        if not self.twilio_configured:
            logger.warning(f"Cannot send SMS - Twilio not configured")
            return {'success': False, 'error': 'Twilio not configured'}
        
        if not to_phone:
            logger.warning("Cannot send SMS - no phone number provided")
            return {'success': False, 'error': 'No phone number provided'}
        
        try:
            # Format phone number to E.164 format
            formatted_phone = self._format_phone_number(to_phone)
            logger.info(f"📱 Formatting phone: {to_phone} -> {formatted_phone}")
            
            message_obj = self.twilio_client.messages.create(
                body=message,
                from_=self.twilio_phone,
                to=formatted_phone
            )
            
            logger.info(f"✅ SMS sent to {formatted_phone}: {message_obj.sid}")
            
            # Log correspondence if patient_id provided
            if log_correspondence and patient_id:
                self._log_sms_correspondence(
                    patient_id=patient_id,
                    user_id=user_id,
                    recipient_phone=formatted_phone,
                    message=message,
                    status='sent',  # Show as 'sent' instead of 'queued' since message was successfully sent
                    external_id=message_obj.sid
                )
            
            return {
                'success': True,
                'sid': message_obj.sid,
                'status': message_obj.status,
                'error': None
            }
            
        except Exception as e:
            logger.error(f"❌ Error sending SMS to {to_phone}: {e}")
            
            # Log failed correspondence if patient_id provided
            if log_correspondence and patient_id:
                self._log_sms_correspondence(
                    patient_id=patient_id,
                    user_id=user_id,
                    recipient_phone=to_phone,
                    message=message,
                    status='failed',
                    error_message=str(e)
                )
            
            return {'success': False, 'error': str(e)}
    
    def _log_sms_correspondence(self, patient_id, recipient_phone, message, status, user_id=None, external_id=None, error_message=None):
        """Log SMS correspondence to database"""
        try:
            from models import db, PatientCorrespondence
            from datetime import datetime
            import psycopg2
            
            correspondence = PatientCorrespondence(
                patient_id=patient_id,
                user_id=user_id,
                channel='sms',
                direction='outbound',
                body=message,
                recipient_phone=recipient_phone,
                status=status,
                external_id=external_id,
                error_message=error_message,
                sent_at=datetime.utcnow(),
                delivered_at=datetime.utcnow() if status in ['sent', 'delivered', 'queued'] else None
            )
            
            db.session.add(correspondence)
            db.session.commit()
            logger.info(f"✅ Logged SMS correspondence for patient {patient_id}")
            
        except Exception as e:
            error_str = str(e)
            # Check for duplicate key errors (sequence issues)
            if 'UniqueViolation' in error_str or 'duplicate key' in error_str.lower():
                logger.warning(f"⚠️  Duplicate key error when logging SMS correspondence. This may indicate a sequence issue. Error: {e}")
                # Try to fix the sequence by getting max ID and setting it
                try:
                    from models import db, PatientCorrespondence
                    max_id = db.session.query(db.func.max(PatientCorrespondence.id)).scalar() or 0
                    db.session.execute(db.text(f"SELECT setval('patient_correspondence_id_seq', {max_id + 1}, false)"))
                    db.session.commit()
                    logger.info(f"✅ Fixed patient_correspondence sequence to {max_id + 1}")
                except Exception as seq_error:
                    logger.error(f"❌ Failed to fix sequence: {seq_error}")
            else:
                logger.error(f"❌ Error logging SMS correspondence: {e}")
            
            # Don't fail the SMS send if logging fails
            try:
                db.session.rollback()
            except:
                pass
    
    def send_email(self, to_email, subject, body_html, body_text=None, patient_id=None, user_id=None, log_correspondence=True):
        """
        Send email via SMTP
        
        Args:
            to_email (str): Recipient email address
            subject (str): Email subject
            body_html (str): HTML email body
            body_text (str, optional): Plain text email body (fallback)
            patient_id (int, optional): Patient ID for logging correspondence
            user_id (int, optional): User ID for logging correspondence
            log_correspondence (bool): Whether to log to correspondence table (default: True)
            
        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not self.smtp_configured:
            logger.warning("Cannot send email - SMTP not configured")
            return False
        
        if not to_email:
            logger.warning("Cannot send email - no email address provided")
            return False
        
        try:
            logger.info(f"🔄 Attempting to send email to {to_email}")
            logger.info(f"📧 SMTP Config - Server: {Config.SMTP_SERVER}, Port: {Config.SMTP_PORT}, Username: {Config.SMTP_USERNAME}")
            
            msg = MIMEMultipart('alternative')
            msg['From'] = Config.SMTP_FROM_EMAIL
            msg['To'] = to_email
            msg['Subject'] = subject
            
            if body_text:
                msg.attach(MIMEText(body_text, 'plain'))
            msg.attach(MIMEText(body_html, 'html'))
            
            logger.info(f"📨 Connecting to SMTP server...")
            with smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT) as server:
                logger.info(f"🔐 Starting TLS...")
                server.starttls()
                # Fix: Replace non-breaking spaces (\xa0) with regular spaces for SMTP compatibility
                smtp_password = Config.SMTP_PASSWORD.replace('\xa0', ' ') if Config.SMTP_PASSWORD else ''
                logger.info(f"🔑 Logging in as {Config.SMTP_USERNAME}...")
                server.login(Config.SMTP_USERNAME, smtp_password)
                logger.info(f"📤 Sending message...")
                server.send_message(msg)
            
            logger.info(f"✅ Email sent to {to_email}: {subject}")
            
            # Log correspondence if patient_id provided
            if log_correspondence and patient_id:
                self._log_email_correspondence(
                    patient_id=patient_id,
                    user_id=user_id,
                    recipient_email=to_email,
                    subject=subject,
                    body=body_text or body_html,
                    status='delivered'
                )
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error sending email to {to_email}: {e}")
            
            # Log failed correspondence if patient_id provided
            if log_correspondence and patient_id:
                self._log_email_correspondence(
                    patient_id=patient_id,
                    user_id=user_id,
                    recipient_email=to_email,
                    subject=subject,
                    body=body_text or body_html,
                    status='failed',
                    error_message=str(e)
                )
            
            return False
    
    def _log_email_correspondence(self, patient_id, recipient_email, subject, body, status, user_id=None, error_message=None):
        """Log email correspondence to database"""
        try:
            from models import db, PatientCorrespondence
            from datetime import datetime
            
            correspondence = PatientCorrespondence(
                patient_id=patient_id,
                user_id=user_id,
                channel='email',
                direction='outbound',
                subject=subject,
                body=body,
                recipient_email=recipient_email,
                status=status,
                error_message=error_message,
                sent_at=datetime.utcnow(),
                delivered_at=datetime.utcnow() if status == 'delivered' else None
            )
            
            db.session.add(correspondence)
            db.session.commit()
            logger.info(f"✅ Logged email correspondence for patient {patient_id}")
            
        except Exception as e:
            logger.error(f"❌ Error logging email correspondence: {e}")
            # Don't fail the email send if logging fails
            try:
                db.session.rollback()
            except:
                pass
    
    def initiate_call(self, to_phone, patient_id=None, user_id=None, twiml_url=None, log_correspondence=True):
        """
        Initiate outbound call via Twilio
        
        Args:
            to_phone (str): Recipient phone number (format: +1234567890)
            patient_id (int, optional): Patient ID for logging correspondence
            user_id (int, optional): User ID for logging correspondence
            twiml_url (str, optional): URL to TwiML for call instructions (default: simple voicemail)
            log_correspondence (bool): Whether to log to correspondence table (default: True)
            
        Returns:
            dict: {'success': bool, 'call_sid': str, 'status': str, 'error': str}
        """
        if not self.twilio_configured:
            logger.warning(f"Cannot initiate call - Twilio not configured")
            return {'success': False, 'error': 'Twilio not configured'}
        
        if not to_phone:
            logger.warning("Cannot initiate call - no phone number provided")
            return {'success': False, 'error': 'No phone number provided'}
        
        try:
            # Format phone number to E.164 format
            formatted_phone = self._format_phone_number(to_phone)
            logger.info(f"📞 Initiating call to: {formatted_phone}")
            
            # Get base URL for webhooks (from config or use default)
            from config import Config
            base_url = os.getenv('BASE_URL', 'http://localhost:5000')
            
            # If no TwiML URL provided, use inline TwiML to simply ring/dial
            if not twiml_url:
                # Use inline TwiML to dial the recipient with recording enabled
                # This creates a simple call that rings the patient's phone
                call_params = {
                    'to': formatted_phone,
                    'from_': self.twilio_phone,
                    'twiml': f'<Response><Say>Please hold while we connect you.</Say><Dial record="record-from-answer" recordingStatusCallback="{base_url}/api/webhook/call-recording" recordingStatusCallbackEvent="completed"><Number>{formatted_phone}</Number></Dial></Response>',
                    'record': True,  # Enable call recording
                    'recording_status_callback': f'{base_url}/api/webhook/call-recording',
                    'recording_status_callback_event': ['completed'],
                    'status_callback': f'{base_url}/api/webhook/call-status',
                    'status_callback_event': ['initiated', 'ringing', 'answered', 'completed']
                }
            else:
                call_params = {
                    'to': formatted_phone,
                    'from_': self.twilio_phone,
                    'url': twiml_url,
                    'record': True,  # Enable call recording
                    'recording_status_callback': f'{base_url}/api/webhook/call-recording',
                    'recording_status_callback_event': ['completed'],
                    'status_callback': f'{base_url}/api/webhook/call-status',
                    'status_callback_event': ['initiated', 'ringing', 'answered', 'completed']
                }
            
            call = self.twilio_client.calls.create(**call_params)
            
            logger.info(f"✅ Call initiated to {formatted_phone}: {call.sid}")
            
            # Log correspondence if patient_id provided
            if log_correspondence and patient_id:
                self._log_call_correspondence(
                    patient_id=patient_id,
                    user_id=user_id,
                    recipient_phone=formatted_phone,
                    call_sid=call.sid,
                    status=call.status,
                    direction='outbound'
                )
            
            return {
                'success': True,
                'call_sid': call.sid,
                'status': call.status,
                'error': None
            }
            
        except Exception as e:
            logger.error(f"❌ Error initiating call to {to_phone}: {e}")
            
            # Log failed correspondence if patient_id provided
            if log_correspondence and patient_id:
                self._log_call_correspondence(
                    patient_id=patient_id,
                    user_id=user_id,
                    recipient_phone=to_phone,
                    status='failed',
                    error_message=str(e),
                    direction='outbound'
                )
            
            return {'success': False, 'error': str(e)}
    
    def _log_call_correspondence(self, patient_id, recipient_phone, status, direction='outbound', 
                                  user_id=None, call_sid=None, call_duration=None, 
                                  recording_url=None, transcript_text=None, 
                                  transcription_status=None, error_message=None, sender_phone=None):
        """Log voice call correspondence to database"""
        try:
            from models import db, PatientCorrespondence, PatientNote
            from datetime import datetime
            
            # Use transcript as body if available, otherwise use placeholder
            body = transcript_text or f"Voice call ({direction})"
            
            correspondence = PatientCorrespondence(
                patient_id=patient_id,
                user_id=user_id,
                channel='voice',
                direction=direction,
                body=body,
                recipient_phone=recipient_phone if direction == 'outbound' else None,
                sender_phone=sender_phone if direction == 'inbound' else None,
                call_sid=call_sid,
                call_duration=call_duration,
                recording_url=recording_url,
                transcription_status=transcription_status,
                status=status,
                external_id=call_sid,
                error_message=error_message,
                sent_at=datetime.utcnow(),
                delivered_at=datetime.utcnow() if status in ['in-progress', 'ringing', 'completed'] else None
            )
            
            db.session.add(correspondence)
            db.session.commit()
            logger.info(f"✅ Logged voice call correspondence for patient {patient_id}")
            
        except Exception as e:
            logger.error(f"❌ Error logging call correspondence: {e}")
    
    def fetch_call_summary(self, call_sid):
        """
        Fetch call summary from Twilio Voice Insights API
        
        Args:
            call_sid (str): Twilio Call SID
            
        Returns:
            dict: Call summary data or None if error
        """
        if not self.twilio_configured:
            logger.warning("Cannot fetch call summary - Twilio not configured")
            return None
        
        try:
            # Use Twilio Insights API to get call summary
            # Note: Voice Insights Advanced Features must be enabled in Twilio
            summary = self.twilio_client.insights.v1.calls(call_sid).summary.fetch()
            
            logger.info(f"✅ Fetched call summary for {call_sid}")
            
            # Extract relevant information
            summary_data = {
                'call_sid': summary.call_sid,
                'call_type': summary.call_type,
                'call_state': summary.call_state,
                'answered_by': summary.answered_by,
                'processing_state': summary.processing_state,
                'duration': summary.duration,
                'connect_duration': summary.connect_duration,
                'start_time': summary.start_time.isoformat() if summary.start_time else None,
                'end_time': summary.end_time.isoformat() if summary.end_time else None,
                'tags': summary.tags or [],
                'properties': {
                    'direction': getattr(summary.properties, 'direction', None) if hasattr(summary, 'properties') else None,
                    'disconnected_by': getattr(summary.properties, 'disconnected_by', None) if hasattr(summary, 'properties') else None,
                } if hasattr(summary, 'properties') else {},
            }
            
            return summary_data
            
        except Exception as e:
            logger.error(f"❌ Error fetching call summary for {call_sid}: {e}")
            # If Voice Insights is not enabled, return None (graceful degradation)
            return None
    
    def save_call_summary_to_notes(self, patient_id, call_sid, call_summary=None, user_id=None):
        """
        Save call summary to Patient Notes
        
        Args:
            patient_id (int): Patient ID
            call_sid (str): Twilio Call SID
            call_summary (dict, optional): Call summary data (will be fetched if not provided)
            user_id (int, optional): User ID who made the call
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            # Fetch summary if not provided
            if not call_summary:
                call_summary = self.fetch_call_summary(call_sid)
            
            if not call_summary:
                logger.warning(f"Could not fetch call summary for {call_sid}")
                return False
            
            # Format summary as note text
            note_parts = [
                f"📞 **Call Summary** (Call SID: {call_sid})",
                "",
                f"**Call Details:**",
                f"- Type: {call_summary.get('call_type', 'Unknown')}",
                f"- State: {call_summary.get('call_state', 'Unknown')}",
                f"- Answered By: {call_summary.get('answered_by', 'Unknown')}",
                f"- Duration: {call_summary.get('duration', 0)} seconds",
                f"- Connected Duration: {call_summary.get('connect_duration', 0)} seconds",
            ]
            
            if call_summary.get('start_time'):
                note_parts.append(f"- Start Time: {call_summary['start_time']}")
            if call_summary.get('end_time'):
                note_parts.append(f"- End Time: {call_summary['end_time']}")
            
            if call_summary.get('tags'):
                note_parts.append(f"- Tags: {', '.join(call_summary['tags'])}")
            
            if call_summary.get('properties', {}).get('direction'):
                note_parts.append(f"- Direction: {call_summary['properties']['direction']}")
            if call_summary.get('properties', {}).get('disconnected_by'):
                note_parts.append(f"- Disconnected By: {call_summary['properties']['disconnected_by']}")
            
            note_text = "\n".join(note_parts)
            
            # Create patient note
            from models import db, PatientNote
            note = PatientNote(
                patient_id=patient_id,
                note_text=note_text,
                note_type='call_summary',
                author=f'System (Call {call_sid[:8]}...)'
            )
            
            db.session.add(note)
            db.session.commit()
            
            logger.info(f"✅ Saved call summary to patient notes for patient {patient_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error saving call summary to notes: {e}")
            db.session.rollback()
            return False
            # Don't fail the call if logging fails
            try:
                db.session.rollback()
            except:
                pass
    
    def send_appointment_confirmation(self, patient, appointment):
        """
        Send appointment confirmation via SMS and email
        
        Args:
            patient: Patient model instance
            appointment: Appointment model instance
            
        Returns:
            dict: Status of SMS and email sending
        """
        from models import NotificationTemplate
        
        start_time = appointment.start_time.strftime('%B %d, %Y at %I:%M %p')
        start_time_short = appointment.start_time.strftime('%d/%m/%Y at %I:%M %p')
        patient_name = f"{patient.first_name} {patient.last_name}"
        
        # Prepare template variables
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
        
        # Try to load custom SMS template
        sms_template = NotificationTemplate.query.filter_by(
            template_type='sms',
            template_name='appointment_confirmation',
            is_active=True,
            is_predefined=False
        ).first()
        
        if sms_template and sms_template.message:
            sms_message = self._substitute_template_variables(sms_template.message, template_vars)
        else:
            # Default SMS message
            sms_message = f"Hi {patient.first_name}, your appointment on {start_time} has been confirmed. Location: {appointment.location or 'TBD'}. See you soon!"
        
        # Try to load custom Email template
        email_template = NotificationTemplate.query.filter_by(
            template_type='email',
            template_name='appointment_confirmation',
            is_active=True,
            is_predefined=False
        ).first()
        
        if email_template:
            email_subject = self._substitute_template_variables(
                email_template.subject or f"Appointment Confirmation - {start_time}",
                template_vars
            )
            email_html = self._substitute_template_variables(email_template.message, template_vars)
            # For email, also create a plain text version from HTML
            import re
            email_text = re.sub(r'<[^>]+>', '', email_html)  # Strip HTML tags
        else:
            # Default email
            email_subject = f"Appointment Confirmation - {start_time}"
            
            email_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
                    <h2 style="color: #2563eb;">Appointment Confirmed</h2>
                    
                    <p>Hi {patient_name},</p>
                    
                    <p>Your appointment has been confirmed with the following details:</p>
                    
                    <div style="background-color: #f3f4f6; padding: 15px; border-radius: 6px; margin: 20px 0;">
                        <p style="margin: 8px 0;"><strong>Date & Time:</strong> {start_time}</p>
                        <p style="margin: 8px 0;"><strong>Duration:</strong> {appointment.duration_minutes} minutes</p>
                        <p style="margin: 8px 0;"><strong>Type:</strong> {appointment.appointment_type}</p>
                        {f'<p style="margin: 8px 0;"><strong>Practitioner:</strong> {appointment.practitioner}</p>' if appointment.practitioner else ''}
                        {f'<p style="margin: 8px 0;"><strong>Location:</strong> {appointment.location}</p>' if appointment.location else ''}
                    </div>
                    
                    {f'<p><strong>Notes:</strong> {appointment.notes}</p>' if appointment.notes else ''}
                    
                    <p style="margin-top: 20px;">If you need to reschedule or cancel, please contact us as soon as possible.</p>
                    
                    <p>We look forward to seeing you!</p>
                    
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #ddd;">
                    
                    <p style="font-size: 12px; color: #666;">
                        This is an automated message from CaptureCare® - Humanising Digital Health. Please do not reply to this email.
                    </p>
                </div>
            </body>
            </html>
            """
            
            email_text = f"""
Appointment Confirmed

Hi {patient_name},

Your appointment has been confirmed with the following details:

Date & Time: {start_time}
Duration: {appointment.duration_minutes} minutes
Type: {appointment.appointment_type}
{f'Practitioner: {appointment.practitioner}' if appointment.practitioner else ''}
{f'Location: {appointment.location}' if appointment.location else ''}

{f'Notes: {appointment.notes}' if appointment.notes else ''}

If you need to reschedule or cancel, please contact us as soon as possible.

We look forward to seeing you!

---
This is an automated message from CaptureCare® - Humanising Digital Health.
            """
        
        results = {
            'sms_sent': False,
            'email_sent': False
        }
        
        if patient.mobile or patient.phone:
            phone = patient.mobile or patient.phone
            sms_result = self.send_sms(phone, sms_message, patient_id=patient.id)
            results['sms_sent'] = sms_result.get('success', False)
        else:
            logger.info(f"No phone number for patient {patient_name} - skipping SMS")
        
        if patient.email:
            results['email_sent'] = self.send_email(patient.email, email_subject, email_html, email_text, patient_id=patient.id)
        else:
            logger.info(f"No email for patient {patient_name} - skipping email")
        
        return results
    
    def send_appointment_reminder(self, patient, appointment, reminder_type='24hr'):
        """
        Send appointment reminder SMS
        
        Args:
            patient: Patient model instance
            appointment: Appointment model instance
            reminder_type: '24hr' or 'day_before'
            
        Returns:
            dict: Status of SMS sending
        """
        from models import NotificationTemplate
        
        start_time = appointment.start_time.strftime('%B %d, %Y at %I:%M %p')
        start_time_short = appointment.start_time.strftime('%d/%m/%Y at %I:%M %p')
        patient_name = f"{patient.first_name} {patient.last_name}"
        
        # Prepare template variables
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
        
        # Determine template name based on reminder type
        template_name = f'appointment_reminder_{reminder_type}'
        
        # Try to load custom SMS template
        sms_template = NotificationTemplate.query.filter_by(
            template_type='sms',
            template_name=template_name,
            is_active=True
        ).first()
        
        if sms_template and sms_template.message:
            sms_message = self._substitute_template_variables(sms_template.message, template_vars)
        else:
            # Default messages
            if reminder_type == '24hr':
                sms_message = f"Hi {patient.first_name}, reminder: Your appointment is in 24 hours at {start_time_short}. Location: {appointment.location or 'TBD'}. See you then!"
            else:  # day_before
                sms_message = f"Hi {patient.first_name}, reminder: Your appointment is tomorrow at {start_time_short}. Location: {appointment.location or 'TBD'}. See you then!"
        
        result = {
            'success': False,
            'error': None
        }
        
        if patient.mobile or patient.phone:
            phone = patient.mobile or patient.phone
            sms_result = self.send_sms(phone, sms_message, patient_id=patient.id, log_correspondence=True)
            result['success'] = sms_result.get('success', False)
            result['error'] = sms_result.get('error')
        else:
            logger.info(f"No phone number for patient {patient_name} - skipping reminder SMS")
            result['error'] = 'No phone number'
        
        return result
    
    def _substitute_template_variables(self, template, variables):
        """Substitute {variable} placeholders in template with actual values"""
        if not template:
            return ''
        
        result = template
        for key, value in variables.items():
            result = result.replace(f'{{{key}}}', str(value))
        
        return result
    
    def send_appointment_update(self, patient, appointment):
        """
        Send appointment update notification via email
        
        Args:
            patient: Patient model instance
            appointment: Appointment model instance
            
        Returns:
            dict: Status of email sending
        """
        start_time = appointment.start_time.strftime('%B %d, %Y at %I:%M %p')
        patient_name = f"{patient.first_name} {patient.last_name}"
        
        email_subject = f"Appointment Updated - {start_time}"
        
        email_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
                <h2 style="color: #2563eb;">Appointment Updated</h2>
                
                <p>Hi {patient_name},</p>
                
                <p>Your appointment has been updated with the following details:</p>
                
                <div style="background-color: #f3f4f6; padding: 15px; border-radius: 6px; margin: 20px 0;">
                    <p style="margin: 8px 0;"><strong>Date & Time:</strong> {start_time}</p>
                    <p style="margin: 8px 0;"><strong>Duration:</strong> {appointment.duration_minutes} minutes</p>
                    <p style="margin: 8px 0;"><strong>Type:</strong> {appointment.appointment_type}</p>
                    {f'<p style="margin: 8px 0;"><strong>Practitioner:</strong> {appointment.practitioner}</p>' if appointment.practitioner else ''}
                    {f'<p style="margin: 8px 0;"><strong>Location:</strong> {appointment.location}</p>' if appointment.location else ''}
                </div>
                
                {f'<p><strong>Notes:</strong> {appointment.notes}</p>' if appointment.notes else ''}
                
                <p style="margin-top: 20px;">If you have any questions about this change, please contact us.</p>
                
                <p>We look forward to seeing you!</p>
                
                <hr style="margin: 30px 0; border: none; border-top: 1px solid #ddd;">
                
                <p style="font-size: 12px; color: #666;">
                    This is an automated message from CaptureCare® - Humanising Digital Health. Please do not reply to this email.
                </p>
            </div>
        </body>
        </html>
        """
        
        email_text = f"""
Appointment Updated

Hi {patient_name},

Your appointment has been updated with the following details:

Date & Time: {start_time}
Duration: {appointment.duration_minutes} minutes
Type: {appointment.appointment_type}
{f'Practitioner: {appointment.practitioner}' if appointment.practitioner else ''}
{f'Location: {appointment.location}' if appointment.location else ''}

{f'Notes: {appointment.notes}' if appointment.notes else ''}

If you have any questions about this change, please contact us.

We look forward to seeing you!

---
This is an automated message from CaptureCare® - Humanising Digital Health.
        """
        
        result = {
            'email_sent': False
        }
        
        if patient.email:
            result['email_sent'] = self.send_email(patient.email, email_subject, email_html, email_text, patient_id=patient.id)
        else:
            logger.info(f"No email for patient {patient_name} - skipping email")
        
        return result
