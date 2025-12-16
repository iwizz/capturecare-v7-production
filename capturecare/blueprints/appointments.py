from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for, session
from flask_login import login_required, current_user
from models import db, Appointment, User, Patient, NotificationTemplate, AvailabilityPattern, AvailabilityException, UserAvailability, Device, HealthData
from datetime import datetime, timedelta, time
import logging
import os
from sqlalchemy import orm
from functools import wraps
from withings_auth import WithingsAuthManager
from sync_health_data import HealthDataSynchronizer
from patient_matcher import ClinikoIntegration
from ai_health_reporter import AIHealthReporter
from email_sender import EmailSender
from heygen_service import HeyGenService

# Create blueprint
appointments_bp = Blueprint('appointments', __name__)
logger = logging.getLogger(__name__)

# Helper to get calendar sync service
def get_calendar_sync():
    try:
        from calendar_sync import GoogleCalendarSync
        return GoogleCalendarSync()
    except Exception as e:
        logger.warning(f"Google Calendar integration not available: {e}")
        return None

# Helper to get notification service
def get_notification_service():
    try:
        from notification_service import NotificationService
        return NotificationService()
    except Exception as e:
        logger.warning(f"Notification service not available: {e}")
        return None

# Helper for optional login required
def optional_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            # For API endpoints, return 401
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': 'Authentication required'}), 401
            # For UI endpoints, redirect to login
            flash('Please log in to access this page.', 'info')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@appointments_bp.route('/calendar')
@login_required
def master_calendar():
    """Master calendar view for practitioners"""
    patients = Patient.query.order_by(Patient.last_name).all()
    practitioners = User.query.filter_by(is_active=True).order_by(User.first_name).all()
    return render_template('calendar.html', patients=patients, practitioners=practitioners)

