from flask import Blueprint, render_template, request, redirect, url_for, jsonify, session, flash, current_app
from flask_login import login_required, current_user
from ..models import db, User, NotificationTemplate
from ..notification_service import NotificationService
from datetime import datetime, timedelta
import os
import logging
import secrets

# Create blueprint
admin_bp = Blueprint('admin', __name__)
logger = logging.getLogger(__name__)

# Helper function to get notification service
def get_notification_service():
    # Notification service is initialized in web_dashboard.py, but we can create a new instance or access it via app context if needed
    # For simplicity, let's create a new instance as it loads config internally
    return NotificationService()

@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Settings page for editing API keys"""
    env_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'capturecare.env')
    
    if request.method == 'POST':
        logger.info("Settings save attempt")
        
        # Build the new env file content - preserve existing values if form field is empty
        # CRITICAL: Get password BEFORE building dict to preserve spaces
        smtp_password_raw = request.form.get('SMTP_PASSWORD', '') if 'SMTP_PASSWORD' in request.form else os.getenv('SMTP_PASSWORD', '')
        logger.info(f"🔐 SMTP_PASSWORD received - Length: {len(smtp_password_raw)}, Has spaces: {' ' in smtp_password_raw}, Value preview: [{smtp_password_raw[:10]}...]")
        
        env_vars = {
            'OPENAI_API_KEY': request.form.get('OPENAI_API_KEY', '') or os.getenv('OPENAI_API_KEY', ''),
            'XAI_API_KEY': request.form.get('XAI_API_KEY', '') or os.getenv('XAI_API_KEY', ''),
            'HEYGEN_API_KEY': request.form.get('HEYGEN_API_KEY', '') or os.getenv('HEYGEN_API_KEY', ''),
            'TWILIO_ACCOUNT_SID': request.form.get('TWILIO_ACCOUNT_SID', '') or os.getenv('TWILIO_ACCOUNT_SID', ''),
            'TWILIO_AUTH_TOKEN': request.form.get('TWILIO_AUTH_TOKEN', '') or os.getenv('TWILIO_AUTH_TOKEN', ''),
            'TWILIO_PHONE_NUMBER': request.form.get('TWILIO_PHONE_NUMBER', '') or os.getenv('TWILIO_PHONE_NUMBER', ''),
            'TWILIO_API_KEY_SID': request.form.get('TWILIO_API_KEY_SID', '') or os.getenv('TWILIO_API_KEY_SID', ''),
            'TWILIO_API_KEY_SECRET': request.form.get('TWILIO_API_KEY_SECRET', '') or os.getenv('TWILIO_API_KEY_SECRET', ''),
            'SMTP_SERVER': request.form.get('SMTP_SERVER', '') or os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
            'SMTP_PORT': request.form.get('SMTP_PORT', '') or os.getenv('SMTP_PORT', '587'),
            'SMTP_USERNAME': request.form.get('SMTP_USERNAME', '') or os.getenv('SMTP_USERNAME', ''),
            # CRITICAL: Use raw password value to preserve ALL characters including spaces
            'SMTP_PASSWORD': smtp_password_raw,
            'SMTP_FROM_EMAIL': request.form.get('SMTP_FROM_EMAIL', '') or os.getenv('SMTP_FROM_EMAIL', ''),
            'WITHINGS_CLIENT_ID': request.form.get('WITHINGS_CLIENT_ID', '') or os.getenv('WITHINGS_CLIENT_ID', ''),
            'WITHINGS_CLIENT_SECRET': request.form.get('WITHINGS_CLIENT_SECRET', '') or os.getenv('WITHINGS_CLIENT_SECRET', ''),
            'WITHINGS_REDIRECT_URI': request.form.get('WITHINGS_REDIRECT_URI', '') or os.getenv('WITHINGS_REDIRECT_URI', ''),
            'CLINIKO_API_KEY': request.form.get('CLINIKO_API_KEY', '') or os.getenv('CLINIKO_API_KEY', ''),
            'CLINIKO_SHARD': request.form.get('CLINIKO_SHARD', '') or os.getenv('CLINIKO_SHARD', 'au1'),
        }
        
        # Write to .env file
        try:
            logger.info(f"Writing settings to: {env_file_path}")
            
            # Write to env file
            with open(env_file_path, 'w') as f:
                f.write("# CaptureCare V7 Configuration\n")
                f.write("# Generated from Settings page\n\n")
                for key, value in env_vars.items():
                    if value:  # Only write non-empty values
                        # ALWAYS quote SMTP_PASSWORD to preserve spaces and special characters
                        if key == 'SMTP_PASSWORD':
                            # Escape backslashes first, then quotes, then wrap in double quotes
                            escaped_value = str(value).replace('\\', '\\\\').replace('"', '\\"')
                            f.write(f'{key}="{escaped_value}"\n')
                            logger.info(f"✅ Saved {key} - Length: {len(value)}, Spaces: {value.count(' ')}, Quoted: True")
                        else:
                            f.write(f"{key}={value}\n")
                        # Also set in current environment immediately
                        os.environ[key] = value
                        # Update app.config immediately so video token generation works
                        current_app.config[key] = value
                        logger.info(f"Set {key} in environment and app.config")
            
            # CRITICAL: In production (Cloud Run), also save to Secret Manager
            use_secret_manager = os.getenv('USE_SECRET_MANAGER', 'False').lower() == 'true'
            gcp_project_id = os.getenv('GCP_PROJECT_ID', '')
            
            if use_secret_manager and gcp_project_id:
                try:
                    from google.cloud import secretmanager
                    client = secretmanager.SecretManagerServiceClient()
                    
                    # Save each secret to Secret Manager
                    for key, value in env_vars.items():
                        if value:  # Only save non-empty values
                            secret_name = key.lower().replace('_', '-')  # Convert SMTP_PASSWORD to smtp-password
                            secret_id = f"{secret_name}"
                            parent = f"projects/{gcp_project_id}"
                            
                            try:
                                # Check if secret exists
                                secret_path = f"{parent}/secrets/{secret_id}"
                                try:
                                    client.get_secret(request={"name": secret_path})
                                    # Secret exists, add new version
                                    logger.info(f"📝 Updating secret: {secret_id}")
                                except:
                                    # Secret doesn't exist, create it
                                    logger.info(f"📝 Creating new secret: {secret_id}")
                                    client.create_secret(
                                        request={
                                            "parent": parent,
                                            "secret_id": secret_id,
                                            "secret": {"replication": {"automatic": {}}},
                                        }
                                    )
                                
                                # Add new version with the value
                                # CRITICAL: Preserve spaces - Secret Manager stores as bytes
                                if key == 'SMTP_PASSWORD':
                                    logger.info(f"🔐 Saving {key} to Secret Manager - Length: {len(value)}, Spaces: {value.count(' ')}")
                                
                                client.add_secret_version(
                                    request={
                                        "parent": secret_path,
                                        "payload": {"data": value.encode('utf-8')}
                                    }
                                )
                                logger.info(f"✅ Saved {key} to Secret Manager as {secret_id}")
                            except Exception as secret_error:
                                logger.error(f"❌ Failed to save {key} to Secret Manager: {secret_error}")
                except Exception as e:
                    logger.error(f"❌ Error saving to Secret Manager: {e}", exc_info=True)
                    # Don't fail the whole save if Secret Manager fails
            
            # Reload notification service credentials immediately
            notification_service = get_notification_service()
            notification_service.reload_credentials()
            
            # Save notification templates
            try:
                # Save SMS template
                sms_template_text = request.form.get('sms_appointment_template', '').strip()
                if sms_template_text:
                    sms_template = NotificationTemplate.query.filter_by(
                        template_type='sms',
                        template_name='appointment_confirmation',
                        is_predefined=False
                    ).first()
                    
                    if sms_template:
                        sms_template.message = sms_template_text
                        sms_template.updated_at = datetime.utcnow()
                    else:
                        sms_template = NotificationTemplate(
                            template_type='sms',
                            template_name='appointment_confirmation',
                            message=sms_template_text,
                            is_predefined=False,
                            is_active=True
                        )
                        db.session.add(sms_template)
                
                # Save Email template
                email_subject = request.form.get('email_subject_template', '').strip()
                email_body = request.form.get('email_body_template', '').strip()
                
                if email_subject or email_body:
                    email_template = NotificationTemplate.query.filter_by(
                        template_type='email',
                        template_name='appointment_confirmation',
                        is_predefined=False
                    ).first()
                    
                    if email_template:
                        if email_subject:
                            email_template.subject = email_subject
                        if email_body:
                            email_template.message = email_body
                        email_template.updated_at = datetime.utcnow()
                    else:
                        email_template = NotificationTemplate(
                            template_type='email',
                            template_name='appointment_confirmation',
                            subject=email_subject or None,
                            message=email_body or '',
                            is_predefined=False,
                            is_active=True
                        )
                        db.session.add(email_template)
                
                db.session.commit()
                logger.info("Notification templates saved successfully")
            except Exception as e:
                logger.error(f"Error saving notification templates: {e}", exc_info=True)
                # Don't fail the whole settings save if templates fail
            
            flash('Settings saved successfully! Changes are active immediately.', 'success')
            logger.info(f"Settings updated via Settings page - {len([v for v in env_vars.values() if v])} keys saved")
        except Exception as e:
            flash(f'Error saving settings: {str(e)}', 'error')
            logger.error(f"Error saving settings: {e}", exc_info=True)
        
        return redirect(url_for('admin.settings'))
    
    # GET request - load current values
    current_values = {
        'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY', ''),
        'XAI_API_KEY': os.getenv('XAI_API_KEY', ''),
        'HEYGEN_API_KEY': os.getenv('HEYGEN_API_KEY', ''),
        'TWILIO_ACCOUNT_SID': os.getenv('TWILIO_ACCOUNT_SID', ''),
        'TWILIO_AUTH_TOKEN': os.getenv('TWILIO_AUTH_TOKEN', ''),
        'TWILIO_PHONE_NUMBER': os.getenv('TWILIO_PHONE_NUMBER', ''),
        'TWILIO_API_KEY_SID': os.getenv('TWILIO_API_KEY_SID', ''),
        'TWILIO_API_KEY_SECRET': os.getenv('TWILIO_API_KEY_SECRET', ''),
        'SMTP_SERVER': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
        'SMTP_PORT': os.getenv('SMTP_PORT', '587'),
        'SMTP_USERNAME': os.getenv('SMTP_USERNAME', ''),
        'SMTP_PASSWORD': os.getenv('SMTP_PASSWORD', ''),
        'SMTP_FROM_EMAIL': os.getenv('SMTP_FROM_EMAIL', ''),
        'WITHINGS_CLIENT_ID': os.getenv('WITHINGS_CLIENT_ID', ''),
        'WITHINGS_CLIENT_SECRET': os.getenv('WITHINGS_CLIENT_SECRET', ''),
        'WITHINGS_REDIRECT_URI': os.getenv('WITHINGS_REDIRECT_URI', ''),
        'CLINIKO_API_KEY': os.getenv('CLINIKO_API_KEY', ''),
        'CLINIKO_SHARD': os.getenv('CLINIKO_SHARD', 'au1'),
    }
    
    # Get Google Calendar info
    calendar_info = None
    try:
        # Import here to avoid circular imports if possible, or move to better location
        # Assuming this is accessible or we need to pass it differently
        from ..calendar_sync import GoogleCalendarSync
        calendar_sync = GoogleCalendarSync()
        calendar_info = calendar_sync.get_calendar_info()
    except Exception as e:
        logger.warning(f"Could not fetch calendar info: {e}")
    
    config_status = {
        'openai_configured': bool(current_values['OPENAI_API_KEY']),
        'xai_configured': bool(current_values['XAI_API_KEY']),
        'calendar_info': calendar_info,
        'heygen_configured': bool(current_values['HEYGEN_API_KEY']),
        'twilio_configured': bool(current_values['TWILIO_ACCOUNT_SID'] and current_values['TWILIO_AUTH_TOKEN']),
        'smtp_configured': bool(current_values['SMTP_USERNAME'] and current_values['SMTP_PASSWORD']),
        'withings_configured': bool(current_values['WITHINGS_CLIENT_ID'] and current_values['WITHINGS_CLIENT_SECRET']),
        'cliniko_configured': bool(current_values['CLINIKO_API_KEY']),
        'current_values': current_values
    }
    
    return render_template('settings.html', **config_status)

@admin_bp.route('/user-management')
@login_required
def user_management():
    """User management page - admin only"""
    if not current_user.is_admin:
        flash('You must be an administrator to access user management.', 'error')
        return redirect(url_for('index'))
    
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('user_management.html', users=users)

@admin_bp.route('/admin/create-patient-auth-table', methods=['POST'])
def create_patient_auth_table():
    """Temporary admin endpoint to create PatientAuth table"""
    try:
        from sqlalchemy import inspect, text
        
        # Check if table exists
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        if 'patient_auth' in tables:
            return jsonify({
                'success': True,
                'message': 'PatientAuth table already exists',
                'tables': tables
            }), 200
        
        # Create the table
        from ..models import PatientAuth
        logger.info("Creating PatientAuth table...")
        PatientAuth.__table__.create(db.engine, checkfirst=True)
        
        # Create indexes
        with db.engine.connect() as conn:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_patient_auth_patient_id 
                ON patient_auth(patient_id);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_patient_auth_email 
                ON patient_auth(email);
            """))
            conn.commit()
        
        # Verify
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        if 'patient_auth' in tables:
            logger.info("✅ PatientAuth table created successfully!")
            return jsonify({
                'success': True,
                'message': 'PatientAuth table created successfully',
                'tables': tables
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Table creation may have failed'
            }), 500
            
    except Exception as e:
        logger.error(f"Error creating PatientAuth table: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_bp.route('/admin/sanitize-phones', methods=['GET', 'POST'])
@login_required
def sanitize_phones():
    """Update all patient phone numbers to a test number"""
    if not current_user.is_admin:
         flash('Admin access required', 'error')
         return redirect(url_for('index'))
         
    if request.method == 'POST':
        try:
            test_number = '+61417518940'
            
            # Update all patients
            patients = Patient.query.all()
            count = 0
            
            for patient in patients:
                patient.mobile = test_number
                patient.phone = test_number
                count += 1
            
            db.session.commit()
            logger.info(f"✅ Updated {count} patients with test phone number {test_number}")
            flash(f'Successfully updated {count} patients with phone number {test_number}', 'success')
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error sanitizing phone numbers: {e}")
            flash(f'Error updating phone numbers: {str(e)}', 'error')
            
        return redirect(url_for('admin.settings'))
        
    return render_template('admin/sanitize_phones.html', test_number='+61417518940')