@appointments_bp.route('/api/calendar/events', methods=['GET'])
@login_required
def get_calendar_events():
    """Get calendar events in FullCalendar format with date range filtering - OPTIMIZED"""
    try:
        practitioner_id = request.args.get('practitioner_id')
        start_date = request.args.get('start')  # ISO format date
        end_date = request.args.get('end')  # ISO format date
        
        # Parse dates
        start_dt = None
        end_dt = None
        
        if start_date:
            try:
                start_date_clean = start_date.replace('Z', '+00:00')
                if 'T' not in start_date_clean:
                    start_date_clean = start_date_clean + 'T00:00:00'
                if '+' in start_date_clean:
                    start_date_clean = start_date_clean.split('+')[0]
                elif start_date_clean.endswith('Z'):
                    start_date_clean = start_date_clean[:-1]
                start_dt = datetime.fromisoformat(start_date_clean)
            except:
                try:
                    date_part = start_date.split('T')[0] if 'T' in start_date else start_date
                    start_dt = datetime.strptime(date_part, '%Y-%m-%d')
                except:
                    pass
        
        if end_date:
            try:
                end_date_clean = end_date.replace('Z', '+00:00')
                if 'T' not in end_date_clean:
                    end_date_clean = end_date_clean + 'T00:00:00'
                if '+' in end_date_clean:
                    end_date_clean = end_date_clean.split('+')[0]
                elif end_date_clean.endswith('Z'):
                    end_date_clean = end_date_clean[:-1]
                end_dt = datetime.fromisoformat(end_date_clean)
            except:
                try:
                    date_part = end_date.split('T')[0] if 'T' in end_date else end_date
                    end_dt = datetime.strptime(date_part, '%Y-%m-%d')
                except:
                    pass
        
        # If no dates provided, default to current month
        if not start_dt:
            start_dt = datetime.now().replace(day=1)
        if not end_dt:
            # Next month start
            if start_dt.month == 12:
                end_dt = start_dt.replace(year=start_dt.year+1, month=1)
            else:
                end_dt = start_dt.replace(month=start_dt.month+1)
        
        # Check if cache table exists
        cache_table_exists = False
        try:
            result = db.session.execute(db.text("SELECT to_regclass('public.appointment_date_cache')")).scalar()
            cache_table_exists = result is not None
        except Exception:
            pass
            
        events = []
        
        if cache_table_exists:
            # Use optimized cache query with JOIN to get full appointment data
            logger.info(f"Using optimized cache query for calendar events ({start_dt.date()} to {end_dt.date()})")
            
            # Build cache query - join with appointments table to get all fields
            # Only show non-cancelled appointments
            cache_query = """
                SELECT 
                    c.appointment_id, 
                    a.title, 
                    c.start_time, 
                    c.end_time, 
                    c.practitioner_id, 
                    u.first_name || ' ' || u.last_name as practitioner_name,
                    u.calendar_color as practitioner_color,
                    c.patient_id, 
                    p.first_name || ' ' || p.last_name as patient_name,
                    c.status, 
                    a.appointment_type, 
                    a.notes
                FROM appointment_date_cache c
                INNER JOIN appointments a ON a.id = c.appointment_id
                LEFT JOIN users u ON u.id = c.practitioner_id
                LEFT JOIN patients p ON p.id = c.patient_id
                WHERE c.date >= :start_date 
                AND c.date <= :end_date
                AND c.status != 'cancelled'
            """
            
            params = {'start_date': start_dt.date(), 'end_date': end_dt.date()}
            
            if practitioner_id:
                cache_query += " AND c.practitioner_id = :practitioner_id"
                params['practitioner_id'] = int(practitioner_id)
                
            result = db.session.execute(db.text(cache_query), params)
            
            for row in result:
                events.append({
                    'id': row.appointment_id,
                    'title': f"{row.patient_name} - {row.title}" if row.patient_name and row.title else (row.title or 'Appointment'),
                    'start': row.start_time.isoformat(),
                    'end': row.end_time.isoformat(),
                    'resourceId': row.practitioner_id,
                    'color': row.practitioner_color or '#3788d8',
                    'extendedProps': {
                        'patientId': row.patient_id,
                        'practitionerId': row.practitioner_id,
                        'practitionerName': row.practitioner_name or 'Unassigned',
                        'status': row.status,
                        'type': row.appointment_type,
                        'notes': row.notes
                    }
                })
        else:
            # Fallback to standard query
            logger.info("Cache table not found, using standard query")
            query = Appointment.query.options(
                orm.joinedload(Appointment.patient),
                orm.joinedload(Appointment.assigned_practitioner)
            )
            
            if practitioner_id:
                query = query.filter_by(practitioner_id=int(practitioner_id))
            
            if start_dt:
                query = query.filter(Appointment.start_time >= start_dt)
            if end_dt:
                query = query.filter(Appointment.start_time <= end_dt)
            
            # Only show non-cancelled appointments
            query = query.filter(Appointment.status != 'cancelled')
                
            appointments = query.all()
            
            for apt in appointments:
                practitioner_name = "Unassigned"
                color = "#3788d8"
                
                if apt.assigned_practitioner:
                    practitioner_name = apt.assigned_practitioner.full_name
                    if apt.assigned_practitioner.calendar_color:
                        color = apt.assigned_practitioner.calendar_color
                
                patient_name = "Unknown Patient"
                if apt.patient:
                    patient_name = f"{apt.patient.first_name} {apt.patient.last_name}"
                
                events.append({
                    'id': apt.id,
                    'title': f"{patient_name} - {apt.title}",
                    'start': apt.start_time.isoformat(),
                    'end': apt.end_time.isoformat(),
                    'resourceId': apt.practitioner_id,
                    'color': color,
                    'extendedProps': {
                        'patientId': apt.patient_id,
                        'practitionerId': apt.practitioner_id,
                        'practitionerName': practitioner_name,
                        'status': apt.status,
                        'type': apt.appointment_type,
                        'notes': apt.notes
                    }
                })
        
        logger.info(f"Returning {len(events)} calendar events")
        return jsonify({'success': True, 'events': events})
    except Exception as e:
        logger.error(f"Error fetching calendar events: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        try:
            db.session.remove()
        except:
            pass

@appointments_bp.route('/api/calendar/appointments', methods=['POST', 'PUT'])
@login_required
def create_or_update_calendar_appointment():
    """Create or update appointment from calendar UI (accepts date/time/duration format)"""
    try:
        data = request.get_json()
        appointment_id = request.args.get('id') or data.get('id')
        
        # Extract data from request
        patient_id = data.get('patient_id')
        practitioner_id = data.get('practitioner_id')
        title = data.get('title', 'Appointment')
        appointment_type = data.get('appointment_type') or data.get('type', 'Consultation')
        notes = data.get('notes')
        location = data.get('location')
        status = data.get('status', 'scheduled')
        
        # Parse date and time
        date_str = data.get('date')
        time_str = data.get('time')
        duration_minutes = int(data.get('duration_minutes', 60))
        
        # Combine date and time into datetime objects
        start_time = datetime.strptime(f"{date_str} {time_str}", '%Y-%m-%d %H:%M')
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        if appointment_id:
            # Update existing appointment
            appointment = Appointment.query.get_or_404(appointment_id)
            appointment.patient_id = patient_id
            appointment.practitioner_id = practitioner_id
            appointment.title = title
            appointment.appointment_type = appointment_type
            appointment.start_time = start_time
            appointment.end_time = end_time
            appointment.duration_minutes = duration_minutes
            appointment.location = location
            appointment.notes = notes
            appointment.status = status
        else:
            # Create new appointment
            appointment = Appointment(
                patient_id=patient_id,
                practitioner_id=practitioner_id,
                title=title,
                appointment_type=appointment_type,
                start_time=start_time,
                end_time=end_time,
                duration_minutes=duration_minutes,
                location=location,
                notes=notes,
                status=status,
                created_by_id=current_user.id
            )
            db.session.add(appointment)
        
        db.session.commit()
        
        # Sync to Google Calendar if configured
        calendar_sync = get_calendar_sync()
        if calendar_sync and practitioner_id:
            try:
                patient = Patient.query.get(patient_id) if patient_id else None
                patient_name = f"{patient.first_name} {patient.last_name}" if patient else "Unknown Patient"
                description = f"Patient: {patient_name}\nType: {appointment_type}\nNotes: {notes or 'None'}"
                
                if appointment.google_calendar_event_id:
                    # Update existing event
                    calendar_sync.update_event(
                        event_id=appointment.google_calendar_event_id,
                        summary=f"{title} - {patient_name}",
                        start_time=start_time,
                        end_time=end_time,
                        description=description
                    )
                else:
                    # Create new event
                    event_id = calendar_sync.create_event(
                        summary=f"{title} - {patient_name}",
                        start_time=start_time,
                        end_time=end_time,
                        description=description,
                        attendee_email=patient.email if patient else None
                    )
                    if event_id:
                        appointment.google_calendar_event_id = event_id
                        db.session.commit()
                        logger.info(f"Synced appointment {appointment.id} to Google Calendar: {event_id}")
            except Exception as e:
                logger.error(f"Failed to sync to Google Calendar: {e}")
        
        return jsonify({
            'success': True,
            'appointment': {
                'id': appointment.id,
                'title': appointment.title,
                'start': appointment.start_time.isoformat(),
                'end': appointment.end_time.isoformat()
            }
        })
    except Exception as e:
        logger.error(f"Error creating/updating calendar appointment: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@appointments_bp.route('/api/appointments', methods=['POST'])
@login_required
def create_appointment():
    try:
        data = request.get_json()
        
        patient_id = data.get('patient_id')
        practitioner_id = data.get('practitioner_id')
        title = data.get('title')
        start_time_str = data.get('start_time')
        end_time_str = data.get('end_time')
        notes = data.get('notes')
        location = data.get('location')
        appointment_type = data.get('type', 'Consultation')
        
        start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
        end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
        
        # Remove timezone info for database storage if needed
        if start_time.tzinfo:
            start_time = start_time.replace(tzinfo=None)
        if end_time.tzinfo:
            end_time = end_time.replace(tzinfo=None)
        
        # Calculate duration in minutes
        duration_minutes = int((end_time - start_time).total_seconds() / 60)
            
        appointment = Appointment(
            patient_id=patient_id,
            practitioner_id=practitioner_id,
            title=title,
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration_minutes,
            location=location,
            notes=notes,
            appointment_type=appointment_type,
            status='scheduled',
            created_by_id=current_user.id
        )
        
        db.session.add(appointment)
        db.session.commit()
        
        # Sync to Google Calendar if configured
        calendar_sync = get_calendar_sync()
        patient = Patient.query.get(patient_id)
        patient_name = f"{patient.first_name} {patient.last_name}" if patient else "Unknown Patient"
        
        if calendar_sync and practitioner_id:
            try:
                practitioner = User.query.get(practitioner_id)
                # Only sync if practitioner has a Google Calendar ID configured (implied, currently we use global calendar)
                # Future: Support individual practitioner calendars
                
                # Format description
                description = f"Patient: {patient_name}\nType: {appointment_type}\nNotes: {notes or 'None'}"
                
                event_id = calendar_sync.create_event(
                    summary=f"{title} - {patient_name}",
                    start_time=start_time,
                    end_time=end_time,
                    description=description,
                    attendee_email=patient.email if patient else None
                )
                
                if event_id:
                    appointment.google_calendar_event_id = event_id
                    db.session.commit()
                    logger.info(f"Synced appointment {appointment.id} to Google Calendar: {event_id}")
            except Exception as e:
                logger.error(f"Failed to sync to Google Calendar: {e}")
                # Don't fail the request, just log error
        
        # Automatically send SMS notification and log to correspondence
        notification_result = {'sms': False, 'email': False}
        if patient:
            try:
                from notification_service import NotificationService
                notification_service = NotificationService()
                
                # Prepare template variables
                start_time_formatted = appointment.start_time.strftime('%d/%m/%Y at %I:%M %p')
                practitioner_name = User.query.get(practitioner_id).full_name if practitioner_id else 'Your practitioner'
                
                # Send SMS if mobile or phone available
                if patient.mobile or patient.phone:
                    try:
                        # Get custom SMS template if exists
                        from models import NotificationTemplate
                        sms_template = NotificationTemplate.query.filter_by(
                            template_type='sms',
                            template_name='appointment_confirmation',
                            is_active=True
                        ).first()
                        
                        if sms_template and sms_template.message:
                            # Substitute template variables
                            sms_message = sms_template.message.format(
                                patient_name=patient.first_name,
                                first_name=patient.first_name,
                                last_name=patient.last_name,
                                date=appointment.start_time.strftime('%d/%m/%Y'),
                                time=appointment.start_time.strftime('%I:%M %p'),
                                date_time=start_time_formatted,
                                date_time_short=start_time_formatted,
                                practitioner=practitioner_name,
                                location=appointment.location or 'TBD',
                                appointment_type=appointment.appointment_type or 'Appointment',
                                duration=f"{appointment.duration_minutes} minutes"
                            )
                        else:
                            # Default SMS message
                            sms_message = f"Hi {patient.first_name}, your appointment has been confirmed for {start_time_formatted}. Location: {appointment.location or 'TBD'}. See you soon!"
                        
                        # Send SMS and log to correspondence
                        sms_result = notification_service.send_sms(
                            to_phone=patient.mobile or patient.phone,
                            message=sms_message,
                            patient_id=patient.id,
                            user_id=current_user.id,
                            log_correspondence=True
                        )
                        
                        if sms_result.get('success'):
                            notification_result['sms'] = True
                            logger.info(f"✅ Sent appointment confirmation SMS for appointment {appointment.id}")
                        else:
                            logger.warning(f"Failed to send SMS for appointment {appointment.id}: {sms_result.get('error')}")
                    except Exception as sms_error:
                        logger.error(f"Error sending SMS for appointment {appointment.id}: {sms_error}")
                else:
                    logger.info(f"No phone number available for patient {patient.id}, skipping SMS")
                    
            except Exception as notif_error:
                logger.error(f"Error sending appointment notification: {notif_error}")
                # Don't fail the appointment creation if notification fails
        
        return jsonify({
            'success': True,
            'appointment': {
                'id': appointment.id,
                'title': appointment.title,
                'start': appointment.start_time.isoformat(),
                'end': appointment.end_time.isoformat()
            },
            'notification_sent': notification_result
        })
    except Exception as e:
        logger.error(f"Error creating appointment: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@appointments_bp.route('/api/appointments/<int:appointment_id>', methods=['PUT', 'DELETE'])
@login_required
def manage_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    
    if request.method == 'DELETE':
        try:
            # Remove from Google Calendar if synced
            calendar_sync = get_calendar_sync()
            if calendar_sync and appointment.google_calendar_event_id:
                try:
                    calendar_sync.delete_event(appointment.google_calendar_event_id)
                except Exception as e:
                    logger.error(f"Failed to delete from Google Calendar: {e}")
            
            db.session.delete(appointment)
            db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400
            
    elif request.method == 'PUT':
        try:
            data = request.get_json()
            
            if 'start_time' in data:
                start_time = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
                if start_time.tzinfo:
                    start_time = start_time.replace(tzinfo=None)
                appointment.start_time = start_time
                
            if 'end_time' in data:
                end_time = datetime.fromisoformat(data['end_time'].replace('Z', '+00:00'))
                if end_time.tzinfo:
                    end_time = end_time.replace(tzinfo=None)
                appointment.end_time = end_time
                
            if 'title' in data:
                appointment.title = data['title']
            if 'notes' in data:
                appointment.notes = data['notes']
            if 'status' in data:
                appointment.status = data['status']
            if 'practitioner_id' in data:
                appointment.practitioner_id = data['practitioner_id']
                
            db.session.commit()
            
            # Update Google Calendar if synced
            calendar_sync = get_calendar_sync()
            if calendar_sync and appointment.google_calendar_event_id:
                try:
                    # Get updated details
                    patient = appointment.patient
                    patient_name = f"{patient.first_name} {patient.last_name}" if patient else "Unknown Patient"
                    description = f"Patient: {patient_name}\nType: {appointment.appointment_type}\nNotes: {appointment.notes or 'None'}"
                    
                    calendar_sync.update_event(
                        event_id=appointment.google_calendar_event_id,
                        summary=f"{appointment.title} - {patient_name}",
                        start_time=appointment.start_time,
                        end_time=appointment.end_time,
                        description=description
                    )
                except Exception as e:
                    logger.error(f"Failed to update Google Calendar: {e}")
            
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400

@appointments_bp.route('/api/appointments/<int:appointment_id>/send-confirmation', methods=['POST'])
@login_required
def send_appointment_confirmation(appointment_id):
    """Send appointment confirmation via SMS/Email"""
    try:
        appointment = Appointment.query.get_or_404(appointment_id)
        patient = appointment.patient
        
        if not patient:
            return jsonify({'success': False, 'error': 'No patient associated with this appointment'}), 400
            
        # Get notification service (assumed to be in app context or created fresh)
        from notification_service import NotificationService
        notification_service = NotificationService()
        
        results = {
            'sms': False,
            'email': False,
            'errors': []
        }
        
        # Send SMS if phone available
        if patient.mobile or patient.phone:
            try:
                # Get custom template if exists
                template = NotificationTemplate.query.filter_by(
                    template_type='sms',
                    template_name='appointment_confirmation',
                    is_active=True
                ).first()
                
                message = None
                if template:
                    message = template.message.format(
                        patient_name=patient.first_name,
                        date=appointment.start_time.strftime('%d/%m/%Y'),
                        time=appointment.start_time.strftime('%I:%M %p'),
                        practitioner=appointment.assigned_practitioner.full_name if appointment.assigned_practitioner else 'CaptureCare'
                    )
                
                if notification_service.send_sms(
                    to_number=patient.mobile or patient.phone,
                    message=message,  # Will use default if None
                    patient_id=patient.id,
                    appointment_id=appointment.id,
                    user_id=current_user.id
                ):
                    results['sms'] = True
            except Exception as e:
                logger.error(f"SMS error: {e}")
                results['errors'].append(f"SMS error: {str(e)}")
        
        # Send Email if email available
        if patient.email:
            try:
                template = NotificationTemplate.query.filter_by(
                    template_type='email',
                    template_name='appointment_confirmation',
                    is_active=True
                ).first()
                
                subject = None
                body = None
                
                if template:
                    subject = template.subject
                    body = template.message.format(
                        patient_name=patient.first_name,
                        date=appointment.start_time.strftime('%d/%m/%Y'),
                        time=appointment.start_time.strftime('%I:%M %p'),
                        practitioner=appointment.assigned_practitioner.full_name if appointment.assigned_practitioner else 'CaptureCare',
                        location="CaptureCare Clinic" # Could be dynamic
                    )
                
                if notification_service.send_email(
                    to_email=patient.email,
                    subject=subject,
                    body_text=body,
                    patient_id=patient.id,
                    user_id=current_user.id
                ):
                    results['email'] = True
            except Exception as e:
                logger.error(f"Email error: {e}")
                results['errors'].append(f"Email error: {str(e)}")
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        logger.error(f"Error sending confirmation: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@appointments_bp.route('/api/calendar/cache/setup', methods=['GET', 'POST'])
def setup_calendar_cache():
    """Setup the calendar cache table and triggers"""
    if not current_user.is_authenticated and not current_app.config.get('DEBUG'):
        return jsonify({'success': False, 'error': 'Authentication required'}), 401
        
    try:
        # Read the SQL file
        sql_path = os.path.join(current_app.root_path, '..', 'scripts', 'create_appointment_cache.sql')
        if not os.path.exists(sql_path):
            # Fallback if running from different directory
            sql_path = os.path.join('scripts', 'create_appointment_cache.sql')
            
        if not os.path.exists(sql_path):
            return jsonify({'success': False, 'error': f'SQL file not found at {sql_path}'}), 404
            
        with open(sql_path, 'r') as f:
            sql_script = f.read()
            
        # Split into individual statements (naive split by semicolon at end of line)
        # Better approach: use sqlalchemy execute directly if it supports multi-statement
        # or split intelligently
        
        # Remove comments
        statements = [s.strip() for s in sql_script.split(';') if s.strip()]
        
        executed = []
        for stmt in statements:
            if stmt.startswith('--'): 
                continue
            
            # Skip psql meta commands
            if stmt.startswith('\\'):
                continue
                
            try:
                db.session.execute(db.text(stmt))
                executed.append(stmt[:50] + '...')
            except Exception as e:
                logger.warning(f"Statement failed (might already exist): {e}")
        
        db.session.commit()
        
        # Initialize cache with current data
        db.session.execute(db.text("SELECT refresh_appointment_cache('2024-01-01', '2026-12-31')"))
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Cache table and triggers created successfully',
            'executed_statements': len(executed)
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error setting up cache: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@appointments_bp.route('/api/reminders/setup', methods=['GET', 'POST'])
def setup_reminders():
    """Setup reminder columns and templates"""
    if not current_user.is_authenticated and not current_app.config.get('DEBUG'):
        return jsonify({'success': False, 'error': 'Authentication required'}), 401
        
    try:
        # 1. Add columns to appointments table if they don't exist
        try:
            db.session.execute(db.text("""
                ALTER TABLE appointments 
                ADD COLUMN IF NOT EXISTS reminder_24hr_sent BOOLEAN DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS reminder_24hr_sent_at TIMESTAMP,
                ADD COLUMN IF NOT EXISTS reminder_day_before_sent BOOLEAN DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS reminder_day_before_sent_at TIMESTAMP,
                ADD COLUMN IF NOT EXISTS reminder_1hr_sent BOOLEAN DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS reminder_1hr_sent_at TIMESTAMP;
            """))
            db.session.commit()
            columns_added = True
        except Exception as e:
            logger.warning(f"Column addition warning: {e}")
            db.session.rollback()
            columns_added = False

        # 2. Create default templates
        try:
            # Check if templates exist
            existing = NotificationTemplate.query.filter_by(
                template_type='sms', 
                template_name='appointment_reminder_24h'
            ).first()
            
            if not existing:
                t1 = NotificationTemplate(
                    template_type='sms',
                    template_name='appointment_reminder_24h',
                    message="Hi {patient_name}, reminder for your appointment with {practitioner} tomorrow at {time}. Reply NO to cancel.",
                    is_predefined=True,
                    is_active=True
                )
                db.session.add(t1)
            
            existing_day = NotificationTemplate.query.filter_by(
                template_type='sms', 
                template_name='appointment_reminder_day_before'
            ).first()
            
            if not existing_day:
                t2 = NotificationTemplate(
                    template_type='sms',
                    template_name='appointment_reminder_day_before',
                    message="Hi {patient_name}, you have an appointment with {practitioner} tomorrow ({date}) at {time}.",
                    is_predefined=True,
                    is_active=True
                )
                db.session.add(t2)
                
            db.session.commit()
            templates_created = True
        except Exception as e:
            logger.error(f"Template creation error: {e}")
            db.session.rollback()
            templates_created = False
            
        return jsonify({
            'success': True,
            'migration': columns_added,
            'templates': templates_created
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@appointments_bp.route('/api/reminders/check', methods=['POST'])
def check_reminders():
    """Manually trigger reminder check (for testing/admin and Cloud Scheduler)"""
    if not current_user.is_authenticated and not current_app.config.get('DEBUG'):
        return jsonify({'success': False, 'error': 'Authentication required'}), 401
    try:
        from appointment_reminder_service import AppointmentReminderService
        
        reminder_service = AppointmentReminderService()
        stats = reminder_service.check_and_send_reminders()
        
        return jsonify({
            'success': True,
            'stats': stats,
            'message': f"Checked {stats['checked']} appointments, sent {stats['24hr_sent']} 24hr reminders and {stats['day_before_sent']} day-before reminders"
        })
    except Exception as e:
        logger.error(f"Error checking reminders: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@appointments_bp.route('/api/reminders/status/<int:appointment_id>', methods=['GET'])
@login_required
def get_reminder_status(appointment_id):
    """Get reminder status for an appointment"""
    try:
        appointment = Appointment.query.get_or_404(appointment_id)
        
        return jsonify({
            'success': True,
            'reminder_status': {
                'reminder_24hr_sent': appointment.reminder_24hr_sent,
                'reminder_24hr_sent_at': appointment.reminder_24hr_sent_at.isoformat() if appointment.reminder_24hr_sent_at else None,
                'reminder_day_before_sent': appointment.reminder_day_before_sent,
                'reminder_day_before_sent_at': appointment.reminder_day_before_sent_at.isoformat() if appointment.reminder_day_before_sent_at else None,
                'reminder_1hr_sent': appointment.reminder_1hr_sent,
                'reminder_1hr_sent_at': appointment.reminder_1hr_sent_at.isoformat() if appointment.reminder_1hr_sent_at else None
            }
        })
    except Exception as e:
        logger.error(f"Error getting reminder status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@appointments_bp.route('/api/calendar/appointments/<int:appointment_id>/move', methods=['PUT'])
@login_required
def move_calendar_appointment(appointment_id):
    """Move appointment (drag and drop)"""
    try:
        appointment = Appointment.query.get_or_404(appointment_id)
        data = request.get_json()
        
        # Store old time for SMS notification
        old_start_time = appointment.start_time
        
        # Update start and end times
        appointment.start_time = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
        appointment.end_time = datetime.fromisoformat(data['end_time'].replace('Z', '+00:00'))
        appointment.duration_minutes = int((appointment.end_time - appointment.start_time).total_seconds() / 60)
        
        db.session.commit()
        
        # Sync with Google Calendar
        calendar_sync = get_calendar_sync()
        if calendar_sync and appointment.google_calendar_event_id:
            try:
                # Get updated details
                patient = appointment.patient
                patient_name = f"{patient.first_name} {patient.last_name}" if patient else "Unknown Patient"
                description = f"Patient: {patient_name}\nType: {appointment.appointment_type}\nNotes: {appointment.notes or 'None'}"
                
                calendar_sync.update_event(
                    event_id=appointment.google_calendar_event_id,
                    summary=f"{appointment.title} - {patient_name}",
                    start_time=appointment.start_time,
                    end_time=appointment.end_time,
                    description=description
                )
            except Exception as e:
                logger.warning(f"Google Calendar sync failed: {e}")
        
        # Return patient info for SMS notification
        return jsonify({
            'success': True,
            'patient_name': f"{appointment.patient.first_name} {appointment.patient.last_name}",
            'patient_phone': appointment.patient.mobile or appointment.patient.phone or '',
            'old_start_time': old_start_time.isoformat() if old_start_time else None
        })
    except Exception as e:
        logger.error(f"Error moving appointment: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@appointments_bp.route('/api/calendar/appointments/<int:appointment_id>/notify', methods=['POST'])
@login_required
def notify_appointment_change(appointment_id):
    """Send SMS notification for appointment change"""
    try:
        appointment = Appointment.query.get_or_404(appointment_id)
        data = request.get_json()
        
        message = data.get('message', '')
        phone = data.get('phone', '')
        
        if not phone:
            return jsonify({'success': False, 'error': 'Phone number required'}), 400
        
        # Send SMS via notification service
        notification_service = get_notification_service()
        result = notification_service.send_sms(phone, message)
        
        if result.get('success'):
            return jsonify({'success': True, 'message': 'SMS sent successfully'})
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Failed to send SMS')}), 400
            
    except Exception as e:
        logger.error(f"Error sending notification: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@appointments_bp.route('/api/calendar/availability-blocks', methods=['GET'])
@login_required
def get_availability_blocks():
    """Get availability blocks for all practitioners for calendar display"""
    try:
        start_date_str = request.args.get('start')
        end_date_str = request.args.get('end')
        practitioner_id = request.args.get('practitioner_id')
        
        if not start_date_str or not end_date_str:
            return jsonify({'success': False, 'error': 'Start and end dates required'}), 400
        
        try:
            # Handle date strings that might have time components
            start_date_clean = start_date_str.split('T')[0] if 'T' in start_date_str else start_date_str
            end_date_clean = end_date_str.split('T')[0] if 'T' in end_date_str else end_date_str
            
            start_date = datetime.strptime(start_date_clean, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_clean, '%Y-%m-%d').date()
        except ValueError as e:
            logger.error(f"Invalid date format: start={start_date_str}, end={end_date_str}, error={e}")
            return jsonify({'success': False, 'error': f'Invalid date format: {str(e)}'}), 400
        
        # Get practitioners to show
        if practitioner_id:
            practitioner = User.query.filter_by(id=int(practitioner_id), is_active=True).first()
            practitioners = [practitioner] if practitioner else []
        else:
            practitioners = User.query.filter_by(is_active=True).all()
        
        availability_blocks = []
        
        # Ensure we have a clean transaction
        try:
            db.session.rollback()  # Start fresh
        except:
            pass
        
        for practitioner in practitioners:
            if not practitioner:
                continue
            try:
                # Ensure practitioner ID is accessible
                practitioner_id = int(practitioner.id) if hasattr(practitioner, 'id') else None
                if not practitioner_id:
                    continue
                    
                # Get all active patterns
                patterns = AvailabilityPattern.query.filter_by(
                    user_id=practitioner_id,
                    is_active=True
                ).all()
                
                # Get exceptions in date range
                exceptions = AvailabilityException.query.filter(
                    AvailabilityException.user_id == practitioner_id,
                    AvailabilityException.exception_date >= start_date,
                    AvailabilityException.exception_date <= end_date
                ).all()
            except Exception as e:
                logger.error(f"Error loading patterns/exceptions for practitioner: {e}")
                db.session.rollback()
                continue  # Skip this practitioner
            
            # Generate availability blocks for each day in range
            current_date = start_date
            while current_date <= end_date:
                day_of_week_num = current_date.weekday()
                
                # Check if entire day is blocked
                day_exceptions = [ex for ex in exceptions if ex.exception_date == current_date]
                full_day_block = any(ex.is_all_day and ex.exception_type in ['blocked', 'holiday', 'vacation'] 
                                    for ex in day_exceptions)
                
                if not full_day_block:
                    # Check each pattern
                    for pattern in patterns:
                        # Check validity period
                        if pattern.valid_from and current_date < pattern.valid_from:
                            continue
                        if pattern.valid_until and current_date > pattern.valid_until:
                            continue
                        
                        # Check if pattern applies to this day
                        applies = False
                        if pattern.frequency == 'daily':
                            applies = True
                        elif pattern.frequency == 'weekdays' and day_of_week_num < 5:
                            applies = True
                        elif pattern.frequency in ['weekly', 'custom']:
                            if pattern.weekdays and pattern.weekdays.strip():
                                try:
                                    day_numbers = [int(d.strip()) for d in pattern.weekdays.split(',') if d.strip().isdigit()]
                                    applies = day_of_week_num in day_numbers
                                except (ValueError, AttributeError):
                                    applies = False
                            else:
                                applies = False
                        
                        if applies:
                            # Get partial blocks for this day
                            partial_blocks = [(ex.start_time, ex.end_time) 
                                            for ex in day_exceptions 
                                            if not ex.is_all_day]
                            
                            # Create availability block
                            start_datetime = datetime.combine(current_date, pattern.start_time)
                            end_datetime = datetime.combine(current_date, pattern.end_time)
                            
                            # Check if blocked by exception
                            is_blocked = any(
                                (block_start <= pattern.start_time < block_end) or
                                (block_start < pattern.end_time <= block_end) or
                                (pattern.start_time <= block_start and pattern.end_time >= block_end)
                                for block_start, block_end in partial_blocks
                            )
                            
                            if not is_blocked:
                                availability_blocks.append({
                                    'title': f'{pattern.title} - {practitioner.full_name}',
                                    'start': start_datetime.isoformat(),
                                    'end': end_datetime.isoformat(),
                                    'backgroundColor': pattern.color or practitioner.calendar_color or '#10b981',
                                    'borderColor': pattern.color or practitioner.calendar_color or '#10b981',
                                    'textColor': '#ffffff',
                                    'display': 'background',
                                    'extendedProps': {
                                        'type': 'availability',
                                        'practitioner_id': practitioner.id,
                                        'practitioner_name': practitioner.full_name,
                                        'pattern_id': pattern.id,
                                        'pattern_title': pattern.title
                                    }
                                })
                
                current_date += timedelta(days=1)
        
        return jsonify({
            'success': True,
            'blocks': availability_blocks
        })
    except Exception as e:
        logger.error(f"Error getting availability blocks: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e), 'message': str(e)}), 500

@appointments_bp.route('/api/calendar/block-slot', methods=['POST'])
@login_required
def block_time_slot():
    """Block a specific time slot for a practitioner"""
    try:
        data = request.get_json()
        practitioner_id = data.get('practitioner_id')
        date_str = data.get('date')
        start_time_str = data.get('start_time')
        end_time_str = data.get('end_time')
        reason = data.get('reason', 'Blocked for capacity')
        
        if not practitioner_id or not date_str or not start_time_str:
            return jsonify({'success': False, 'error': 'Practitioner ID, date, and start time are required'}), 400
        
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Parse times
        start_h, start_m = map(int, start_time_str.split(':'))
        start_time = time(start_h, start_m)
        
        # Default to 30-minute block if end_time not provided
        if end_time_str:
            end_h, end_m = map(int, end_time_str.split(':'))
            end_time = time(end_h, end_m)
        else:
            # Add 30 minutes to start time
            dt = datetime.combine(target_date, start_time)
            dt += timedelta(minutes=30)
            end_time = dt.time()
        
        # Check if block already exists
        existing = AvailabilityException.query.filter_by(
            user_id=practitioner_id,
            exception_date=target_date,
            is_all_day=False
        ).filter(
            db.or_(
                db.and_(
                    AvailabilityException.start_time <= start_time,
                    AvailabilityException.end_time > start_time
                ),
                db.and_(
                    AvailabilityException.start_time < end_time,
                    AvailabilityException.end_time >= end_time
                ),
                db.and_(
                    AvailabilityException.start_time >= start_time,
                    AvailabilityException.end_time <= end_time
                )
            )
        ).first()
        
        if existing:
            # Unblock - delete the exception
            db.session.delete(existing)
            db.session.commit()
            return jsonify({
                'success': True,
                'action': 'unblocked',
                'message': 'Time slot unblocked successfully'
            })
        else:
            # Block - create exception
            exception = AvailabilityException(
                user_id=practitioner_id,
                exception_date=target_date,
                exception_type='blocked',
                is_all_day=False,
                start_time=start_time,
                end_time=end_time,
                reason=reason
            )
            db.session.add(exception)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'action': 'blocked',
                'message': 'Time slot blocked successfully',
                'exception_id': exception.id
            })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error blocking time slot: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@appointments_bp.route('/api/calendar/availability/batch', methods=['POST'])
@login_required
def get_batch_availability():
    """Get availability for multiple practitioners and dates in one request"""
    try:
        data = request.get_json()
        practitioner_ids = data.get('practitioner_ids', [])
        dates = data.get('dates', [])  # List of date strings in YYYY-MM-DD format
        duration_minutes = int(data.get('duration', 30))
        
        if not practitioner_ids or not dates:
            return jsonify({'success': False, 'error': 'practitioner_ids and dates required'}), 400
        
        result = {}
        
        for practitioner_id in practitioner_ids:
            practitioner = User.query.get(practitioner_id)
            if not practitioner:
                continue
            
            result[practitioner_id] = {}
            
            # Get availability patterns once
            patterns = AvailabilityPattern.query.filter_by(
                user_id=practitioner_id,
                is_active=True
            ).all()
            
            for date_str in dates:
                try:
                    target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    
                    # Check for company-wide blocks first (practice closed)
                    company_wide_blocks = AvailabilityException.query.filter_by(
                        is_company_wide=True,
                        exception_date=target_date
                    ).all()
                    
                    # If practice is closed company-wide, no one is available
                    company_wide_full_block = any(ex.is_all_day and ex.exception_type in ['blocked', 'holiday', 'vacation'] 
                                                 for ex in company_wide_blocks)
                    
                    # Get exceptions for this practitioner
                    exceptions = AvailabilityException.query.filter_by(
                        user_id=practitioner_id,
                        exception_date=target_date
                    ).all()
                    
                    # Check if entire day is blocked (company-wide OR individual)
                    full_day_block = company_wide_full_block or any(ex.is_all_day and ex.exception_type in ['blocked', 'holiday', 'vacation'] 
                                        for ex in exceptions)
                    
                    available_slots = []
                    booked_slots = []
                    
                    if not full_day_block and patterns:
                        # Process patterns and exceptions (same logic as single date endpoint)
                        for pattern in patterns:
                            # Check if pattern is valid for this date
                            if pattern.valid_from and target_date < pattern.valid_from:
                                continue
                            if pattern.valid_until and target_date > pattern.valid_until:
                                continue
                            
                            # Check if pattern applies to this day of week
                            day_of_week_num = target_date.weekday()  # 0=Monday, 6=Sunday
                            applies = False
                            
                            if pattern.frequency == 'daily':
                                applies = True
                            elif pattern.frequency == 'weekdays' and day_of_week_num < 5:  # Mon-Fri
                                applies = True
                            elif pattern.frequency == 'weekly' or pattern.frequency == 'custom':
                                if pattern.weekdays:
                                    day_numbers = [int(d.strip()) for d in pattern.weekdays.split(',') if d.strip().isdigit()]
                                    applies = day_of_week_num in day_numbers
                            
                            if applies:
                                # Get partial blocks for this day (company-wide + individual)
                                partial_blocks = []
                                # Company-wide partial blocks
                                for ex in company_wide_blocks:
                                    if not ex.is_all_day and ex.start_time and ex.end_time:
                                        try:
                                            if isinstance(ex.start_time, str):
                                                block_start = datetime.strptime(ex.start_time, '%H:%M').time()
                                            else:
                                                block_start = ex.start_time
                                                
                                            if isinstance(ex.end_time, str):
                                                block_end = datetime.strptime(ex.end_time, '%H:%M').time()
                                            else:
                                                block_end = ex.end_time
                                                
                                            partial_blocks.append((block_start, block_end))
                                        except:
                                            pass
                                
                                # Individual practitioner partial blocks
                                for ex in exceptions:
                                    if not ex.is_all_day and ex.start_time and ex.end_time:
                                        try:
                                            if isinstance(ex.start_time, str):
                                                block_start = datetime.strptime(ex.start_time, '%H:%M').time()
                                            else:
                                                block_start = ex.start_time
                                                
                                            if isinstance(ex.end_time, str):
                                                block_end = datetime.strptime(ex.end_time, '%H:%M').time()
                                            else:
                                                block_end = ex.end_time
                                                
                                            partial_blocks.append((block_start, block_end))
                                        except:
                                            pass
                                
                                # Generate time slots (every 30 minutes)
                                try:
                                    if isinstance(pattern.start_time, str):
                                        start_time = datetime.strptime(pattern.start_time, '%H:%M').time()
                                    else:
                                        start_time = pattern.start_time

                                    if isinstance(pattern.end_time, str):
                                        end_time = datetime.strptime(pattern.end_time, '%H:%M').time()
                                    else:
                                        end_time = pattern.end_time
                                    current_time = start_time
                                    
                                    while current_time < end_time:
                                        # Check if this slot is blocked by an exception
                                        is_blocked = any(
                                            (block_start <= current_time < block_end)
                                            for block_start, block_end in partial_blocks
                                        )
                                        
                                        if not is_blocked:
                                            # Check if slot has continuous availability for duration
                                            slot_datetime = datetime.combine(target_date, current_time)
                                            end_slot_datetime = slot_datetime + timedelta(minutes=duration_minutes)
                                            
                                            # Verify all 30-minute intervals in this duration are available
                                            has_continuous = True
                                            check_time = slot_datetime
                                            while check_time < end_slot_datetime:
                                                check_time_obj = check_time.time()
                                                if any(block_start <= check_time_obj < block_end for block_start, block_end in partial_blocks):
                                                    has_continuous = False
                                                    break
                                                check_time += timedelta(minutes=30)
                                            
                                            if has_continuous:
                                                available_slots.append(current_time.strftime('%H:%M'))
                                        
                                        # Increment by 30 minutes
                                        dt = datetime.combine(target_date, current_time)
                                        dt += timedelta(minutes=30)
                                        current_time = dt.time()
                                except Exception as e:
                                    logger.warning(f"Error processing pattern {pattern.id} for {date_str}: {e}")
                                    continue
                        
                        # Get booked appointments for this date
                        try:
                            appointments = Appointment.query.filter(
                                Appointment.practitioner_id == practitioner_id,
                                db.func.date(Appointment.start_time) == target_date
                            ).all()
                            
                            for apt in appointments:
                                booked_slots.append(apt.start_time.strftime('%H:%M'))
                        except Exception as db_error:
                            # If reminder fields don't exist, try to add them or use raw SQL
                            error_str = str(db_error).lower()
                            if 'reminder' in error_str and 'does not exist' in error_str:
                                try:
                                    from sqlalchemy import text
                                    db.session.execute(text("""
                                        ALTER TABLE appointments 
                                        ADD COLUMN IF NOT EXISTS reminder_24hr_sent BOOLEAN DEFAULT FALSE;
                                    """))
                                    db.session.execute(text("""
                                        ALTER TABLE appointments 
                                        ADD COLUMN IF NOT EXISTS reminder_24hr_sent_at TIMESTAMP;
                                    """))
                                    db.session.execute(text("""
                                        ALTER TABLE appointments 
                                        ADD COLUMN IF NOT EXISTS reminder_day_before_sent BOOLEAN DEFAULT FALSE;
                                    """))
                                    db.session.execute(text("""
                                        ALTER TABLE appointments 
                                        ADD COLUMN IF NOT EXISTS reminder_day_before_sent_at TIMESTAMP;
                                    """))
                                    db.session.execute(text("""
                                        ALTER TABLE appointments 
                                        ADD COLUMN IF NOT EXISTS reminder_1hr_sent BOOLEAN DEFAULT FALSE;
                                    """))
                                    db.session.execute(text("""
                                        ALTER TABLE appointments 
                                        ADD COLUMN IF NOT EXISTS reminder_1hr_sent_at TIMESTAMP;
                                    """))
                                    db.session.commit()
                                    # Retry query
                                    appointments = Appointment.query.filter(
                                        Appointment.practitioner_id == practitioner_id,
                                        db.func.date(Appointment.start_time) == target_date
                                    ).all()
                                    for apt in appointments:
                                        booked_slots.append(apt.start_time.strftime('%H:%M'))
                                except:
                                    db.session.rollback()
                                    # Use raw SQL as fallback
                                    from sqlalchemy import text
                                    appointments_raw = db.session.execute(text("""
                                        SELECT start_time FROM appointments
                                        WHERE practitioner_id = :pract_id 
                                          AND date(start_time) = :target_date
                                    """), {
                                        'pract_id': practitioner_id,
                                        'target_date': target_date
                                    }).fetchall()
                                    for row in appointments_raw:
                                        if row[0]:
                                            booked_slots.append(row[0].strftime('%H:%M'))
                            else:
                                raise
                    
                    result[practitioner_id][date_str] = {
                        'available_slots': available_slots,
                        'booked_slots': booked_slots,
                        'is_blocked': full_day_block
                    }
                except ValueError as e:
                    logger.warning(f"Invalid date format {date_str}: {e}")
                    continue  # Invalid date format
        
        return jsonify({'success': True, 'availability': result})
    except Exception as e:
        logger.error(f"Error fetching batch availability: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@appointments_bp.route('/api/calendar/availability/<int:practitioner_id>', methods=['GET'])
@optional_login_required
def get_practitioner_availability(practitioner_id):
    """Get practitioner availability for a specific date"""
    try:
        date_str = request.args.get('date')
        duration_minutes = int(request.args.get('duration', 60))
        
        if not date_str:
            return jsonify({'success': False, 'error': 'Date parameter required'}), 400
        
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        practitioner = User.query.get_or_404(practitioner_id)
        
        available_slots = []
        booked_slots = []
        
        # Get availability patterns for this practitioner
        patterns = AvailabilityPattern.query.filter_by(
            user_id=practitioner_id,
            is_active=True
        ).all()
        
        # Log for debugging
        logger.info(f"Availability check: practitioner_id={practitioner_id}, date={date_str}, duration={duration_minutes}")
        logger.info(f"Found {len(patterns)} availability patterns")
        
        # Check for company-wide blocks first (practice closed)
        company_wide_blocks = AvailabilityException.query.filter_by(
            is_company_wide=True,
            exception_date=target_date
        ).all()
        
        # If practice is closed company-wide, no one is available
        company_wide_full_block = any(ex.is_all_day and ex.exception_type in ['blocked', 'holiday', 'vacation'] 
                                     for ex in company_wide_blocks)
        
        # Get exceptions for this practitioner
        exceptions = AvailabilityException.query.filter_by(
            user_id=practitioner_id,
            exception_date=target_date
        ).all()
        
        # Check if entire day is blocked (company-wide OR individual)
        full_day_block = company_wide_full_block or any(ex.is_all_day and ex.exception_type in ['blocked', 'holiday', 'vacation'] 
                            for ex in exceptions)
        
        if not full_day_block:
            if not patterns:
                logger.warning(f"No availability patterns found for practitioner {practitioner_id}")
            else:
                # Check each pattern to see if it applies to this date
                for pattern in patterns:
                    # Check if pattern is valid for this date
                    if pattern.valid_from and target_date < pattern.valid_from:
                        continue
                    if pattern.valid_until and target_date > pattern.valid_until:
                        continue
                    
                    # Check if pattern applies to this day of week
                    # Python weekday: Monday=0, Sunday=6
                    day_of_week_num = target_date.weekday()  # 0=Monday, 6=Sunday
                    day_of_week_name = target_date.strftime('%A').lower()
                    applies = False
                    
                    if pattern.frequency == 'daily':
                        applies = True
                    elif pattern.frequency == 'weekdays' and day_of_week_num < 5:  # Mon-Fri (0-4)
                        applies = True
                    elif pattern.frequency == 'weekly':
                        # For weekly, check if this day matches the pattern's day
                        # This would need pattern.day_of_week field, but we use weekdays instead
                        # For now, if weekdays contains this day number, it applies
                        if pattern.weekdays:
                            day_numbers = [int(d.strip()) for d in pattern.weekdays.split(',') if d.strip().isdigit()]
                            applies = day_of_week_num in day_numbers
                    elif pattern.frequency == 'custom':
                        # Custom uses weekdays field with comma-separated day numbers
                        if pattern.weekdays:
                            day_numbers = [int(d.strip()) for d in pattern.weekdays.split(',') if d.strip().isdigit()]
                            applies = day_of_week_num in day_numbers
                    
                    if applies:
                        # Check if exception blocks this time (company-wide + individual)
                        partial_block_times = []
                        # Company-wide partial blocks
                        partial_block_times.extend([(ex.start_time, ex.end_time) 
                                              for ex in company_wide_blocks 
                                              if not ex.is_all_day])
                        # Individual practitioner partial blocks
                        partial_block_times.extend([(ex.start_time, ex.end_time) 
                                              for ex in exceptions 
                                              if not ex.is_all_day])
                        
                        # Generate time slots (every 30 minutes)
                        current_time = pattern.start_time
                        while current_time < pattern.end_time:
                            # Check if this slot is blocked by an exception
                            is_blocked = any(
                                (block_start <= current_time < block_end) 
                                for block_start, block_end in partial_block_times
                            )
                            
                            if not is_blocked:
                                available_slots.append(current_time.strftime('%H:%M'))
                            
                            # Increment by 30 minutes
                            dt = datetime.combine(target_date, current_time)
                            dt += timedelta(minutes=30)
                            current_time = dt.time()
        
        # Get existing appointments for this date
        appointments = Appointment.query.filter(
            Appointment.practitioner_id == practitioner_id,
            db.func.date(Appointment.start_time) == target_date
        ).all()
        
        for appt in appointments:
            booked_slots.append({
                'start': appt.start_time.strftime('%H:%M'),
                'end': appt.end_time.strftime('%H:%M'),
                'title': appt.title
            })
        
        # Log available slots before filtering
        logger.info(f"Generated {len(available_slots)} raw available slots before filtering")
        
        # Filter available slots to only show those with continuous availability for the requested duration
        filtered_slots = []
        for slot in available_slots:
            slot_time = datetime.strptime(slot, '%H:%M').time()
            slot_datetime = datetime.combine(target_date, slot_time)
            end_datetime = slot_datetime + timedelta(minutes=duration_minutes)
            
            # Check if all 30-minute intervals in this duration are available
            has_continuous_availability = True
            check_time = slot_datetime
            
            while check_time < end_datetime:
                check_time_str = check_time.strftime('%H:%M')
                
                # Check if this time is in available slots
                if check_time_str not in available_slots:
                    has_continuous_availability = False
                    break
                
                # Check if this time conflicts with any booked appointment
                for booking in booked_slots:
                    booking_start = datetime.strptime(booking['start'], '%H:%M').time()
                    booking_end = datetime.strptime(booking['end'], '%H:%M').time()
                    check_time_only = check_time.time()
                    
                    if booking_start <= check_time_only < booking_end:
                        has_continuous_availability = False
                        break
                
                if not has_continuous_availability:
                    break
                
                check_time += timedelta(minutes=30)
            
            if has_continuous_availability:
                filtered_slots.append(slot)
        
        logger.info(f"Returning {len(filtered_slots)} filtered available slots")
        
        return jsonify({
            'success': True,
            'date': date_str,
            'practitioner': practitioner.full_name,
            'available_slots': filtered_slots,
            'booked_slots': booked_slots,
            'is_blocked': full_day_block,
            'duration_minutes': duration_minutes,
            'has_patterns': len(patterns) > 0
        })
    except Exception as e:
        logger.error(f"Error getting availability: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@appointments_bp.route('/my-availability')
@login_required
def my_availability():
    """Practitioner's own availability management page (admins can manage any practitioner)"""
    # Check if admin is managing another practitioner's availability
    manage_user_id = request.args.get('user_id', type=int)
    
    # Admins can manage any practitioner, non-admins can only manage their own
    if manage_user_id and manage_user_id != current_user.id:
        if not current_user.is_admin:
            flash('You do not have permission to manage other practitioners\' availability', 'error')
            return redirect(url_for('appointments.my_availability'))
        target_user = User.query.get_or_404(manage_user_id)
    else:
        target_user = current_user
        manage_user_id = current_user.id
    
    patterns = AvailabilityPattern.query.filter_by(
        user_id=manage_user_id, 
        is_company_wide=False
    ).order_by(AvailabilityPattern.valid_from.desc()).all()
    
    exceptions = AvailabilityException.query.filter_by(
        user_id=manage_user_id,
        is_company_wide=False
    ).order_by(AvailabilityException.exception_date.desc()).all()
    
    # Get all practitioners for admin dropdown
    all_practitioners = []
    if current_user.is_admin:
        all_practitioners = User.query.filter_by(is_active=True).order_by(User.first_name, User.last_name).all()
    
    return render_template('my_availability_v2.html', 
                         patterns=patterns, 
                         exceptions=exceptions,
                         target_user=target_user,
                         all_practitioners=all_practitioners,
                         is_admin=current_user.is_admin)

@appointments_bp.route('/api/my-availability', methods=['GET'])
@login_required
def get_my_availability():
    """Get user's availability patterns and exceptions (admins can view any practitioner)"""
    try:
        # Check if admin is viewing another practitioner's availability
        manage_user_id = request.args.get('user_id', type=int, default=current_user.id)
        
        # Admins can view any practitioner, non-admins can only view their own
        if manage_user_id != current_user.id and not current_user.is_admin:
            return jsonify({'success': False, 'error': 'Permission denied'}), 403
        
        # Get UserAvailability records (simple day_of_week format)
        user_availability = UserAvailability.query.filter_by(user_id=manage_user_id).all()
        availability_list = []
        for avail in user_availability:
            availability_list.append({
                'id': avail.id,
                'day_of_week': avail.day_of_week,
                'start_time': avail.start_time.strftime('%H:%M') if avail.start_time else None,
                'end_time': avail.end_time.strftime('%H:%M') if avail.end_time else None,
                'specific_date': avail.specific_date.isoformat() if avail.specific_date else None,
                'is_available': avail.is_available,
                'notes': avail.notes
            })
        
        patterns = AvailabilityPattern.query.filter_by(user_id=manage_user_id, is_company_wide=False).all()
        exceptions = AvailabilityException.query.filter_by(user_id=manage_user_id, is_company_wide=False).all()
        
        pattern_list = []
        for pattern in patterns:
            pattern_list.append({
                'id': pattern.id,
                'title': pattern.title,
                'frequency': pattern.frequency,
                'weekdays': pattern.weekdays if pattern.weekdays else '',  # Return as string for frontend .split()
                'start_time': pattern.start_time.strftime('%H:%M'),
                'end_time': pattern.end_time.strftime('%H:%M'),
                'valid_from': pattern.valid_from.isoformat() if pattern.valid_from else None,
                'valid_until': pattern.valid_until.isoformat() if pattern.valid_until else None,
                'is_active': pattern.is_active,
                'color': pattern.color
            })
        
        exception_list = []
        for exception in exceptions:
            exception_list.append({
                'id': exception.id,
                'exception_date': exception.exception_date.isoformat(),
                'exception_type': exception.exception_type,
                'is_all_day': exception.is_all_day,
                'start_time': exception.start_time.strftime('%H:%M') if exception.start_time else None,
                'end_time': exception.end_time.strftime('%H:%M') if exception.end_time else None,
                'reason': exception.reason
            })
        
        return jsonify({
            'success': True, 
            'availability': availability_list,  # For simple day_of_week format
            'patterns': pattern_list, 
            'exceptions': exception_list
        })
    except Exception as e:
        logger.error(f"Error fetching user availability: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@appointments_bp.route('/api/my-availability', methods=['POST'])
@login_required
def add_my_availability():
    """Add a new availability pattern or exception (admins can add for any practitioner)"""
    try:
        data = request.get_json()
        item_type = data.get('type') # 'pattern' or 'exception'
        
        # Check if admin is managing another practitioner's availability
        manage_user_id = data.get('user_id', current_user.id)
        
        # Admins can manage any practitioner, non-admins can only manage their own
        if manage_user_id != current_user.id and not current_user.is_admin:
            return jsonify({'success': False, 'error': 'Permission denied'}), 403
        
        # Handle simple UserAvailability format (day_of_week, start_time, end_time)
        if 'day_of_week' in data and data.get('day_of_week') is not None:
            new_availability = UserAvailability(
                user_id=manage_user_id,
                day_of_week=int(data.get('day_of_week')),
                start_time=datetime.strptime(data.get('start_time'), '%H:%M').time(),
                end_time=datetime.strptime(data.get('end_time'), '%H:%M').time(),
                specific_date=datetime.strptime(data.get('specific_date'), '%Y-%m-%d').date() if data.get('specific_date') else None,
                is_available=data.get('is_available', True),
                notes=data.get('notes')
            )
            db.session.add(new_availability)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Availability block added', 'id': new_availability.id}), 201
        
        elif item_type == 'pattern':
            new_pattern = AvailabilityPattern(
                user_id=manage_user_id,
                is_company_wide=False,
                title=data.get('title'),
                frequency=data.get('frequency'),
                weekdays=','.join(map(str, data.get('weekdays', []))),
                start_time=datetime.strptime(data.get('start_time'), '%H:%M').time(),
                end_time=datetime.strptime(data.get('end_time'), '%H:%M').time(),
                valid_from=datetime.strptime(data.get('valid_from'), '%Y-%m-%d').date() if data.get('valid_from') else None,
                valid_until=datetime.strptime(data.get('valid_until'), '%Y-%m-%d').date() if data.get('valid_until') else None,
                is_active=data.get('is_active', True),
                color=data.get('color')
            )
            db.session.add(new_pattern)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Availability pattern added', 'id': new_pattern.id}), 201
        
        elif item_type == 'exception':
            new_exception = AvailabilityException(
                user_id=manage_user_id,
                is_company_wide=False,
                exception_date=datetime.strptime(data.get('exception_date'), '%Y-%m-%d').date(),
                exception_type=data.get('exception_type'),
                is_all_day=data.get('is_all_day', False),
                start_time=datetime.strptime(data.get('start_time'), '%H:%M').time() if data.get('start_time') else None,
                end_time=datetime.strptime(data.get('end_time'), '%H:%M').time() if data.get('end_time') else None,
                reason=data.get('reason')
            )
            db.session.add(new_exception)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Availability exception added', 'id': new_exception.id}), 201
        
        return jsonify({'success': False, 'error': 'Invalid item type or missing required fields'}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding availability: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@appointments_bp.route('/api/my-availability/<int:slot_id>', methods=['DELETE'])
@login_required
def delete_my_availability(slot_id):
    """Delete an availability pattern or exception for the current user"""
    try:
        # Try to delete as UserAvailability (simple format)
        user_availability = UserAvailability.query.filter_by(id=slot_id, user_id=current_user.id).first()
        if user_availability:
            db.session.delete(user_availability)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Availability block deleted'})
        
        # Try to delete as pattern
        pattern = AvailabilityPattern.query.filter_by(id=slot_id, user_id=current_user.id).first()
        if pattern:
            db.session.delete(pattern)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Availability pattern deleted'})
        
        # Try to delete as exception
        exception = AvailabilityException.query.filter_by(id=slot_id, user_id=current_user.id).first()
        if exception:
            db.session.delete(exception)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Availability exception deleted'})
        
        return jsonify({'success': False, 'error': 'Availability item not found or not authorized'}), 404
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting availability item: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@appointments_bp.route('/api/availability-patterns', methods=['GET', 'POST'])
@login_required
def manage_availability_patterns():
    if request.method == 'GET':
        try:
            # Check if admin is viewing another user's patterns
            manage_user_id = request.args.get('user_id', type=int, default=current_user.id)
            
            # Admins can view any user, non-admins only their own
            if manage_user_id != current_user.id and not current_user.is_admin:
                manage_user_id = current_user.id
            
            # Get user-specific patterns
            user_patterns = AvailabilityPattern.query.filter_by(
                user_id=manage_user_id,
                is_company_wide=False
            ).all()
            
            # Get company-wide patterns (office hours) - visible to all
            company_patterns = AvailabilityPattern.query.filter_by(
                is_company_wide=True,
                is_active=True
            ).all()
            
            pattern_list = []
            
            # Add user-specific patterns
            for pattern in user_patterns:
                pattern_list.append({
                    'id': pattern.id,
                    'title': pattern.title,
                    'frequency': pattern.frequency,
                    'weekdays': pattern.weekdays if pattern.weekdays else '',
                    'start_time': pattern.start_time.strftime('%H:%M'),
                    'end_time': pattern.end_time.strftime('%H:%M'),
                    'valid_from': pattern.valid_from.isoformat() if pattern.valid_from else None,
                    'valid_until': pattern.valid_until.isoformat() if pattern.valid_until else None,
                    'is_active': pattern.is_active,
                    'is_company_wide': False,
                    'color': pattern.color
                })
            
            # Add company-wide patterns (office hours)
            for pattern in company_patterns:
                pattern_list.append({
                    'id': pattern.id,
                    'title': pattern.title + ' (Office Hours)',
                    'frequency': pattern.frequency,
                    'weekdays': pattern.weekdays if pattern.weekdays else '',
                    'start_time': pattern.start_time.strftime('%H:%M'),
                    'end_time': pattern.end_time.strftime('%H:%M'),
                    'valid_from': pattern.valid_from.isoformat() if pattern.valid_from else None,
                    'valid_until': pattern.valid_until.isoformat() if pattern.valid_until else None,
                    'is_active': pattern.is_active,
                    'is_company_wide': True,
                    'color': '#10b981'  # Green for office hours
                })
            
            return jsonify({'success': True, 'patterns': pattern_list})
        except Exception as e:
            logger.error(f"Error fetching availability patterns: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
    
    elif request.method == 'POST':
        try:
            data = request.get_json()
            # Handle weekdays - can be string (comma-separated) or array
            weekdays_data = data.get('weekdays', [])
            if isinstance(weekdays_data, str):
                weekdays_str = weekdays_data  # Already a string like '0,1,2,3,4'
            elif isinstance(weekdays_data, list):
                weekdays_str = ','.join(map(str, weekdays_data))
            else:
                weekdays_str = ''
            
            new_pattern = AvailabilityPattern(
                user_id=current_user.id,
                title=data.get('title'),
                frequency=data.get('frequency'),
                weekdays=weekdays_str,
                start_time=datetime.strptime(data.get('start_time'), '%H:%M').time(),
                end_time=datetime.strptime(data.get('end_time'), '%H:%M').time(),
                valid_from=datetime.strptime(data.get('valid_from'), '%Y-%m-%d').date() if data.get('valid_from') else None,
                valid_until=datetime.strptime(data.get('valid_until'), '%Y-%m-%d').date() if data.get('valid_until') else None,
                is_active=data.get('is_active', True),
                color=data.get('color')
            )
            db.session.add(new_pattern)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Availability pattern added', 'id': new_pattern.id}), 201
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error adding availability pattern: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

@appointments_bp.route('/api/availability-patterns/<int:pattern_id>', methods=['PUT', 'DELETE'])
@login_required
def update_delete_availability_pattern(pattern_id):
    pattern = AvailabilityPattern.query.filter_by(id=pattern_id, user_id=current_user.id).first_or_404()
    
    if request.method == 'PUT':
        try:
            data = request.get_json()
            # Handle weekdays - can be string (comma-separated) or array
            if 'weekdays' in data:
                weekdays_data = data.get('weekdays')
                if isinstance(weekdays_data, str):
                    pattern.weekdays = weekdays_data  # Already a string
                elif isinstance(weekdays_data, list):
                    pattern.weekdays = ','.join(map(str, weekdays_data))
                else:
                    pattern.weekdays = ''
            else:
                # Keep existing weekdays if not provided
                pattern.weekdays = pattern.weekdays
            
            pattern.title = data.get('title', pattern.title)
            pattern.frequency = data.get('frequency', pattern.frequency)
            pattern.start_time = datetime.strptime(data.get('start_time'), '%H:%M').time() if data.get('start_time') else pattern.start_time
            pattern.end_time = datetime.strptime(data.get('end_time'), '%H:%M').time() if data.get('end_time') else pattern.end_time
            pattern.valid_from = datetime.strptime(data.get('valid_from'), '%Y-%m-%d').date() if data.get('valid_from') else pattern.valid_from
            pattern.valid_until = datetime.strptime(data.get('valid_until'), '%Y-%m-%d').date() if data.get('valid_until') else pattern.valid_until
            pattern.is_active = data.get('is_active', pattern.is_active)
            pattern.color = data.get('color', pattern.color)
            
            db.session.commit()
            return jsonify({'success': True, 'message': 'Availability pattern updated'})
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating availability pattern: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
    
    elif request.method == 'DELETE':
        try:
            db.session.delete(pattern)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Availability pattern deleted'})
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting availability pattern: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

@appointments_bp.route('/api/availability-exceptions', methods=['GET', 'POST'])
@login_required
def manage_availability_exceptions():
    if request.method == 'GET':
        try:
            # Check if admin is viewing another user's exceptions
            manage_user_id = request.args.get('user_id', type=int, default=current_user.id)
            
            # Admins can view any user, non-admins only their own
            if manage_user_id != current_user.id and not current_user.is_admin:
                manage_user_id = current_user.id
            
            # Get user-specific exceptions
            user_exceptions = AvailabilityException.query.filter_by(
                user_id=manage_user_id,
                is_company_wide=False
            ).all()
            
            # Get company-wide exceptions (holidays) - visible to all
            company_exceptions = AvailabilityException.query.filter_by(
                is_company_wide=True
            ).all()
            
            exception_list = []
            
            # Add user-specific exceptions
            for exception in user_exceptions:
                exception_list.append({
                    'id': exception.id,
                    'exception_date': exception.exception_date.isoformat(),
                    'exception_type': exception.exception_type,
                    'is_all_day': exception.is_all_day,
                    'start_time': exception.start_time.strftime('%H:%M') if exception.start_time else None,
                    'end_time': exception.end_time.strftime('%H:%M') if exception.end_time else None,
                    'reason': exception.reason,
                    'is_company_wide': False
                })
            
            # Add company-wide exceptions (holidays/closures)
            for exception in company_exceptions:
                exception_list.append({
                    'id': exception.id,
                    'exception_date': exception.exception_date.isoformat(),
                    'exception_type': exception.exception_type,
                    'is_all_day': exception.is_all_day,
                    'start_time': exception.start_time.strftime('%H:%M') if exception.start_time else None,
                    'end_time': exception.end_time.strftime('%H:%M') if exception.end_time else None,
                    'reason': (exception.reason or 'Company Holiday') + ' (Company-Wide)',
                    'is_company_wide': True
                })
            
            return jsonify({'success': True, 'exceptions': exception_list})
        except Exception as e:
            logger.error(f"Error fetching availability exceptions: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
    
    elif request.method == 'POST':
        try:
            data = request.get_json()
            is_range = data.get('is_range', False)
            exceptions_created = []
            
            if is_range:
                # Handle date range - create exception for each date
                from_date = datetime.strptime(data.get('from_date'), '%Y-%m-%d').date()
                to_date = datetime.strptime(data.get('to_date'), '%Y-%m-%d').date()
                
                current_date = from_date
                while current_date <= to_date:
                    # Check if exception already exists for this date and user
                    existing = AvailabilityException.query.filter_by(
                        user_id=current_user.id,
                        exception_date=current_date
                    ).first()
                    
                    if not existing:
                        new_exception = AvailabilityException(
                            user_id=current_user.id,
                            exception_date=current_date,
                            exception_type=data.get('exception_type', 'blocked'),
                            is_all_day=data.get('is_all_day', True),
                            start_time=datetime.strptime(data.get('start_time'), '%H:%M').time() if data.get('start_time') else None,
                            end_time=datetime.strptime(data.get('end_time'), '%H:%M').time() if data.get('end_time') else None,
                            reason=data.get('reason')
                        )
                        db.session.add(new_exception)
                        exceptions_created.append(new_exception)
                    
                    current_date += timedelta(days=1)
            else:
                # Handle single date
                exception_date = datetime.strptime(data.get('exception_date'), '%Y-%m-%d').date()
                
                # Check if exception already exists
                existing = AvailabilityException.query.filter_by(
                    user_id=current_user.id,
                    exception_date=exception_date
                ).first()
                
                if existing:
                    return jsonify({'success': False, 'error': 'An exception already exists for this date'}), 400
                
                new_exception = AvailabilityException(
                    user_id=current_user.id,
                    exception_date=exception_date,
                    exception_type=data.get('exception_type', 'blocked'),
                    is_all_day=data.get('is_all_day', False),
                    start_time=datetime.strptime(data.get('start_time'), '%H:%M').time() if data.get('start_time') else None,
                    end_time=datetime.strptime(data.get('end_time'), '%H:%M').time() if data.get('end_time') else None,
                    reason=data.get('reason')
                )
                db.session.add(new_exception)
                exceptions_created.append(new_exception)
            
            db.session.commit()
            
            count = len(exceptions_created)
            message = f'{count} date{"s" if count > 1 else ""} blocked successfully' if count > 0 else 'All dates were already blocked'
            
            return jsonify({
                'success': True, 
                'message': message, 
                'count': count,
                'ids': [ex.id for ex in exceptions_created]
            }), 201
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error adding availability exception: {e}", exc_info=True)
            # Handle duplicate key error specifically
            if 'duplicate key' in str(e).lower() or 'unique constraint' in str(e).lower():
                return jsonify({'success': False, 'error': 'One or more dates are already blocked. Please refresh and try again.'}), 400
            return jsonify({'success': False, 'error': str(e)}), 500

@appointments_bp.route('/api/availability-exceptions/<int:exception_id>', methods=['DELETE'])
@login_required
def delete_availability_exception(exception_id):
    exception = AvailabilityException.query.filter_by(id=exception_id, user_id=current_user.id).first_or_404()
    try:
        db.session.delete(exception)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Availability exception deleted'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting availability exception: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@appointments_bp.route('/api/calendar/cache/refresh', methods=['POST'])
@login_required
def refresh_appointment_cache():
    """Manually refresh the appointment cache table"""
    try:
        from sqlalchemy import text
        from datetime import date, timedelta
        
        start_date = request.json.get('start_date') if request.json else None
        end_date = request.json.get('end_date') if request.json else None
        
        if not start_date or not end_date:
            # Default to current month + 3 months ahead
            start_date = (date.today() - timedelta(days=30)).isoformat()
            end_date = (date.today() + timedelta(days=90)).isoformat()
        
        # Check if function exists first
        func_exists = db.session.execute(text("""
            SELECT EXISTS (
                SELECT FROM pg_proc 
                WHERE proname = 'refresh_appointment_cache'
            )
        """)).scalar()
        
        if not func_exists:
            # Try to setup cache first
            setup_result = setup_calendar_cache()
            if not setup_result[0].get_json().get('success'):
                return setup_result
        
        result = db.session.execute(text("""
            SELECT refresh_appointment_cache(:start_date::date, :end_date::date)
        """), {
            'start_date': start_date,
            'end_date': end_date
        })
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Cache refreshed for {start_date} to {end_date}'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error refreshing cache: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@appointments_bp.route('/api/appointments/<int:appointment_id>', methods=['GET'])
@login_required
def get_appointment(appointment_id):
    """Get a single appointment by ID for calendar drawer"""
    try:
        appointment = Appointment.query.get_or_404(appointment_id)
        return jsonify({
            'success': True,
            'appointment': {
                'id': appointment.id,
                'patient_id': appointment.patient_id,
                'patient_name': f"{appointment.patient.first_name} {appointment.patient.last_name}",
                'practitioner_id': appointment.practitioner_id,
                'practitioner_name': appointment.assigned_practitioner.full_name if appointment.assigned_practitioner else 'Unassigned',
                'start_time': appointment.start_time.strftime('%I:%M %p') if appointment.start_time else '',
                'end_time': appointment.end_time.strftime('%I:%M %p') if appointment.end_time else '',
                'appointment_type': appointment.appointment_type,
                'duration': f"{appointment.duration_minutes} min",
                'location': appointment.location,
                'notes': appointment.notes,
                'status': appointment.status
            }
        })
    except Exception as e:
        logger.error(f"Error fetching appointment {appointment_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@appointments_bp.route('/api/calendar/check-conflict', methods=['GET'])
@login_required
def check_appointment_conflict():
    """Check if moving an appointment causes a conflict"""
    try:
        appointment_id = request.args.get('appointment_id', type=int)
        date_str = request.args.get('date')
        time_str = request.args.get('time')
        
        if not appointment_id or not date_str or not time_str:
            return jsonify({'conflict': False, 'message': 'Invalid parameters'}), 400
            
        # Parse new start time
        try:
            new_start = datetime.strptime(f"{date_str} {time_str}", '%Y-%m-%d %H:%M')
        except ValueError:
            # Try ISO format if simple format fails or fallback
            try:
                new_start = datetime.fromisoformat(f"{date_str}T{time_str}")
            except ValueError:
                return jsonify({'conflict': False, 'message': 'Invalid date/time format'}), 400
            
        # Get existing appointment to get duration and practitioner
        appointment = Appointment.query.get(appointment_id)
        if not appointment:
            return jsonify({'conflict': False, 'message': 'Appointment not found'}), 404
            
        duration = appointment.duration_minutes
        new_end = new_start + timedelta(minutes=duration)
        practitioner_id = appointment.practitioner_id
        
        # Check for overlaps with OTHER appointments for same practitioner
        if practitioner_id:
            conflicting_appointments = Appointment.query.filter(
                Appointment.practitioner_id == practitioner_id,
                Appointment.id != appointment_id, # Exclude self
                Appointment.status != 'cancelled',
                db.or_(
                    # New appointment starts during existing appointment
                    db.and_(
                        Appointment.start_time <= new_start,
                        Appointment.end_time > new_start
                    ),
                    # New appointment ends during existing appointment
                    db.and_(
                        Appointment.start_time < new_end,
                        Appointment.end_time >= new_end
                    ),
                    # New appointment completely contains existing appointment
                    db.and_(
                        Appointment.start_time >= new_start,
                        Appointment.end_time <= new_end
                    )
                )
            ).all()
            
            if conflicting_appointments:
                practitioner_name = appointment.assigned_practitioner.full_name if appointment.assigned_practitioner else 'Practitioner'
                conflict_msg = f"This time overlaps with another appointment for {practitioner_name}."
                # Specific details could be added
                return jsonify({
                    'conflict': True, 
                    'message': conflict_msg,
                    'details': [f"{apt.title} ({apt.start_time.strftime('%H:%M')}-{apt.end_time.strftime('%H:%M')})" for apt in conflicting_appointments]
                })
                
        return jsonify({'conflict': False, 'message': 'No conflict'})
        
    except Exception as e:
        logger.error(f"Error checking conflict: {e}")
        return jsonify({'conflict': False, 'message': str(e)}), 500

@appointments_bp.route('/api/calendar/appointments/<int:appointment_id>', methods=['DELETE'])
@login_required
def delete_calendar_appointment(appointment_id):
    """Delete appointment from calendar"""
    try:
        appointment = Appointment.query.get_or_404(appointment_id)
        
        # Delete from Google Calendar
        calendar_sync = get_calendar_sync()
        if calendar_sync and appointment.google_calendar_event_id:
            try:
                calendar_sync.delete_event(appointment.google_calendar_event_id)
            except Exception as e:
                logger.warning(f"Google Calendar delete failed: {e}")
        
        db.session.delete(appointment)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting appointment: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@appointments_bp.route('/patients/<int:patient_id>/appointments', methods=['GET'])
@login_required
def get_patient_appointments(patient_id):
    """Get all appointments for a specific patient"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        appointments = Appointment.query.filter_by(patient_id=patient_id).filter(
            Appointment.status != 'cancelled'
        ).order_by(Appointment.start_time.desc()).all()
        
        appointment_list = []
        for apt in appointments:
            appointment_list.append({
                'id': apt.id,
                'title': apt.title,
                'start_time': apt.start_time.isoformat() if apt.start_time else None,
                'end_time': apt.end_time.isoformat() if apt.end_time else None,
                'status': apt.status,
                'type': apt.appointment_type,
                'practitioner_name': apt.assigned_practitioner.full_name if apt.assigned_practitioner else 'Unassigned',
                'notes': apt.notes
            })
        
        return jsonify({'success': True, 'appointments': appointment_list})
    except Exception as e:
        logger.error(f"Error fetching patient appointments: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        try:
            db.session.remove()
        except:
            pass

@appointments_bp.route('/patients/<int:patient_id>/appointments', methods=['POST'])
@login_required
def add_patient_appointment(patient_id):
    """Add a new appointment for a specific patient"""
    try:
        data = request.get_json()
        
        # Parse start_time
        start_time = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
        if start_time.tzinfo:
            start_time = start_time.replace(tzinfo=None)
        
        # VALIDATION: Only allow future appointments
        now = datetime.now()
        if start_time < now:
            return jsonify({
                'success': False,
                'error': 'Cannot book appointments in the past. Please select a future date and time.'
            }), 400
        
        # Calculate end_time from start_time + duration
        duration_minutes = int(data.get('duration_minutes', 60))
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        new_appointment = Appointment(
            patient_id=patient_id,
            practitioner_id=data.get('practitioner_id'),
            title=data.get('title'),
            appointment_type=data.get('appointment_type', 'Consultation'),
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration_minutes,
            location=data.get('location'),
            notes=data.get('notes'),
            status=data.get('status', 'scheduled'),
            created_by_id=current_user.id
        )
        
        db.session.add(new_appointment)
        db.session.commit()
        
        # Sync to Google Calendar if configured
        calendar_sync = get_calendar_sync()
        patient = Patient.query.get(patient_id)
        if calendar_sync and new_appointment.practitioner_id:
            try:
                practitioner = User.query.get(new_appointment.practitioner_id)
                
                description = f"Patient: {patient.first_name} {patient.last_name}\nType: {new_appointment.appointment_type}\nNotes: {new_appointment.notes or 'None'}"
                
                event_id = calendar_sync.create_event(
                    summary=f"{new_appointment.title} - {patient.first_name} {patient.last_name}",
                    start_time=new_appointment.start_time,
                    end_time=new_appointment.end_time,
                    description=description,
                    attendee_email=patient.email
                )
                
                if event_id:
                    new_appointment.google_calendar_event_id = event_id
                    db.session.commit()
                    logger.info(f"Synced appointment {new_appointment.id} to Google Calendar: {event_id}")
            except Exception as e:
                logger.error(f"Failed to sync to Google Calendar: {e}")
        
        # Send SMS notification to patient
        notification_result = {'sms': False, 'email': False}
        if patient:
            try:
                from notification_service import NotificationService
                notification_service = NotificationService()
                
                # Prepare template variables
                start_time_formatted = new_appointment.start_time.strftime('%d/%m/%Y at %I:%M %p')
                practitioner_name = User.query.get(new_appointment.practitioner_id).full_name if new_appointment.practitioner_id else 'Your practitioner'
                
                # Send SMS if mobile or phone available
                if patient.mobile or patient.phone:
                    try:
                        # Get custom SMS template if exists
                        from models import NotificationTemplate
                        sms_template = NotificationTemplate.query.filter_by(
                            template_type='sms',
                            template_name='appointment_confirmation',
                            is_active=True
                        ).first()
                        
                        if sms_template and sms_template.message:
                            # Substitute template variables
                            sms_message = sms_template.message.format(
                                patient_name=patient.first_name,
                                first_name=patient.first_name,
                                last_name=patient.last_name,
                                date=new_appointment.start_time.strftime('%d/%m/%Y'),
                                time=new_appointment.start_time.strftime('%I:%M %p'),
                                date_time=start_time_formatted,
                                date_time_short=start_time_formatted,
                                practitioner=practitioner_name,
                                location=new_appointment.location or 'TBD',
                                appointment_type=new_appointment.appointment_type or 'Appointment',
                                duration=f"{new_appointment.duration_minutes} minutes"
                            )
                        else:
                            # Default SMS message
                            sms_message = f"Hi {patient.first_name}, your appointment has been confirmed for {start_time_formatted}. Location: {new_appointment.location or 'TBD'}. See you soon!"
                        
                        # Send SMS and log to correspondence
                        sms_result = notification_service.send_sms(
                            to_phone=patient.mobile or patient.phone,
                            message=sms_message,
                            patient_id=patient.id,
                            user_id=current_user.id,
                            log_correspondence=True
                        )
                        
                        if sms_result.get('success'):
                            notification_result['sms'] = True
                            logger.info(f"✅ Sent appointment confirmation SMS for appointment {new_appointment.id}")
                        else:
                            logger.warning(f"Failed to send SMS for appointment {new_appointment.id}: {sms_result.get('error')}")
                    except Exception as sms_error:
                        logger.error(f"Error sending SMS for appointment {new_appointment.id}: {sms_error}")
                else:
                    logger.info(f"No phone number available for patient {patient.id}, skipping SMS")
                    
            except Exception as notif_error:
                logger.error(f"Error sending appointment notification: {notif_error}")
                # Don't fail the appointment creation if notification fails
        
        return jsonify({
            'success': True, 
            'appointment': new_appointment.to_dict(),
            'notification_sent': notification_result
        }), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding patient appointment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@appointments_bp.route('/patients/<int:patient_id>/appointments/<int:appointment_id>', methods=['PUT'])
@login_required
def update_patient_appointment(patient_id, appointment_id):
    """Update an existing appointment for a specific patient"""
    try:
        appointment = Appointment.query.filter_by(id=appointment_id, patient_id=patient_id).first_or_404()
        data = request.get_json()
        
        if 'start_time' in data:
            start_time = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
            if start_time.tzinfo:
                start_time = start_time.replace(tzinfo=None)
            appointment.start_time = start_time
        if 'end_time' in data:
            end_time = datetime.fromisoformat(data['end_time'].replace('Z', '+00:00'))
            if end_time.tzinfo:
                end_time = end_time.replace(tzinfo=None)
            appointment.end_time = end_time
        
        if appointment.start_time and appointment.end_time:
            appointment.duration_minutes = int((appointment.end_time - appointment.start_time).total_seconds() / 60)
        
        appointment.practitioner_id = data.get('practitioner_id', appointment.practitioner_id)
        appointment.title = data.get('title', appointment.title)
        appointment.appointment_type = data.get('appointment_type', appointment.appointment_type)
        appointment.location = data.get('location', appointment.location)
        appointment.notes = data.get('notes', appointment.notes)
        appointment.status = data.get('status', appointment.status)
        
        db.session.commit()
        
        # Sync to Google Calendar if configured
        calendar_sync = get_calendar_sync()
        if calendar_sync and appointment.google_calendar_event_id:
            try:
                patient = appointment.patient
                description = f"Patient: {patient.first_name} {patient.last_name}\nType: {appointment.appointment_type}\nNotes: {appointment.notes or 'None'}"
                
                calendar_sync.update_event(
                    event_id=appointment.google_calendar_event_id,
                    summary=f"{appointment.title} - {patient.first_name} {patient.last_name}",
                    start_time=appointment.start_time,
                    end_time=appointment.end_time,
                    description=description,
                    attendee_email=patient.email
                )
            except Exception as e:
                logger.error(f"Failed to update Google Calendar: {e}")
        
        return jsonify({'success': True, 'appointment': appointment.to_dict()})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating patient appointment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@appointments_bp.route('/patients/<int:patient_id>/appointments/<int:appointment_id>', methods=['DELETE'])
@login_required
def delete_patient_appointment(patient_id, appointment_id):
    """Delete an appointment for a specific patient"""
    try:
        appointment = Appointment.query.filter_by(id=appointment_id, patient_id=patient_id).first_or_404()
        
        # Delete from Google Calendar
        calendar_sync = get_calendar_sync()
        if calendar_sync and appointment.google_calendar_event_id:
            try:
                calendar_sync.delete_event(appointment.google_calendar_event_id)
            except Exception as e:
                logger.warning(f"Google Calendar delete failed: {e}")
        
        db.session.delete(appointment)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Appointment deleted successfully'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting patient appointment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@appointments_bp.route('/patients/<int:patient_id>/sync-info', methods=['GET'])
@login_required
def get_patient_sync_info(patient_id):
    """Get patient sync information (Withings, Cliniko)"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        
        withings_configured = bool(current_app.config.get('WITHINGS_CLIENT_ID') and current_app.config.get('WITHINGS_CLIENT_SECRET'))
        cliniko_configured = bool(current_app.config.get('CLINIKO_API_KEY'))
        
        withings_status = {
            'is_connected': False,
            'last_sync': None,
            'auth_url': None,
            'last_record': None
        }
        
        if withings_configured:
            # Check if patient has valid Withings token
            has_valid_token = (
                patient.withings_access_token and 
                patient.withings_token_expiry and 
                patient.withings_token_expiry > datetime.utcnow()
            )
            
            if has_valid_token:
                withings_status['is_connected'] = True
                
                # Get last sync from patient's last_synced_at or from last HealthData record
                if patient.last_synced_at:
                    withings_status['last_sync'] = patient.last_synced_at.isoformat()
                
                # Get last health data record timestamp
                last_record = HealthData.query.filter_by(patient_id=patient_id).order_by(HealthData.timestamp.desc()).first()
                if last_record:
                    withings_status['last_record'] = {
                        'timestamp': last_record.timestamp.isoformat(),
                        'measurement_type': last_record.measurement_type,
                        'value': float(last_record.value) if last_record.value else None
                    }
            else:
                # Generate new auth URL
                # CRITICAL: Force production redirect URI - must be HTTPS
                production_redirect_uri = 'https://capturecare-310697189983.australia-southeast2.run.app/withings/callback'
                redirect_uri = current_app.config.get('WITHINGS_REDIRECT_URI', production_redirect_uri)
                if 'localhost' in redirect_uri or not redirect_uri.startswith('https://'):
                    redirect_uri = production_redirect_uri
                
                try:
                    auth_manager = WithingsAuthManager(
                        client_id=current_app.config['WITHINGS_CLIENT_ID'],
                        client_secret=current_app.config['WITHINGS_CLIENT_SECRET'],
                        redirect_uri=redirect_uri
                    )
                    withings_status['auth_url'] = auth_manager.get_authorization_url(patient_id)
                except Exception as e:
                    logger.error(f"Error generating Withings auth URL: {e}", exc_info=True)
                    withings_status['auth_url'] = None
        
        cliniko_status = {
            'is_connected': bool(patient.cliniko_patient_id),
            'last_sync': patient.cliniko_last_sync_at.isoformat() if patient.cliniko_last_sync_at else None
        }
        
        return jsonify({
            'success': True,
            'withings': withings_status,
            'cliniko': cliniko_status
        })
    except Exception as e:
        logger.error(f"Error fetching sync info for patient {patient_id}: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.session.remove()

@appointments_bp.route('/patients/<int:patient_id>/sync', methods=['POST'])
@login_required
def sync_patient_data(patient_id):
    """Manually trigger data sync for a patient (Withings, Cliniko)"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        
        # Handle both JSON and FormData
        if request.is_json:
            data = request.json or {}
            sync_type = data.get('sync_type', 'withings')
            full_sync = data.get('full_sync', False)
            send_email = data.get('send_email', False)
        else:
            # Handle FormData
            sync_type = request.form.get('sync_type', 'withings')
            full_sync = request.form.get('full_sync', 'false').lower() == 'true'
            send_email = request.form.get('send_email', 'false').lower() == 'true'
        
        if sync_type == 'withings':
            try:
                # Initialize synchronizer with config dict
                config_dict = {
                    'WITHINGS_CLIENT_ID': current_app.config.get('WITHINGS_CLIENT_ID', ''),
                    'WITHINGS_CLIENT_SECRET': current_app.config.get('WITHINGS_CLIENT_SECRET', ''),
                    'WITHINGS_REDIRECT_URI': current_app.config.get('WITHINGS_REDIRECT_URI', ''),
                    'GOOGLE_SHEETS_CREDENTIALS': current_app.config.get('GOOGLE_SHEETS_CREDENTIALS', ''),
                    'GOOGLE_SHEET_ID': current_app.config.get('GOOGLE_SHEET_ID', ''),
                    'OPENAI_API_KEY': current_app.config.get('OPENAI_API_KEY', ''),
                    'SMTP_SERVER': current_app.config.get('SMTP_SERVER', ''),
                    'SMTP_PORT': current_app.config.get('SMTP_PORT', 587),
                    'SMTP_USERNAME': current_app.config.get('SMTP_USERNAME', ''),
                    'SMTP_PASSWORD': current_app.config.get('SMTP_PASSWORD', ''),
                    'SMTP_FROM_EMAIL': current_app.config.get('SMTP_FROM_EMAIL', '')
                }
                synchronizer = HealthDataSynchronizer(config_dict)
                
                # Determine sync range
                startdate = None
                if not full_sync:
                    # Get last sync date
                    last_record = HealthData.query.filter_by(patient_id=patient_id).order_by(HealthData.timestamp.desc()).first()
                    if last_record:
                        # Start 1 day before last record
                        startdate = last_record.timestamp - timedelta(days=1)
                
                # Sync patient data
                result = synchronizer.sync_patient_data(
                    patient_id=patient_id,
                    days_back=365 if full_sync else 7,
                    startdate=startdate,
                    send_email=send_email
                )
                
                if result.get('success'):
                    patient.last_synced_at = datetime.utcnow()
                    db.session.commit()
                    return jsonify({
                        'success': True,
                        'message': result.get('message', 'Withings data synced successfully'),
                        'measurements': result.get('measurements', 0),
                        'activities': result.get('activities', 0),
                        'sleep': result.get('sleep', 0),
                        'devices': result.get('devices', 0),
                        'total': result.get('measurements', 0) + result.get('activities', 0) + result.get('sleep', 0)
                    })
                else:
                    db.session.rollback()
                    return jsonify({'success': False, 'error': result.get('error', 'Sync failed')}), 500
                    
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error syncing Withings data for patient {patient_id}: {e}", exc_info=True)
                return jsonify({'success': False, 'error': str(e)}), 500
        
        elif sync_type == 'cliniko':
            try:
                cliniko_integration = ClinikoIntegration(
                    api_key=current_app.config['CLINIKO_API_KEY'],
                    shard=current_app.config['CLINIKO_SHARD']
                )
                if not patient.cliniko_patient_id:
                    # Try to match patient first
                    cliniko_id = cliniko_integration.match_patient(patient)
                    if cliniko_id:
                        patient.cliniko_patient_id = cliniko_id
                        db.session.commit()
                    else:
                        return jsonify({'success': False, 'error': 'Patient not linked to Cliniko and no match found'}), 400
                
                notes_count = cliniko_integration.sync_treatment_notes(patient)
                patient.cliniko_last_sync_at = datetime.utcnow()
                db.session.commit()
                return jsonify({'success': True, 'message': f'Cliniko notes synced. New notes: {notes_count}'})
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error syncing Cliniko data for patient {patient_id}: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        else:
            return jsonify({'success': False, 'error': 'Invalid sync type'}), 400
            
    except Exception as e:
        logger.error(f"Error in sync_patient_data for patient {patient_id}: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@appointments_bp.route('/patients/<int:patient_id>/report', methods=['GET', 'POST'])
@login_required
def patient_report(patient_id):
    """Generate and view patient reports"""
    patient = Patient.query.get_or_404(patient_id)
    
    if request.method == 'POST':
        report_type = request.form.get('report_type')
        # Logic for generating reports (e.g., PDF, AI summary)
        flash(f"Generating {report_type} report for {patient.full_name}...", 'info')
        return redirect(url_for('appointments.patient_report', patient_id=patient_id))
    
    return render_template('patient_report.html', patient=patient)

@appointments_bp.route('/patients/<int:patient_id>/report/patient', methods=['POST'])
@login_required
def generate_patient_report(patient_id):
    """Generate a patient-friendly AI health report"""
    patient = Patient.query.get_or_404(patient_id)
    try:
        reporter = AIHealthReporter(patient.id)
        report_text = reporter.generate_patient_report()
        
        # Save report as a patient note or correspondence
        # For now, just return it
        return jsonify({'success': True, 'report': report_text})
    except Exception as e:
        logger.error(f"Error generating patient report for {patient_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@appointments_bp.route('/patients/<int:patient_id>/report/clinical', methods=['POST'])
@login_required
def generate_clinical_report(patient_id):
    """Generate a clinical AI health report"""
    patient = Patient.query.get_or_404(patient_id)
    try:
        reporter = AIHealthReporter(patient.id)
        report_text = reporter.generate_clinical_report()
        
        return jsonify({'success': True, 'report': report_text})
    except Exception as e:
        logger.error(f"Error generating clinical report for {patient_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@appointments_bp.route('/patients/<int:patient_id>/report/video', methods=['POST'])
@login_required
def generate_video_report(patient_id):
    """Generate a video summary report using HeyGen"""
    patient = Patient.query.get_or_404(patient_id)
    try:
        heygen_service = HeyGenService(
            api_key=current_app.config.get('HEYGEN_API_KEY')
        )
        
        # This is a placeholder. In a real scenario, you'd pass actual content
        # or a script to HeyGen based on patient data.
        script_text = f"Here is a personalized health summary for {patient.first_name} {patient.last_name}."
        
        # Example: Use a default avatar and voice
        # You would likely have these configurable or patient-specific
        avatar_id = request.json.get('avatar_id', '65b11a3112114b0011111111') # Example avatar ID
        voice_id = request.json.get('voice_id', '2a2a2a2a2a2a2a2a2a2a2a2a') # Example voice ID
        
        video_response = heygen_service.create_video_from_script(
            script_text=script_text,
            avatar_id=avatar_id,
            voice_id=voice_id
        )
        
        if video_response and video_response.get('video_id'):
            return jsonify({'success': True, 'video_id': video_response['video_id'], 'message': 'Video generation started'})
        else:
            return jsonify({'success': False, 'error': video_response.get('error', 'Failed to start video generation')}), 500
    except Exception as e:
        logger.error(f"Error generating video report for {patient_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@appointments_bp.route('/video-room/<room_name>')
def video_room_patient(room_name):
    """Public page for patients to join video consultation"""
    # Reload .env file to get latest settings
    from dotenv import load_dotenv
    env_file_path = os.path.join(current_app.root_path, '..', 'capturecare.env')
    if os.path.exists(env_file_path):
        load_dotenv(env_file_path, override=True)
    
    # Get credentials from environment (most up-to-date)
    account_sid = os.getenv('TWILIO_ACCOUNT_SID', '') or current_app.config.get('TWILIO_ACCOUNT_SID', '')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN', '') or current_app.config.get('TWILIO_AUTH_TOKEN', '')
    api_key_sid = os.getenv('TWILIO_API_KEY_SID', '') or current_app.config.get('TWILIO_API_KEY_SID', '')
    api_key_secret = os.getenv('TWILIO_API_KEY_SECRET', '') or current_app.config.get('TWILIO_API_KEY_SECRET', '')
    
    # Strip whitespace
    account_sid = account_sid.strip() if account_sid else ''
    auth_token = auth_token.strip() if auth_token else ''
    api_key_sid = api_key_sid.strip() if api_key_sid else ''
    api_key_secret = api_key_secret.strip() if api_key_secret else ''
    
    # If credentials not configured, show waiting screen
    if not account_sid:
        return render_template('video_room.html', 
                            room_name=room_name,
                            access_token=None,
                            credentials_missing=True,
                            error_message='Twilio Account SID not configured (same as SMS)')
    
    use_api_keys = bool(api_key_sid and api_key_secret)
    if not use_api_keys and not auth_token:
        return render_template('video_room.html', 
                            room_name=room_name,
                            access_token=None,
                            credentials_missing=True,
                            error_message='Twilio Auth Token not configured. Video uses the SAME credentials as SMS (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN).')
    
    try:
        from twilio.jwt.access_token import AccessToken
        from twilio.jwt.access_token.grants import VideoGrant
        
        # Generate access token for patient
        identity = f"patient_{room_name}"
        
        if use_api_keys:
            # Use Video API Keys (from Settings page)
            # AccessToken(account_sid, signing_key_sid, secret, identity=identity)
            # account_sid = subject (sub) in JWT
            # signing_key_sid = issuer (iss) in JWT = API Key SID
            # secret = API Key Secret
            
            # Validate formats
            if not api_key_sid.startswith('SK'):
                raise ValueError(f"API Key SID must start with 'SK', got: {api_key_sid[:20]}...")
            if not account_sid.startswith('AC'):
                raise ValueError(f"Account SID must start with 'AC', got: {account_sid[:20]}...")
            
            logger.info(f"📹 Patient token using API Keys:")
            logger.info(f"   Account SID (subject): {account_sid}")
            logger.info(f"   API Key SID (issuer): {api_key_sid[:20]}...")
            
            token = AccessToken(account_sid, api_key_sid, api_key_secret, identity=identity)
            logger.info(f"📹 ✅ Patient AccessToken created successfully")
        else:
            # Fallback: Use Account SID + Auth Token (same credentials as SMS)
            # When using Auth Token, Account SID is used as both account_sid and signing_key_sid
            token = AccessToken(account_sid, account_sid, auth_token, identity=identity)
            logger.info(f"📹 Patient token using Account SID + Auth Token")
        
        # Grant access to video room
        video_grant = VideoGrant(room=room_name)
        token.add_grant(video_grant)
        
        # Token expires in 2 hours
        token.ttl = 7200
        
        # Note: Using ad-hoc rooms (recommended by Twilio for better scaling)
        # The room will be created automatically when the first participant connects
        # See: https://www.twilio.com/docs/video/tutorials/understanding-video-rooms#ad-hoc-rooms
        logger.info(f"📹 Patient accessing room: {room_name} (will be created on first participant join)")
        
        return render_template('video_room.html', 
                            room_name=room_name,
                            access_token=token.to_jwt(),
                            credentials_missing=False)
    except ValueError as e:
        # Validation errors
        error_msg = str(e)
        logger.error(f"❌ Validation error creating patient token: {error_msg}")
        return render_template('video_room.html', 
                            room_name=room_name,
                            access_token=None,
                            credentials_missing=True,
                            error_message=f'Invalid credentials: {error_msg}')
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error creating patient video token: {error_msg}")
        
        # Check for issuer/subject errors
        if 'issuer' in error_msg.lower() or 'subject' in error_msg.lower() or 'invalid access token' in error_msg.lower():
            error_message = (
                f'Invalid Access Token: The API Key SID does not belong to the Account SID.\n\n'
                f'Account SID: {account_sid[:15]}...\n'
                f'API Key SID: {api_key_sid[:20]}...\n\n'
                f'Please verify both belong to the same Twilio account.'
            )
        else:
            error_message = f'Error creating video token: {error_msg}'
        
        return render_template('video_room.html', 
                            room_name=room_name,
                            access_token=None,
                            credentials_missing=True,
                            error_message=error_message)

@appointments_bp.route('/patients/<int:patient_id>/reset-withings', methods=['POST'])
@login_required
def reset_withings(patient_id):
    """Reset Withings connection for a patient"""
    patient = Patient.query.get_or_404(patient_id)
    try:
        device = Device.query.filter_by(patient_id=patient_id, device_type='withings').first()
        if device:
            db.session.delete(device)
            db.session.commit()
        flash('Withings connection reset successfully.', 'success')
        return jsonify({'success': True, 'message': 'Withings connection reset'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error resetting Withings connection for patient {patient_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@appointments_bp.route('/patients/<int:patient_id>/authorize-withings')
@login_required
def authorize_withings(patient_id):
    """Initiate Withings OAuth flow for a patient"""
    patient = Patient.query.get_or_404(patient_id)
    try:
        # CRITICAL: Force production redirect URI - must be HTTPS
        production_redirect_uri = 'https://capturecare-3ecstuprbq-km.a.run.app/withings/callback'
        redirect_uri = current_app.config.get('WITHINGS_REDIRECT_URI', production_redirect_uri)
        if 'localhost' in redirect_uri or not redirect_uri.startswith('https://'):
            redirect_uri = production_redirect_uri
        
        auth_manager = WithingsAuthManager(
            client_id=current_app.config['WITHINGS_CLIENT_ID'],
            client_secret=current_app.config['WITHINGS_CLIENT_SECRET'],
            redirect_uri=redirect_uri
        )
        authorize_url = auth_manager.get_authorization_url(patient_id)
        return redirect(authorize_url)
    except Exception as e:
        logger.error(f"Error initiating Withings OAuth for patient {patient_id}: {e}")
        flash(f"Error initiating Withings connection: {str(e)}", 'error')
        return redirect(url_for('patients.patient_detail', patient_id=patient_id))

@appointments_bp.route('/api/patients/<int:patient_id>/send-withings-email', methods=['POST'])
@login_required
def send_withings_email(patient_id):
    """Send an email to the patient with the Withings authorization link"""
    patient = Patient.query.get_or_404(patient_id)
    
    if not patient.email:
        return jsonify({'success': False, 'error': 'Patient does not have an email address.'}), 400
    
    try:
        # CRITICAL: Force production redirect URI - must be HTTPS and match production URL
        production_redirect_uri = 'https://capturecare-310697189983.australia-southeast2.run.app/withings/callback'
        
        # Use production URI, fallback to config if needed
        redirect_uri = current_app.config.get('WITHINGS_REDIRECT_URI', production_redirect_uri)
        
        # Ensure it's HTTPS and production URL (override any localhost/env issues)
        if 'localhost' in redirect_uri or not redirect_uri.startswith('https://'):
            logger.warning(f"Withings redirect_uri was {redirect_uri}, overriding to production URL")
            redirect_uri = production_redirect_uri
        
        logger.info(f"Using Withings redirect_uri: {redirect_uri}")
        
        auth_manager = WithingsAuthManager(
            client_id=current_app.config['WITHINGS_CLIENT_ID'],
            client_secret=current_app.config['WITHINGS_CLIENT_SECRET'],
            redirect_uri=redirect_uri
        )
        authorize_url = auth_manager.get_authorization_url(patient_id)
        
        # CRITICAL: Double-check the authorize_url doesn't contain localhost
        if 'localhost' in authorize_url:
            logger.error(f"❌ CRITICAL ERROR: localhost found in authorize_url after generation!")
            logger.error(f"   authorize_url: {authorize_url}")
            logger.error(f"   redirect_uri used: {redirect_uri}")
            # Force replace localhost in the URL
            authorize_url = authorize_url.replace('localhost:5000', 'capturecare-3ecstuprbq-km.a.run.app')
            authorize_url = authorize_url.replace('http://', 'https://')
            logger.warning(f"   Fixed authorize_url: {authorize_url}")
        
        # Log the authorize URL to verify it's correct
        logger.info(f"📧 Generated Withings authorization URL for patient {patient_id}: {authorize_url}")
        logger.info(f"   Redirect URI in URL: {redirect_uri}")
        if 'localhost' in authorize_url:
            logger.error(f"❌ ERROR: localhost found in authorize_url! URL: {authorize_url}")
        
        subject = "Connect your Withings account to CaptureCare"
        
        # Force template reload and verify it's being used
        try:
            # Check if template file exists
            template_path = os.path.join(current_app.root_path, 'templates', 'emails', 'withings_invite.html')
            logger.info(f"📧 Looking for template at: {template_path}")
            if os.path.exists(template_path):
                logger.info(f"✅ Template file exists")
            else:
                logger.error(f"❌ Template file NOT FOUND at: {template_path}")
            
            # Clear template cache if in debug mode
            if current_app.config.get('DEBUG'):
                current_app.jinja_env.cache = None
            
            logger.info(f"📧 Rendering template: emails/withings_invite.html")
            logger.info(f"   Patient: {patient.first_name} {patient.last_name}")
            logger.info(f"   Authorize URL (first 100 chars): {authorize_url[:100]}")
            
            body_html = render_template('emails/withings_invite.html', patient=patient, authorize_url=authorize_url)
            logger.info(f"📧 Template rendered, body length: {len(body_html)}")
            logger.info(f"   Body contains 'CONNECT TO YOUR WITHINGS DEVICE': {'CONNECT TO YOUR WITHINGS DEVICE' in body_html}")
            logger.info(f"   Body contains 'authorize_url': {'authorize_url' in body_html}")
            
            # Verify the template was rendered correctly
            if 'CONNECT TO YOUR WITHINGS DEVICE' not in body_html:
                logger.error(f"❌ Template not rendered correctly! Button text missing.")
                logger.error(f"   Body preview (first 1000 chars): {body_html[:1000]}")
                # Fallback to inline HTML with correct button text
                body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
        .email-container {{ background-color: #ffffff; border-radius: 8px; padding: 40px; }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .logo {{ font-size: 24px; font-weight: bold; color: #00698f; }}
        h1 {{ color: #00698f; font-size: 28px; text-align: center; }}
        .button-container {{ text-align: center; margin: 40px 0; }}
        .connect-button {{
            display: inline-block;
            background-color: #00698f;
            color: #ffffff !important;
            padding: 16px 32px;
            text-decoration: none;
            border-radius: 6px;
            font-size: 18px;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <div class="logo">CaptureCare®</div>
            <p>Humanising Digital Health</p>
        </div>
        <h1>Connect Your Withings Device</h1>
        <p>Hello {patient.first_name},</p>
        <p>Your healthcare provider has requested that you connect your Withings device to your CaptureCare account.</p>
        <div class="button-container">
            <a href="{authorize_url}" class="connect-button" style="color: #ffffff; text-decoration: none;">
                CONNECT TO YOUR WITHINGS DEVICE
            </a>
        </div>
        <p style="font-size: 12px; color: #666; word-break: break-all;">If the button doesn't work, copy this link: {authorize_url}</p>
    </div>
</body>
</html>
"""
            else:
                logger.info(f"✅ Template rendered successfully with correct button text")
        except Exception as e:
            logger.error(f"❌ Error rendering template: {e}", exc_info=True)
            # Fallback HTML
            body_html = f"<html><body><h1>Connect Your Withings Device</h1><p>Hello {patient.first_name},</p><p><a href='{authorize_url}' style='background-color: #00698f; color: white; padding: 16px 32px; text-decoration: none; border-radius: 6px; font-weight: bold;'>CONNECT TO YOUR WITHINGS DEVICE</a></p></body></html>"
        
        # Use NotificationService which has send_email method for HTML emails
        from notification_service import NotificationService
        notification_service = NotificationService()
        
        body_text = f"Hello {patient.first_name},\n\nYour healthcare provider has requested that you connect your Withings device to your CaptureCare account.\n\nClick this link to authorize: {authorize_url}\n\nIf the link doesn't work, copy and paste it into your browser."
        
        email_sent = notification_service.send_email(
            to_email=patient.email,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            patient_id=patient_id,
            user_id=current_user.id if current_user.is_authenticated else None,
            log_correspondence=True
        )
        
        if not email_sent:
            raise Exception("Failed to send email via NotificationService")
        
        return jsonify({'success': True, 'message': 'Withings authorization email sent successfully.'})
    except Exception as e:
        logger.error(f"Error sending Withings authorization email to patient {patient_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@appointments_bp.route('/withings/callback')
def withings_callback():
    """Callback for Withings OAuth"""
    code = request.args.get('code')
    state = request.args.get('state')
    
    if not code:
        flash('Authorization failed - no code received', 'error')
        return redirect(url_for('appointments.master_calendar'))
    
    try:
        # CRITICAL: Force production redirect URI - must match the one used in authorization
        production_redirect_uri = 'https://capturecare-3ecstuprbq-km.a.run.app/withings/callback'
        redirect_uri = current_app.config.get('WITHINGS_REDIRECT_URI', production_redirect_uri)
        if 'localhost' in redirect_uri or not redirect_uri.startswith('https://'):
            redirect_uri = production_redirect_uri
        
        # Initialize auth manager
        auth_manager = WithingsAuthManager(
            client_id=current_app.config['WITHINGS_CLIENT_ID'],
            client_secret=current_app.config['WITHINGS_CLIENT_SECRET'],
            redirect_uri=redirect_uri
        )
        
        credentials = auth_manager.get_credentials(code, state)
        
        # Logic to get patient_id
        patient_id = None
        if state:
             if '_' in state:
                 try:
                     patient_id = int(state.split('_')[0])
                 except ValueError:
                     pass
        
        if not patient_id:
             # Fallback to session
             patient_id = session.get('patient_id')
             
        if not patient_id:
            flash('Unable to identify patient', 'error')
            return redirect(url_for('appointments.master_calendar'))
        
        auth_manager.save_tokens(patient_id, credentials)
        
        flash('Withings device authorized successfully!', 'success')
        return redirect(url_for('patients.patient_detail', patient_id=patient_id))
    
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Withings callback error: {error_msg}")
        
        if "Scope has changed" in error_msg or "scope" in error_msg.lower():
            if 'patient_id' in locals() and patient_id:
                 auth_manager.reset_patient_connection(patient_id)
            flash('Scope configuration changed. Please go to https://account.withings.com/partner/apps and revoke "CaptureCare" app, then click Connect Withings again.', 'warning')
        else:
            flash(f'Authorization error: {error_msg}', 'error')
        
        if 'patient_id' in locals() and patient_id:
            return redirect(url_for('patients.patient_detail', patient_id=patient_id))
        else:
            return redirect(url_for('appointments.master_calendar'))

