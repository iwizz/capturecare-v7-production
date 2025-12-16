from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash, Response, send_file
from werkzeug.exceptions import HTTPException
from flask_cors import CORS
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import or_
from .models import db, Patient, HealthData, Device, User, TargetRange, Appointment, PatientNote, WebhookLog, Invoice, InvoiceItem, PatientCorrespondence, CommunicationWebhookLog, NotificationTemplate, AvailabilityPattern, AvailabilityException, PatientAuth, OnboardingChecklist
from .config import Config
from .withings_auth import WithingsAuthManager
from .sync_health_data import HealthDataSynchronizer
from .patient_matcher import ClinikoIntegration
from .ai_health_reporter import AIHealthReporter
from .email_sender import EmailSender
from .calendar_sync import GoogleCalendarSync
from .notification_service import NotificationService
from .heygen_service import HeyGenService
from .stripe_service import StripeService
import logging
import os
import json
import requests
import smtplib
import jwt
import secrets
from functools import wraps
from flask_migrate import Migrate
from .extensions import cache
from .blueprints.admin import admin_bp
from .blueprints.api import api_bp
from .blueprints.auth import auth_bp
from .blueprints.patients import patients_bp
from .blueprints.patient_portal import patient_portal_bp
from .blueprints.appointments import appointments_bp
from .blueprints.leads import leads_bp


# Configure logging with Australian Eastern time
from logging import Formatter
import time

class AustralianTimezoneFormatter(Formatter):
    """Formatter that converts log timestamps to Australian Eastern time"""
    def formatTime(self, record, datefmt=None):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        
        # Convert timestamp to Australian Eastern time
        dt = datetime.fromtimestamp(record.created, tz=ZoneInfo('Australia/Sydney'))
        if datefmt:
            return dt.strftime(datefmt)
        else:
            return dt.strftime('%Y-%m-%d %H:%M:%S %Z')

# Set up logging with Australian timezone
handler = logging.StreamHandler()
handler.setFormatter(AustralianTimezoneFormatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))

logging.basicConfig(
    level=logging.INFO,
    handlers=[handler]
)
logger = logging.getLogger(__name__)
logger.info("Starting app init...")

# Load environment variables from capturecare.env file
from dotenv import load_dotenv
env_file_path = os.path.join(os.path.dirname(__file__), 'capturecare.env')
if os.path.exists(env_file_path):
    load_dotenv(env_file_path)
    logger.info(f"✅ Loaded environment variables from {env_file_path}")
    logger.info(f"🔑 HeyGen API configured: {bool(os.getenv('HEYGEN_API_KEY'))}")

app = Flask(__name__)
config = Config()
app.config.from_object(config)

# CRITICAL: Reload app.config from config instance to get updated values after Secret Manager load
# The Config.__init__() updates both class AND instance attributes, so we need to reload
for key in dir(config):
    if key.isupper() and not key.startswith('_'):
        app.config[key] = getattr(config, key)

# Initialize Cache
cache.init_app(app)

# CRITICAL: Database error handling to prevent connection corruption
@app.teardown_appcontext
def shutdown_session(exception=None):
    """Ensure database session is properly cleaned up, even on errors"""
    try:
        if exception:
            # On any exception, rollback and dispose of potentially bad connections
            db.session.rollback()
            # Force dispose of the connection pool to clear bad connections
            db.engine.dispose()
            logger.warning(f"Database session rolled back due to exception: {exception}")
        db.session.remove()
    except Exception as e:
        logger.error(f"Error during session cleanup: {e}")
        try:
            # Force engine disposal as last resort
            db.engine.dispose()
        except:
            pass

@app.errorhandler(Exception)
def handle_exception(e):
    """Global exception handler to log errors and clean up bad connections"""
    logger.error(f"Unhandled exception: {e}", exc_info=True)
    # Rollback and dispose on any error
    try:
        db.session.rollback()
        db.engine.dispose()
    except:
        pass
    # Return a proper error response
    if isinstance(e, HTTPException):
        return e
    return jsonify({'error': 'Internal server error', 'message': str(e)}), 500

app.secret_key = app.config['SECRET_KEY']

# CRITICAL: Initialize database BEFORE registering blueprints
CORS(app)
db.init_app(app)
migrate = Migrate(app, db)

# Register Blueprints (AFTER db.init_app)
app.register_blueprint(admin_bp)
app.register_blueprint(api_bp, url_prefix='/api')
app.register_blueprint(auth_bp)
app.register_blueprint(patients_bp)
app.register_blueprint(patient_portal_bp)
app.register_blueprint(appointments_bp)
app.register_blueprint(leads_bp)

# Force production security settings
os.environ['FLASK_DEBUG'] = '0'
SKIP_AUTH = False
app.config['DEBUG'] = False
app.config['PREFERRED_URL_SCHEME'] = 'https'  # Force HTTPS for all URL generation
logger.info("Production mode enabled: Debug disabled, authentication enforced.")

# Download client_secrets.json from Cloud Storage if not present (for Google OAuth)
try:
    if not os.path.exists('client_secrets.json'):
        from google.cloud import storage
        storage_client = storage.Client()
        bucket = storage_client.bucket('capturecare-v7-storage')
        blob = bucket.blob('client_secrets.json')
        blob.download_to_filename('client_secrets.json')
        logger.info("✅ Downloaded client_secrets.json from Cloud Storage")
    else:
        logger.info("✅ client_secrets.json already exists locally")
except Exception as e:
    logger.warning(f"⚠️ Could not download client_secrets.json from Cloud Storage: {e}")
    logger.warning("Google OAuth login may not work without this file")

# TEMPORARY: Force create admin user on startup (remove after first successful login)
def ensure_admin_user():
    """Ensure the admin user exists with correct credentials"""
    try:
        from werkzeug.security import generate_password_hash
        admin = User.query.filter_by(username='iwizz').first()
        if not admin:
            logger.info("Creating admin user 'iwizz'...")
            admin = User(
                username='iwizz',
                email='admin@capturecare.com',
                password_hash=generate_password_hash('wizard007'),
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()
            logger.info("✅ Admin user 'iwizz' created successfully")
        else:
            # Reset password to ensure it's correct
            logger.info("Resetting password for admin user 'iwizz'...")
            admin.password_hash = generate_password_hash('wizard007')
            admin.is_admin = True
            db.session.commit()
            logger.info("✅ Admin user password reset successfully")
    except Exception as e:
        logger.error(f"Failed to create/update admin user: {e}")

# Root route: Always redirect to login if not authenticated
@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
    return redirect(url_for('dashboard'))

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Custom decorator that respects SKIP_AUTH flag
def optional_login_required(f):
    """Decorator that skips authentication when SKIP_AUTH is True"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if SKIP_AUTH:
            # In debug mode, simulate a logged-in user
            if not current_user.is_authenticated:
                from flask_login import login_user as flask_login_user
                # Get first user or create a temp one
                user = User.query.first()
                if user:
                    flask_login_user(user)
                    logger.info(f"🔓 DEBUG MODE: Auto-logged in as {user.email}")
            return f(*args, **kwargs)
        else:
            # Normal authentication required
            return login_required(f)(*args, **kwargs)
    return decorated_function

withings_auth = WithingsAuthManager(
    app.config['WITHINGS_CLIENT_ID'],
    app.config['WITHINGS_CLIENT_SECRET'],
    app.config['WITHINGS_REDIRECT_URI']
)

synchronizer = HealthDataSynchronizer(app.config)

cliniko = ClinikoIntegration(
    app.config['CLINIKO_API_KEY'],
    app.config['CLINIKO_SHARD']
) if app.config['CLINIKO_API_KEY'] else None

# Initialize AI reporter - prefer XAI (Grok 4.1) if configured, otherwise use OpenAI
xai_key = app.config.get('XAI_API_KEY') or Config.XAI_API_KEY
openai_key = app.config.get('OPENAI_API_KEY') or Config.OPENAI_API_KEY

if xai_key:
    # Use Grok 4.1 if XAI API key is configured
    ai_reporter = AIHealthReporter(
        api_key=None,
        use_xai=True,
        xai_api_key=xai_key
    )
    logger.info("✅ Using xAI (Grok 4.1) for AI health reporting")
elif openai_key:
    # Fallback to OpenAI if XAI not configured
    ai_reporter = AIHealthReporter(
        api_key=openai_key,
        use_xai=False,
        xai_api_key=None
    )
    logger.info("✅ Using OpenAI GPT-4 for AI health reporting")
else:
    ai_reporter = None
    logger.warning("⚠️  No AI API keys configured - AI health reporting disabled")

email_sender = EmailSender(
    app.config.get('SMTP_SERVER'),
    app.config.get('SMTP_PORT'),
    app.config.get('SMTP_USERNAME'),
    app.config.get('SMTP_PASSWORD'),
    app.config.get('SMTP_FROM_EMAIL')
) if app.config.get('SMTP_SERVER') else None

try:
    calendar_sync = GoogleCalendarSync()
    logger.info("Google Calendar integration initialized successfully")
except Exception as e:
    calendar_sync = None
    logger.warning(f"Google Calendar integration not available: {e}")

notification_service = NotificationService()

heygen = HeyGenService(
    app.config.get('HEYGEN_API_KEY')
) if app.config.get('HEYGEN_API_KEY') else None

with app.app_context():
    try:
        db.create_all()
        logger.info("✅ Database tables created/verified")
        
        # Ensure admin user exists with correct credentials
        ensure_admin_user()
        
        existing_admin = User.query.filter_by(username='admin').first()
        if not existing_admin and os.getenv('FLASK_ENV') == 'development':
            admin_user = User(
                username='admin',
                email='admin@capturecare.com',
                first_name='System',
                last_name='Administrator',
                role='admin',
                is_admin=True,
                is_active=True,
                calendar_color='#00698f'
            )
            admin_user.set_password('admin123')
            db.session.add(admin_user)
            db.session.commit()
            logger.info("Default admin user created (username: admin, password: admin123)")
        else:
            logger.info("Production mode: Skipping default admin user creation")
    except Exception as e:
        logger.error(f"❌ Error during database initialization: {e}")
        import traceback
        traceback.print_exc()

# Add Jinja2 template filters for Australian timezone formatting
from .tz_utils import to_local, format_local

@app.template_filter('aest')
def aest_filter(dt, format='%Y-%m-%d %H:%M'):
    """Convert datetime to Australian Eastern time and format it"""
    if dt is None:
        return ''
    return format_local(dt, format)

@app.template_filter('aest_full')
def aest_full_filter(dt):
    """Convert datetime to Australian Eastern time with timezone abbreviation"""
    if dt is None:
        return ''
    return format_local(dt, '%Y-%m-%d %H:%M:%S %Z')

# Auth and Settings routes moved to blueprints


@app.route('/api/users', methods=['POST'])
@optional_login_required
def create_user():
    """Create a new user - admin only"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    
    try:
        import secrets
        data = request.get_json()
        
        if User.query.filter_by(username=data['username']).first():
            return jsonify({'success': False, 'error': 'Username already exists'}), 400
        
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'success': False, 'error': 'Email already exists'}), 400
        
        # Generate password setup token
        setup_token = secrets.token_urlsafe(32)
        token_expires = datetime.utcnow() + timedelta(days=7)
        
        new_user = User(
            username=data['username'],
            email=data['email'],
            first_name=data.get('first_name', ''),
            last_name=data.get('last_name', ''),
            role=data.get('role', 'practitioner'),
            is_admin=data.get('is_admin', False),
            is_active=data.get('is_active', True),
            calendar_color=data.get('calendar_color', '#00698f'),
            password_setup_token=setup_token,
            password_setup_token_expires=token_expires,
            password_set=False
        )
        
        # Set a temporary password (will be replaced when user sets their own)
        new_user.set_password(secrets.token_urlsafe(32))
        
        db.session.add(new_user)
        db.session.commit()
        
        # Send welcome email with password setup link
        if email_sender:
            setup_url = f"{request.host_url}setup-password?token={setup_token}"
            email_subject = "Welcome to CaptureCare - Set Your Password"
            email_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Welcome to CaptureCare</title>
            </head>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f9f9f9;">
                <div style="max-width: 600px; margin: 40px auto; background-color: #ffffff; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); overflow: hidden;">
                    
                    <!-- Header -->
                    <div style="background: linear-gradient(135deg, #265063 0%, #00698f 100%); padding: 30px 40px; text-align: center;">
                        <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 600;">Welcome to CaptureCare</h1>
                    </div>
                    
                    <!-- Content -->
                    <div style="padding: 40px;">
                        <p style="font-size: 16px; margin-bottom: 20px;">Hello <strong style="color: #00698f;">{new_user.first_name or new_user.username}</strong>,</p>
                        
                        <p style="font-size: 16px; color: #555; margin-bottom: 25px;">
                            An account has been created for you on the CaptureCare platform. We're excited to have you on board!
                        </p>
                        
                        <div style="background-color: #f0f8fa; border-left: 4px solid #00698f; padding: 15px 20px; margin-bottom: 30px; border-radius: 4px;">
                            <p style="margin: 5px 0; font-size: 14px;"><strong>Username:</strong> {new_user.username}</p>
                            <p style="margin: 5px 0; font-size: 14px;"><strong>Email:</strong> {new_user.email}</p>
                        </div>
                        
                        <p style="font-size: 16px; margin-bottom: 30px;">
                            To get started, please set your secure password by clicking the button below:
                        </p>
                        
                        <div style="text-align: center; margin-bottom: 35px;">
                            <a href="{setup_url}" style="background-color: #00698f; color: #ffffff; padding: 14px 30px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 16px; display: inline-block; transition: background-color 0.3s;">
                                Set Your Password
                            </a>
                        </div>
                        
                        <p style="font-size: 13px; color: #777; margin-bottom: 10px;">
                            Or copy and paste this link into your browser:
                        </p>
                        <p style="font-size: 13px; color: #00698f; word-break: break-all; margin-bottom: 20px; background-color: #f5f5f5; padding: 10px; border-radius: 4px;">
                            {setup_url}
                        </p>
                        
                        <p style="font-size: 13px; color: #999; font-style: italic;">
                            This invitation link will expire in 7 days.
                        </p>
                    </div>
                    
                    <!-- Footer -->
                    <div style="background-color: #f1f1f1; padding: 20px; text-align: center; border-top: 1px solid #e0e0e0;">
                        <p style="color: #888; font-size: 12px; margin: 0;">
                            &copy; {datetime.now().year} CaptureCare Health System. All rights reserved.<br>
                            Humanising Digital Health
                        </p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            email_sent = email_sender.send_notification(
                to_email=new_user.email,
                subject=email_subject,
                message=email_body
            )
            
            if email_sent:
                logger.info(f"Password setup email sent to {new_user.email}")
            else:
                logger.warning(f"Failed to send password setup email to {new_user.email}")
        
        logger.info(f"New user created: {new_user.username} by {current_user.username}")
        
        return jsonify({
            'success': True,
            'user': {
                'id': new_user.id,
                'username': new_user.username,
                'email': new_user.email,
                'full_name': new_user.full_name,
                'role': new_user.role,
                'is_admin': new_user.is_admin,
                'is_active': new_user.is_active
            },
            'email_sent': bool(email_sender)
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/users/<int:user_id>', methods=['PUT'])
@optional_login_required
def update_user(user_id):
    """Update user details - admin only"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    
    try:
        user = User.query.get_or_404(user_id)
        data = request.get_json()
        
        if 'username' in data and data['username'] != user.username:
            if User.query.filter_by(username=data['username']).first():
                return jsonify({'success': False, 'error': 'Username already exists'}), 400
            user.username = data['username']
        
        if 'email' in data and data['email'] != user.email:
            if User.query.filter_by(email=data['email']).first():
                return jsonify({'success': False, 'error': 'Email already exists'}), 400
            user.email = data['email']
        
        if 'first_name' in data:
            user.first_name = data['first_name']
        if 'last_name' in data:
            user.last_name = data['last_name']
        if 'role' in data:
            user.role = data['role']
        if 'is_admin' in data:
            user.is_admin = data['is_admin']
        if 'is_active' in data:
            user.is_active = data['is_active']
        if 'calendar_color' in data:
            user.calendar_color = data['calendar_color']
        if 'password' in data and data['password']:
            user.set_password(data['password'])
        
        db.session.commit()
        
        logger.info(f"User updated: {user.username} by {current_user.username}")
        
        return jsonify({
            'success': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'full_name': user.full_name,
                'role': user.role,
                'is_admin': user.is_admin,
                'is_active': user.is_active
            }
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@optional_login_required
def delete_user(user_id):
    """Delete a user - admin only"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    
    try:
        user = User.query.get_or_404(user_id)
        
        if user.id == current_user.id:
            return jsonify({'success': False, 'error': 'Cannot delete your own account'}), 400
        
        username = user.username
        db.session.delete(user)
        db.session.commit()
        
        logger.info(f"User deleted: {username} by {current_user.username}")
        
        return jsonify({'success': True, 'message': f'User {username} deleted successfully'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/users/<int:user_id>/toggle-active', methods=['POST'])
@optional_login_required
def toggle_user_active(user_id):
    """Toggle user active status - admin only"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    
    try:
        user = User.query.get_or_404(user_id)
        
        if user.id == current_user.id:
            return jsonify({'success': False, 'error': 'Cannot deactivate your own account'}), 400
        
        user.is_active = not user.is_active
        db.session.commit()
        
        status = 'activated' if user.is_active else 'deactivated'
        logger.info(f"User {status}: {user.username} by {current_user.username}")
        
        return jsonify({
            'success': True,
            'is_active': user.is_active,
            'message': f'User {user.username} {status} successfully'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error toggling user status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400




# API routes moved to blueprints


# Patient list moved


# Communications moved


# Add patient moved


@app.route('/patients/<int:patient_id>')
@optional_login_required
def patient_detail(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    
    # Get date range from query params (default to last 30 days)
    end_date_str = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
    start_date_str = request.args.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)  # Include end date
    except ValueError:
        start_date = datetime.now() - timedelta(days=30)
        end_date = datetime.now()
    
    # Query health data and devices in parallel (optimized)
    from sqlalchemy import orm
    health_data = HealthData.query.filter(
        HealthData.patient_id == patient_id,
        HealthData.timestamp >= start_date,
        HealthData.timestamp < end_date
    ).order_by(HealthData.timestamp.asc()).all()
    
    devices = Device.query.filter_by(patient_id=patient_id).all()
    
    # Organize health data by type with chronological order (optimized)
    health_summary = {}
    latest_values = {}
    
    for data in health_data:
        measurement_type = data.measurement_type
        if measurement_type not in health_summary:
            health_summary[measurement_type] = []
        health_summary[measurement_type].append({
            'value': data.value,
            'unit': data.unit,
            'timestamp': data.timestamp.isoformat(),
            'timestamp_display': data.timestamp.strftime('%Y-%m-%d %H:%M')
        })
        # Track latest value (only update if this is newer)
        if measurement_type not in latest_values or data.timestamp > latest_values[measurement_type]['timestamp']:
            latest_values[measurement_type] = {
                'value': data.value,
                'unit': data.unit,
                'timestamp': data.timestamp
            }
    
    cliniko_notes = []
    if patient.cliniko_patient_id and cliniko:
        cliniko_notes = cliniko.get_treatment_notes(patient.cliniko_patient_id)
    
    # Calculate patient age
    patient_age = None
    if patient.date_of_birth:
        today = datetime.now().date()
        patient_age = int((today - patient.date_of_birth).days / 365.25)
    
    # Load target ranges (convert None to empty string for HTML compatibility)
    # Handle case where show_in_patient_app column doesn't exist yet
    try:
        target_ranges = TargetRange.query.filter_by(patient_id=patient_id).all()
    except Exception as e:
        # If column doesn't exist, rollback and query without it
        db.session.rollback()  # Rollback the failed transaction
        
        # Use raw SQL to get target ranges without the new column
        from sqlalchemy import text
        try:
            result = db.session.execute(
                text("SELECT measurement_type, min_value, max_value, target_value FROM target_ranges WHERE patient_id = :patient_id"),
                {'patient_id': patient_id}
            )
            target_ranges = []
            for row in result:
                # Create a simple object-like structure
                class SimpleTargetRange:
                    def __init__(self, measurement_type, min_value, max_value, target_value):
                        self.measurement_type = measurement_type
                        self.min_value = min_value
                        self.max_value = max_value
                        self.target_value = target_value
                target_ranges.append(SimpleTargetRange(row[0], row[1], row[2], row[3]))
        except Exception as e2:
            logger.error(f"Error loading target ranges with raw SQL: {e2}")
            target_ranges = []  # Return empty list if both methods fail
    
    target_ranges_dict = {}
    for tr in target_ranges:
        target_ranges_dict[tr.measurement_type] = {
            'min': tr.min_value if tr.min_value is not None else '',
            'max': tr.max_value if tr.max_value is not None else '',
            'target': tr.target_value if tr.target_value is not None else '',
            'show_in_patient_app': getattr(tr, 'show_in_patient_app', True)  # Default to True if column doesn't exist
        }
    
    # Get all active practitioners for appointment booking
    practitioners = User.query.filter_by(is_active=True).order_by(User.first_name).all()
    
    # Get public base URL for video room links
    base_url = app.config.get('BASE_URL', '') or os.getenv('BASE_URL', '') or os.getenv('PUBLIC_URL', '')
    
    # Get or create onboarding checklist for this patient
    onboarding_checklist = OnboardingChecklist.query.filter_by(patient_id=patient_id).first()
    if not onboarding_checklist:
        onboarding_checklist = OnboardingChecklist(patient_id=patient_id)
        db.session.add(onboarding_checklist)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating onboarding checklist: {e}")
            onboarding_checklist = None
    
    return render_template('patient_detail.html', 
                         patient=patient, 
                         patient_age=patient_age,
                         health_summary=health_summary,
                         latest_values=latest_values,
                         devices=devices,
                         cliniko_notes=cliniko_notes,
                         start_date=start_date_str,
                         end_date=end_date_str,
                         target_ranges=target_ranges_dict,
                         practitioners=practitioners,
                         base_url=base_url,
                         onboarding_checklist=onboarding_checklist,
                         today=datetime.now().strftime('%Y-%m-%d'))


# ============================================================================
# ONBOARDING CHECKLIST API
# ============================================================================

@app.route('/api/patients/<int:patient_id>/onboarding-checklist', methods=['GET'])
@optional_login_required
def get_onboarding_checklist(patient_id):
    """Get onboarding checklist for a patient"""
    patient = Patient.query.get_or_404(patient_id)
    
    checklist = OnboardingChecklist.query.filter_by(patient_id=patient_id).first()
    if not checklist:
        # Create new checklist if it doesn't exist
        checklist = OnboardingChecklist(patient_id=patient_id)
        db.session.add(checklist)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': f'Failed to create checklist: {str(e)}'}), 500
    
    return jsonify(checklist.to_dict())

@app.route('/api/patients/<int:patient_id>/onboarding-checklist', methods=['PUT'])
@optional_login_required
def update_onboarding_checklist(patient_id):
    """Update onboarding checklist items"""
    patient = Patient.query.get_or_404(patient_id)
    
    checklist = OnboardingChecklist.query.filter_by(patient_id=patient_id).first()
    if not checklist:
        checklist = OnboardingChecklist(patient_id=patient_id)
        db.session.add(checklist)
    
    data = request.get_json()
    
    # Mark as started if not already
    if not checklist.started_at:
        checklist.started_at = datetime.utcnow()
    
    # Update checklist items from request
    if 'items' in data:
        for section_key, section_items in data['items'].items():
            for item_key, item_value in section_items.items():
                if hasattr(checklist, item_key):
                    setattr(checklist, item_key, item_value)
    
    # Update notes if provided
    if 'notes' in data:
        checklist.notes = data['notes']
    
    # Update completed_by
    if current_user.is_authenticated:
        checklist.completed_by_id = current_user.id
    
    # Check if checklist is complete and mark completion time
    if checklist.is_complete() and not checklist.completed_at:
        checklist.completed_at = datetime.utcnow()
    elif not checklist.is_complete() and checklist.completed_at:
        # If unchecking items, remove completed_at
        checklist.completed_at = None
    
    try:
        db.session.commit()
        return jsonify(checklist.to_dict())
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to update checklist: {str(e)}'}), 500

@app.route('/api/patients/<int:patient_id>/target-ranges', methods=['GET'])
@optional_login_required
def get_target_ranges(patient_id):
    """Get all target ranges for a patient"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        # Handle case where show_in_patient_app column doesn't exist yet
        try:
            target_ranges = TargetRange.query.filter_by(patient_id=patient_id).all()
        except Exception as e:
            # If column doesn't exist, rollback and use raw SQL
            db.session.rollback()  # Rollback the failed transaction
            
            from sqlalchemy import text
            try:
                result = db.session.execute(
                    text("""
                        SELECT id, measurement_type, target_mode, min_value, max_value, target_value, 
                               unit, source, auto_apply_ai, suggested_min, suggested_max, suggested_value, 
                               last_ai_generated_at
                        FROM target_ranges 
                        WHERE patient_id = :patient_id
                    """),
                    {'patient_id': patient_id}
                )
                target_ranges = []
                for row in result:
                    class SimpleTargetRange:
                        def __init__(self, row_data):
                            self.id = row_data[0]
                            self.measurement_type = row_data[1]
                            self.target_mode = row_data[2]
                            self.min_value = row_data[3]
                            self.max_value = row_data[4]
                            self.target_value = row_data[5]
                            self.unit = row_data[6]
                            self.source = row_data[7]
                            self.auto_apply_ai = row_data[8]
                            self.suggested_min = row_data[9]
                            self.suggested_max = row_data[10]
                            self.suggested_value = row_data[11]
                            self.last_ai_generated_at = row_data[12]
                    target_ranges.append(SimpleTargetRange(row))
            except Exception as e2:
                logger.error(f"Error loading target ranges with raw SQL: {e2}")
                target_ranges = []  # Return empty list if both methods fail
        
        # Optimized: Use list comprehension
        ranges_list = [{
            'id': tr.id,
            'measurement_type': tr.measurement_type,
            'target_mode': tr.target_mode,
            'min_value': tr.min_value,
            'max_value': tr.max_value,
            'target_value': tr.target_value,
            'unit': tr.unit,
            'source': tr.source,
            'auto_apply_ai': tr.auto_apply_ai,
            'show_in_patient_app': getattr(tr, 'show_in_patient_app', True),
            'suggested_min': tr.suggested_min,
            'suggested_max': tr.suggested_max,
            'suggested_value': tr.suggested_value,
            'last_ai_generated_at': tr.last_ai_generated_at.isoformat() if tr.last_ai_generated_at else None
        } for tr in target_ranges]
        
        return jsonify({'success': True, 'target_ranges': ranges_list, 'patient_age': (datetime.now().date() - patient.date_of_birth).days // 365 if patient.date_of_birth else None, 'patient_sex': patient.sex, 'patient_weight': None})
    except Exception as e:
        logger.error(f"Error getting target ranges: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/patients/<int:patient_id>/target-ranges', methods=['POST'])
@optional_login_required
def save_target_ranges(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    
    try:
        data = request.get_json()
        
        for measurement_type, values in data.items():
            target_mode = values.get('target_mode', 'range')
            min_val = float(values.get('min')) if values.get('min') not in [None, ''] else None
            max_val = float(values.get('max')) if values.get('max') not in [None, ''] else None
            target_val = float(values.get('target')) if values.get('target') not in [None, ''] else None
            unit = values.get('unit', '')
            source = values.get('source', 'manual')
            auto_apply = values.get('auto_apply_ai', False)
            show_in_app = values.get('show_in_patient_app', True)  # Default to True if not specified
            
            existing = TargetRange.query.filter_by(
                patient_id=patient_id,
                measurement_type=measurement_type
            ).first()
            
            if existing:
                if target_mode:  # Only update if target_mode is provided (means we have actual values)
                    existing.target_mode = target_mode
                    existing.min_value = min_val
                    existing.max_value = max_val
                    existing.target_value = target_val
                    existing.unit = unit
                    existing.source = source
                    existing.auto_apply_ai = auto_apply
                # Always update show_in_patient_app if provided (even if no target values)
                if hasattr(TargetRange, 'show_in_patient_app') and 'show_in_patient_app' in values:
                    existing.show_in_patient_app = show_in_app
                existing.updated_at = datetime.utcnow()
            else:
                # Create new range if we have target values OR just show_in_patient_app setting
                if target_mode or 'show_in_patient_app' in values:
                    range_kwargs = {
                        'patient_id': patient_id,
                        'measurement_type': measurement_type,
                        'target_mode': target_mode if target_mode else 'range',
                        'min_value': min_val,
                        'max_value': max_val,
                        'target_value': target_val,
                        'unit': unit,
                        'source': source,
                        'auto_apply_ai': auto_apply
                    }
                    if hasattr(TargetRange, 'show_in_patient_app'):
                        range_kwargs['show_in_patient_app'] = show_in_app
                    
                    new_range = TargetRange(**range_kwargs)
                    db.session.add(new_range)
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Target ranges saved successfully'})
    
    except Exception as e:
        logger.error(f"Error saving target ranges: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/patients/<int:patient_id>/target-ranges/ai-suggest', methods=['POST'])
@optional_login_required
def generate_ai_target_suggestions(patient_id):
    """Generate AI-powered target range suggestions based on patient demographics"""
    global ai_reporter
    
    try:
        patient = Patient.query.get_or_404(patient_id)
        
        # Improved validation: check for None and empty strings
        missing_fields = []
        if not patient.date_of_birth:
            missing_fields.append('date of birth')
        if not patient.sex or (isinstance(patient.sex, str) and not patient.sex.strip()):
            missing_fields.append('sex')
        
        if missing_fields:
            # Log actual values for debugging
            logger.warning(f"AI suggestions requested for patient {patient_id} (Name: {patient.first_name} {patient.last_name})")
            logger.warning(f"  date_of_birth: {patient.date_of_birth} (type: {type(patient.date_of_birth)})")
            logger.warning(f"  sex: '{patient.sex}' (type: {type(patient.sex)}, length: {len(patient.sex) if patient.sex else 0})")
            logger.warning(f"  Missing fields: {missing_fields}")
            
            error_msg = f"Patient {' and '.join(missing_fields)} {'is' if len(missing_fields) == 1 else 'are'} required for AI suggestions"
            return jsonify({'success': False, 'error': error_msg}), 400
        
        age = (datetime.now().date() - patient.date_of_birth).days // 365
        sex = patient.sex.strip().lower() if isinstance(patient.sex, str) else str(patient.sex).lower()
        
        latest_weight_data = HealthData.query.filter_by(
            patient_id=patient_id,
            measurement_type='weight'
        ).order_by(HealthData.timestamp.desc()).first()
        
        weight = latest_weight_data.value if latest_weight_data else None
        
        prompt = f"""As a medical expert, provide evidence-based target ranges for the following health metrics for a {age}-year-old {sex} patient{f' weighing {weight}kg' if weight else ''}.

Please provide target ranges in JSON format for these metrics:
- heart_rate (bpm)
- systolic_bp (mmHg)
- diastolic_bp (mmHg)
- weight (kg)
- steps (daily goal)
- sleep_duration (hours)
- spo2 (%)
- hydration (%)
- body_temperature (°C)

Format as JSON with this structure:
{{
    "metric_name": {{"min": value, "max": value, "target": value_if_applicable, "unit": "unit"}}
}}

Only include min/max for ranges, or target for single values. Base recommendations on clinical guidelines for this patient's age and sex."""

        # Always reload AI reporter from current config to ensure we have the latest settings
        # Reload .env file to get latest values
        from dotenv import load_dotenv
        import os
        config_dir = os.path.dirname(os.path.abspath(__file__))
        env_path = os.path.join(config_dir, 'capturecare.env')
        load_dotenv(env_path, override=True)
        
        # Try multiple sources for API keys
        xai_key = (app.config.get('XAI_API_KEY') or 
                  os.getenv('XAI_API_KEY') or 
                  getattr(Config, 'XAI_API_KEY', None) or
                  '')
        openai_key = (app.config.get('OPENAI_API_KEY') or 
                     os.getenv('OPENAI_API_KEY') or 
                     getattr(Config, 'OPENAI_API_KEY', None) or
                     '')
        
        # Clean up keys (remove whitespace)
        xai_key = xai_key.strip() if xai_key else ''
        openai_key = openai_key.strip() if openai_key else ''
        
        logger.info(f"Checking AI keys - XAI: {'configured' if xai_key else 'not configured'}, OpenAI: {'configured' if openai_key else 'not configured'}")
        
        reporter_to_use = None
        if xai_key:
            reporter_to_use = AIHealthReporter(
                api_key=None,
                use_xai=True,
                xai_api_key=xai_key
            )
            logger.info("✅ Using xAI (Grok) for target suggestions")
        elif openai_key:
            reporter_to_use = AIHealthReporter(
                api_key=openai_key,
                use_xai=False,
                xai_api_key=None
            )
            logger.info("✅ Using OpenAI for target suggestions")
        else:
            logger.error("❌ No AI API keys found in config")
            return jsonify({'success': False, 'error': 'AI API key not configured. Please add OpenAI or xAI API key in Settings.'}), 500
        
        if not reporter_to_use or not reporter_to_use.client:
            logger.error(f"❌ Failed to initialize AI reporter - client: {reporter_to_use.client if reporter_to_use else 'None'}")
            return jsonify({'success': False, 'error': 'Failed to initialize AI client. Please check your API key in Settings.'}), 500
        
        import json
        response = reporter_to_use.client.chat.completions.create(
            model=reporter_to_use.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        
        suggestions_text = response.choices[0].message.content
        suggestions_json = json.loads(suggestions_text.strip().replace('```json', '').replace('```', ''))
        
        for metric, values in suggestions_json.items():
            existing = TargetRange.query.filter_by(
                patient_id=patient_id,
                measurement_type=metric
            ).first()
            
            if existing:
                existing.suggested_min = values.get('min')
                existing.suggested_max = values.get('max')
                existing.suggested_value = values.get('target')
                existing.last_ai_generated_at = datetime.utcnow()
            else:
                new_range = TargetRange(
                    patient_id=patient_id,
                    measurement_type=metric,
                    target_mode='range' if 'min' in values and 'max' in values else 'single',
                    suggested_min=values.get('min'),
                    suggested_max=values.get('max'),
                    suggested_value=values.get('target'),
                    unit=values.get('unit', ''),
                    source='manual',
                    last_ai_generated_at=datetime.utcnow()
                )
                db.session.add(new_range)
        
        db.session.commit()
        
        return jsonify({'success': True, 'suggestions': suggestions_json, 'message': 'AI suggestions generated successfully'})
    
    except Exception as e:
        logger.error(f"Error generating AI suggestions: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/patients/<int:patient_id>/health_data/heart_rate', methods=['GET'])
@optional_login_required
def get_heart_rate_data(patient_id):
    """Get heart rate data filtered by device source and optionally by date"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        device_source = request.args.get('device_source', 'all')
        date_str = request.args.get('date')
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        
        query = HealthData.query.filter(
            HealthData.patient_id == patient_id,
            HealthData.measurement_type == 'heart_rate'
        )
        
        if device_source == 'scale_or_null':
            query = query.filter(
                or_(
                    HealthData.device_source == 'scale',
                    HealthData.device_source.is_(None)
                )
            )
        elif device_source != 'all':
            query = query.filter_by(device_source=device_source)
        
        # Handle date range (start_date and end_date)
        if start_date_str or end_date_str:
            try:
                if start_date_str:
                    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                    query = query.filter(HealthData.timestamp >= start_date)
                if end_date_str:
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
                    query = query.filter(HealthData.timestamp < end_date)
            except ValueError as e:
                logger.error(f"Invalid date format: start_date={start_date_str}, end_date={end_date_str}, error={e}")
        elif date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                start_of_day = datetime.combine(target_date, datetime.min.time())
                end_of_day = datetime.combine(target_date, datetime.max.time())
                query = query.filter(
                    HealthData.timestamp >= start_of_day,
                    HealthData.timestamp <= end_of_day
                )
            except ValueError:
                logger.error(f"Invalid date format: {date_str}")
        
        health_data = query.order_by(HealthData.timestamp.asc()).all()
        
        data = [{
            'value': d.value,
            'timestamp': d.timestamp.isoformat(),
            'unit': d.unit,
            'device_source': d.device_source
        } for d in health_data]
        
        # Get available dates using raw SQL to avoid label access issues
        from sqlalchemy import text
        if device_source == 'scale_or_null':
            dates_result = db.session.execute(text("""
                SELECT DISTINCT DATE(timestamp) as date
                FROM health_data
                WHERE patient_id = :patient_id
                  AND measurement_type = 'heart_rate'
                  AND (device_source = 'scale' OR device_source IS NULL)
                ORDER BY DATE(timestamp)
            """), {'patient_id': patient_id}).fetchall()
        elif device_source != 'all':
            dates_result = db.session.execute(text("""
                SELECT DISTINCT DATE(timestamp) as date
                FROM health_data
                WHERE patient_id = :patient_id
                  AND measurement_type = 'heart_rate'
                  AND device_source = :device_source
                ORDER BY DATE(timestamp)
            """), {'patient_id': patient_id, 'device_source': device_source}).fetchall()
        else:
            dates_result = db.session.execute(text("""
                SELECT DISTINCT DATE(timestamp) as date
                FROM health_data
                WHERE patient_id = :patient_id
                  AND measurement_type = 'heart_rate'
                ORDER BY DATE(timestamp)
            """), {'patient_id': patient_id}).fetchall()
        
        available_dates = [str(d[0]) for d in dates_result]
        
        return jsonify({
            'data': data,
            'available_dates': available_dates,
            'current_date': date_str if date_str else None
        })
    
    except Exception as e:
        logger.error(f"Error fetching heart rate data: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            db.session.remove()
        except:
            pass

@app.route('/patients/<int:patient_id>/health_data/heart_rate/daily_minmax', methods=['GET'])
@optional_login_required
def get_heart_rate_daily_minmax(patient_id):
    """Get min/max/avg heart rate by day for watch data"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        
        # Get date range from query params (default to last 30 days)
        end_date_str = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
        start_date_str = request.args.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        
        try:
            # Parse dates - handle both date-only and datetime strings
            if 'T' in start_date_str or ' ' in start_date_str:
                # Contains time component, parse as datetime
                start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
            else:
                # Date only
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            
            if 'T' in end_date_str or ' ' in end_date_str:
                # Contains time component, parse as datetime
                end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
            else:
                # Date only - add 1 day to include the full end date
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
        except (ValueError, AttributeError) as e:
            logger.warning(f"Invalid date format in heart_rate/daily_minmax: start={start_date_str}, end={end_date_str}, error={e}")
            start_date = datetime.now() - timedelta(days=30)
            end_date = datetime.now()
        
        # Use raw SQL to avoid SQLAlchemy label issues with date() function
        from sqlalchemy import text
        daily_data = db.session.execute(text("""
            SELECT 
                DATE(timestamp) as date,
                MIN(value) as min_hr,
                MAX(value) as max_hr,
                AVG(value) as avg_hr
            FROM health_data
            WHERE patient_id = :patient_id
              AND device_source = 'watch'
              AND measurement_type = 'heart_rate'
              AND timestamp >= :start_date
              AND timestamp < :end_date
            GROUP BY DATE(timestamp)
            ORDER BY DATE(timestamp)
        """), {
            'patient_id': patient_id,
            'start_date': start_date,
            'end_date': end_date
        }).fetchall()
        
        data = [{
            'date': str(d[0]),  # date is first column
            'min': d[1],  # min_hr
            'max': d[2],  # max_hr
            'avg': round(d[3], 1)  # avg_hr
        } for d in daily_data]
        
        return jsonify({'data': data})
    
    except Exception as e:
        logger.error(f"Error fetching daily min/max heart rate: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            db.session.remove()
        except:
            pass

@app.route('/patients/<int:patient_id>/update', methods=['POST'])
@optional_login_required
def update_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    
    try:
        patient.first_name = request.form.get('first_name', patient.first_name)
        patient.last_name = request.form.get('last_name', patient.last_name)
        patient.email = request.form.get('email', patient.email)
        
        dob_str = request.form.get('date_of_birth')
        if dob_str:
            patient.date_of_birth = datetime.strptime(dob_str, '%Y-%m-%d').date()
        
        patient.phone = request.form.get('phone') or None
        patient.mobile = request.form.get('mobile') or None
        patient.sex = request.form.get('sex') or None
        
        # Update allocated practitioner
        allocated_pract_id = request.form.get('allocated_practitioner_id')
        if allocated_pract_id:
            patient.allocated_practitioner_id = int(allocated_pract_id) if allocated_pract_id else None
        else:
            patient.allocated_practitioner_id = None
        
        patient.address_line1 = request.form.get('address_line1') or None
        patient.address_line2 = request.form.get('address_line2') or None
        patient.city = request.form.get('city') or None
        patient.state = request.form.get('state') or None
        patient.postcode = request.form.get('postcode') or None
        patient.country = request.form.get('country') or None
        
        patient.emergency_contact_name = request.form.get('emergency_contact_name') or None
        patient.emergency_contact_phone = request.form.get('emergency_contact_phone') or None
        patient.emergency_contact_relationship = request.form.get('emergency_contact_relationship') or None
        
        patient.occupation = request.form.get('occupation') or None
        patient.medicare_number = request.form.get('medicare_number') or None
        patient.dva_number = request.form.get('dva_number') or None
        
        patient.notes = request.form.get('notes') or None
        patient.medical_alerts = request.form.get('medical_alerts') or None
        
        db.session.commit()
        flash('Patient information updated successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating patient: {e}")
        flash(f'Error updating patient: {str(e)}', 'error')
    
    return redirect(url_for('patient_detail', patient_id=patient_id))

@app.route('/patients/<int:patient_id>/delete')
@optional_login_required
def delete_patient(patient_id):
    """Delete a patient and all associated data"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        patient_name = f"{patient.first_name} {patient.last_name}"
        
        db.session.delete(patient)
        db.session.commit()
        
        logger.info(f"🗑️ Deleted patient {patient_id} - {patient_name}")
        flash(f'Patient {patient_name} has been permanently deleted.', 'success')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting patient {patient_id}: {e}")
        flash(f'Error deleting patient: {str(e)}', 'error')
        return redirect(url_for('patient_detail', patient_id=patient_id))
    
    return redirect(url_for('patients.patients_list'))




@app.route('/api/patients/<int:patient_id>', methods=['GET'])
@optional_login_required
def api_get_patient(patient_id):
    """Get patient data as JSON"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        return jsonify({
            'success': True,
            'patient': {
                'id': patient.id,
                'first_name': patient.first_name,
                'last_name': patient.last_name,
                'email': patient.email,
                'phone': patient.phone or patient.mobile,
                'date_of_birth': patient.date_of_birth.isoformat() if patient.date_of_birth else None,
                'sex': patient.sex
            }
        })
    except Exception as e:
        logger.error(f"Error getting patient {patient_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/patients/list', methods=['GET'])
@optional_login_required
def api_list_patients():
    """Get list of all patients for dropdowns"""
    try:
        # Get all patients, ordered by name
        patients = Patient.query.order_by(Patient.first_name, Patient.last_name).all()
        
        return jsonify({
            'success': True,
            'patients': [{
                'id': p.id,
                'name': f"{p.first_name} {p.last_name}",
                'phone': p.phone or p.mobile,
                'email': p.email
            } for p in patients]
        })
    except Exception as e:
        logger.error(f"Error getting patient list: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/patients/search')
@optional_login_required
def api_search_patients():
    """Search patients by name or email"""
    query_param = request.args.get('q', '').strip()
    
    if len(query_param) < 2:
        return jsonify({'success': False, 'error': 'Query must be at least 2 characters'}), 400
    
    # Search by first name, last name, or email
    search_pattern = f'%{query_param}%'
    patients = Patient.query.filter(
        or_(
            Patient.first_name.ilike(search_pattern),
            Patient.last_name.ilike(search_pattern),
            Patient.email.ilike(search_pattern)
        )
    ).order_by(Patient.first_name, Patient.last_name).limit(20).all()
    
    patient_list = []
    for patient in patients:
        patient_list.append({
            'id': patient.id,
            'first_name': patient.first_name,
            'last_name': patient.last_name,
            'email': patient.email,
            'phone': patient.phone or patient.mobile
        })
    
    return jsonify({'success': True, 'patients': patient_list})

@app.route('/api/patients/<int:patient_id>/health-data')
@optional_login_required
def api_health_data(patient_id):
    days_back = int(request.args.get('days', 30))
    metric_type = request.args.get('type')
    
    query = HealthData.query.filter(
        HealthData.patient_id == patient_id,
        HealthData.timestamp >= datetime.now() - timedelta(days=days_back)
    )
    
    if metric_type:
        query = query.filter(HealthData.measurement_type == metric_type)
    
    health_data = query.order_by(HealthData.timestamp).all()
    
    data = []
    for item in health_data:
        data.append({
            'type': item.measurement_type,
            'value': item.value,
            'unit': item.unit,
            'timestamp': item.timestamp.isoformat(),
            'source': item.source
        })
    
    return jsonify(data)

@app.route('/api/sync-all', methods=['POST'])
@optional_login_required
def api_sync_all():
    results = synchronizer.sync_all_patients(days_back=1)
    return jsonify(results)

@app.route('/api/webhook/patient', methods=['POST'])
def webhook_add_patient():
    """
    Public webhook endpoint to receive patient data from Google Forms or other external sources.
    Accepts JSON data and creates a new patient in the database.
    
    Expected JSON fields:
    - first_name (required)
    - last_name (required)
    - email (required)
    - date_of_birth (optional, format: YYYY-MM-DD)
    - phone (optional)
    - mobile (optional)
    - sex (optional)
    - address_line1 (optional)
    - address_line2 (optional)
    - city (optional)
    - state (optional)
    - postcode (optional)
    - country (optional)
    - emergency_contact_name (optional)
    - emergency_contact_phone (optional)
    - emergency_contact_relationship (optional)
    - occupation (optional)
    - medicare_number (optional)
    - dva_number (optional)
    - notes (optional)
    - medical_alerts (optional)
    """
    try:
        # Parse JSON data
        data = request.get_json() if request.is_json else request.form.to_dict()
        
        if not data:
            logger.warning("Webhook received empty data")
            return jsonify({
                'success': False,
                'error': 'No data received'
            }), 400
        
        # Helper function to normalize field names (handles spaces, capitalization, etc.)
        def normalize_data(raw_data):
            """Convert form field names to database field names"""
            # Direct field mapping for camelCase and other variations
            field_mapping = {
                # CamelCase mappings (without underscores)
                'firstname': 'first_name',
                'lastname': 'last_name',
                'dateofbirth': 'date_of_birth',
                'mobilephone': 'mobile',
                'homephone': 'phone',
                'hasgp': 'has_gp',
                'gpname': 'gp_name',
                'gpaddress': 'gp_address',
                'gpphone': 'gp_phone',
                'onmedications': 'on_medications',
                'medicationslist': 'current_medications',
                'emergencycontact': 'emergency_contact_name',
                'emergencymobile': 'emergency_contact_phone',
                'emergencyemail': 'emergency_contact_email',
                'consentemergencycontact': 'emergency_contact_consent',
                'hassmartdevice': 'owns_smart_device',
                'healthconcerns': 'health_focus_areas',
                'agreeterms': 'terms_consent',
                'digitalsignature': 'digital_signature',
                # Snake_case mappings (with underscores from normalization)
                'mobile_phone': 'mobile',
                'home_phone': 'phone',
                'has_gp': 'has_gp',
                'gp_name': 'gp_name',
                'gp_address': 'gp_address',
                'gp_phone': 'gp_phone',
                'on_medications': 'on_medications',
                'medications_list': 'current_medications',
                'emergency_contact': 'emergency_contact_name',
                'emergency_mobile': 'emergency_contact_phone',
                'emergency_email': 'emergency_contact_email',
                'consent_emergency_contact': 'emergency_contact_consent',
                'has_smart_device': 'owns_smart_device',
                'health_concerns': 'health_focus_areas',
                'agree_terms': 'terms_consent',
                'digital_signature': 'digital_signature',
                # Alternative names
                'email_address': 'email',
                'suburb': 'city',
                'address': 'address_line1',
                'next_of_kin': 'emergency_contact_name',
                'medications': 'current_medications',
                'gp_phone_number': 'gp_phone',
                'state_territory': 'state'
            }
            
            normalized = {}
            for key, value in raw_data.items():
                # Convert to lowercase and replace spaces/hyphens with underscores
                normalized_key = key.lower().replace(' ', '_').replace('-', '_')
                # Remove asterisks and special characters
                normalized_key = normalized_key.replace('*', '').replace('?', '').strip('_')
                
                # Apply field mapping if exists
                if normalized_key in field_mapping:
                    normalized_key = field_mapping[normalized_key]
                
                normalized[normalized_key] = value
            
            return normalized
        
        # Normalize the incoming data
        data = normalize_data(data)
        
        # Log all received field names for debugging
        logger.info(f"Webhook received fields: {list(data.keys())}")
        logger.info(f"Webhook received patient data for: {data.get('first_name')} {data.get('last_name')}")
        
        # Validate required fields
        required_fields = ['first_name', 'last_name', 'email']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            logger.warning(f"Webhook missing required fields: {missing_fields}")
            
            # Log failure
            webhook_log = WebhookLog(
                success=False,
                email=data.get('email'),
                error_message=f'Missing required fields: {", ".join(missing_fields)}',
                request_data=str(data)
            )
            db.session.add(webhook_log)
            db.session.commit()
            
            return jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }), 400
        
        # Check if patient with this email already exists
        existing_patient = Patient.query.filter_by(email=data['email']).first()
        if existing_patient:
            logger.warning(f"Webhook: Patient with email {data['email']} already exists")
            
            # Log duplicate
            webhook_log = WebhookLog(
                success=False,
                patient_id=existing_patient.id,
                patient_name=f"{existing_patient.first_name} {existing_patient.last_name}",
                email=data['email'],
                error_message='Patient with this email already exists',
                request_data=str(data)
            )
            db.session.add(webhook_log)
            db.session.commit()
            
            return jsonify({
                'success': False,
                'error': 'Patient with this email already exists',
                'patient_id': existing_patient.id
            }), 409
        
        # Parse date of birth if provided
        date_of_birth = None
        if data.get('date_of_birth'):
            try:
                date_of_birth = datetime.strptime(data['date_of_birth'], '%Y-%m-%d').date()
            except ValueError:
                logger.warning(f"Invalid date format: {data['date_of_birth']}")
                return jsonify({
                    'success': False,
                    'error': 'Invalid date_of_birth format. Use YYYY-MM-DD'
                }), 400
        
        # Helper function to convert string booleans to actual booleans
        def parse_bool(value):
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ('yes', 'true', '1', 'on')
            return False
        
        # Helper function to convert arrays to comma-separated strings
        def parse_array(value):
            if isinstance(value, list):
                return ', '.join(str(v) for v in value)
            return value if value else None
        
        # Map 'suburb' to 'city' if provided
        city_value = data.get('city', '').strip() or None
        
        # Create new patient with all fields
        patient = Patient(
            first_name=data['first_name'].strip(),
            last_name=data['last_name'].strip(),
            email=data['email'].strip().lower(),
            date_of_birth=date_of_birth,
            phone=data.get('phone', '').strip() or None,
            mobile=data.get('mobile', '').strip() or None,
            sex=data.get('sex', '').strip() or None,
            address_line1=data.get('address_line1', '').strip() or None,
            address_line2=data.get('address_line2', '').strip() or None,
            city=city_value,
            state=data.get('state', '').strip() or None,
            postcode=data.get('postcode', '').strip() or None,
            country=data.get('country', '').strip() or 'Australia',
            emergency_contact_name=data.get('emergency_contact_name', '').strip() or None,
            emergency_contact_phone=data.get('emergency_contact_phone', '').strip() or None,
            emergency_contact_email=data.get('emergency_contact_email', '').strip() or None,
            emergency_contact_relationship=data.get('emergency_contact_relationship', '').strip() or None,
            emergency_contact_consent=parse_bool(data.get('emergency_contact_consent', False)),
            gp_name=data.get('gp_name', '').strip() or None,
            gp_address=data.get('gp_address', '').strip() or None,
            gp_phone=data.get('gp_phone', '').strip() or None,
            has_gp=parse_bool(data.get('has_gp', False)),
            current_medications=data.get('current_medications', '').strip() or None,
            owns_smart_device=parse_bool(data.get('owns_smart_device', False)),
            health_focus_areas=parse_array(data.get('health_focus_areas')),
            occupation=data.get('occupation', '').strip() or None,
            medicare_number=data.get('medicare_number', '').strip() or None,
            dva_number=data.get('dva_number', '').strip() or None,
            notes=data.get('notes', '').strip() or data.get('digital_signature', '').strip() or None,
            medical_alerts=data.get('medical_alerts', '').strip() or None,
            terms_consent=parse_bool(data.get('terms_consent', False) or data.get('agreeterms', False))
        )
        
        db.session.add(patient)
        db.session.commit()
        
        # Log success
        webhook_log = WebhookLog(
            success=True,
            patient_id=patient.id,
            patient_name=f"{patient.first_name} {patient.last_name}",
            email=patient.email,
            request_data=str(data)
        )
        db.session.add(webhook_log)
        db.session.commit()
        
        logger.info(f"✅ Webhook: Successfully created patient {patient.id} - {patient.first_name} {patient.last_name}")
        
        return jsonify({
            'success': True,
            'message': 'Patient created successfully',
            'patient_id': patient.id,
            'patient': {
                'id': patient.id,
                'first_name': patient.first_name,
                'last_name': patient.last_name,
                'email': patient.email
            }
        }), 201
        
    except Exception as e:
        logger.error(f"❌ Webhook error: {str(e)}")
        db.session.rollback()
        
        # Log error
        try:
            webhook_log = WebhookLog(
                success=False,
                error_message=str(e),
                request_data=str(data) if 'data' in locals() else 'No data'
            )
            db.session.add(webhook_log)
            db.session.commit()
        except:
            pass
        
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}'
        }), 500

@app.route('/api/webhook/logs', methods=['GET'])
@optional_login_required
def get_webhook_logs():
    """Get recent webhook activity logs"""
    try:
        logs = WebhookLog.query.order_by(WebhookLog.created_at.desc()).limit(20).all()
        
        logs_data = []
        for log in logs:
            logs_data.append({
                'id': log.id,
                'success': log.success,
                'patient_id': log.patient_id,
                'patient_name': log.patient_name,
                'email': log.email,
                'error': log.error_message,
                'timestamp': log.created_at.isoformat() if log.created_at else None
            })
        
        return jsonify({'logs': logs_data})
    except Exception as e:
        logger.error(f"Error fetching webhook logs: {e}", exc_info=True)
        # Return empty logs array instead of error to prevent frontend issues
        # This prevents the frontend from breaking when the table doesn't exist or DB is unavailable
        return jsonify({'logs': [], 'error': str(e)}), 200  # Return 200 with empty logs


@app.route('/patients/<int:patient_id>/invoices', methods=['GET'])
@optional_login_required
def get_patient_invoices(patient_id):
    """Get all invoices for a patient"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        invoices = Invoice.query.filter_by(patient_id=patient_id).order_by(Invoice.created_at.desc()).all()
        
        return jsonify({
            'invoices': [{
                'id': inv.id,
                'invoice_number': inv.invoice_number,
                'invoice_type': inv.invoice_type,
                'status': inv.status,
                'total_amount': inv.total_amount,
                'amount_paid': inv.amount_paid,
                'currency': inv.currency,
                'invoice_date': inv.invoice_date.isoformat() if inv.invoice_date else None,
                'due_date': inv.due_date.isoformat() if inv.due_date else None,
                'paid_date': inv.paid_date.isoformat() if inv.paid_date else None,
                'description': inv.description,
                'is_recurring': inv.is_recurring,
                'recurring_frequency': inv.recurring_frequency,
                'next_billing_date': inv.next_billing_date.isoformat() if inv.next_billing_date else None,
                'stripe_hosted_invoice_url': inv.stripe_hosted_invoice_url,
                'stripe_invoice_pdf': inv.stripe_invoice_pdf,
                'items': [{
                    'description': item.description,
                    'quantity': item.quantity,
                    'unit_price': item.unit_price,
                    'tax_rate': item.tax_rate,
                    'amount': item.amount
                } for item in inv.items]
            } for inv in invoices]
        })
    except Exception as e:
        logger.error(f"Error fetching patient invoices: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            db.session.remove()
        except:
            pass

@app.route('/patients/<int:patient_id>/invoices', methods=['POST'])
@optional_login_required
def create_patient_invoice(patient_id):
    """Create a new invoice for a patient"""
    patient = Patient.query.get_or_404(patient_id)
    data = request.get_json()
    
    try:
        invoice_type = data.get('invoice_type', 'one_off')
        items = data.get('items', [])
        description = data.get('description', '')
        notes = data.get('notes', '')
        
        if not items:
            return jsonify({'success': False, 'error': 'At least one item is required'}), 400
        
        if invoice_type == 'one_off':
            due_days = data.get('due_days', 14)
            invoice = StripeService.create_one_off_invoice(
                patient_id=patient_id,
                items=items,
                description=description,
                notes=notes,
                due_days=due_days
            )
        elif invoice_type == 'recurring':
            frequency = data.get('frequency', 'monthly')
            start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d').date() if data.get('start_date') else None
            end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d').date() if data.get('end_date') else None
            
            invoice = StripeService.create_recurring_invoice(
                patient_id=patient_id,
                items=items,
                frequency=frequency,
                start_date=start_date,
                end_date=end_date,
                description=description,
                notes=notes
            )
        else:
            return jsonify({'success': False, 'error': 'Invalid invoice type'}), 400
        
        return jsonify({
            'success': True,
            'message': 'Invoice created successfully',
            'invoice': {
                'id': invoice.id,
                'invoice_number': invoice.invoice_number,
                'total_amount': invoice.total_amount,
                'status': invoice.status,
                'stripe_hosted_invoice_url': invoice.stripe_hosted_invoice_url
            }
        })
        
    except Exception as e:
        logger.error(f"Error creating invoice: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/patients/<int:patient_id>/invoices/<int:invoice_id>/sync', methods=['POST'])
@optional_login_required
def sync_invoice_status(patient_id, invoice_id):
    """Sync invoice status from Stripe"""
    try:
        invoice = StripeService.sync_invoice_status(invoice_id)
        return jsonify({
            'success': True,
            'status': invoice.status,
            'amount_paid': invoice.amount_paid
        })
    except Exception as e:
        logger.error(f"Error syncing invoice: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/patients/<int:patient_id>/invoices/<int:invoice_id>/cancel', methods=['POST'])
@optional_login_required
def cancel_invoice_subscription(patient_id, invoice_id):
    """Cancel a recurring subscription"""
    try:
        invoice = StripeService.cancel_subscription(invoice_id)
        return jsonify({
            'success': True,
            'message': 'Subscription cancelled successfully',
            'status': invoice.status
        })
    except Exception as e:
        logger.error(f"Error cancelling subscription: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/patients/import-from-cliniko', methods=['POST'])
@optional_login_required
def import_from_cliniko():
    if not cliniko:
        flash('Cliniko API not configured', 'error')
        return redirect(url_for('patients.patients_list'))
    
    try:
        cliniko_patients = cliniko.get_all_patients()
        imported_count = 0
        skipped_count = 0
        
        for cp in cliniko_patients:
            email = cp.get('email')
            if not email:
                skipped_count += 1
                continue
            
            existing = Patient.query.filter_by(email=email).first()
            if existing:
                if not existing.cliniko_patient_id:
                    existing.cliniko_patient_id = str(cp.get('id'))
                    db.session.commit()
                skipped_count += 1
                continue
            
            dob = None
            if cp.get('date_of_birth'):
                try:
                    dob = datetime.strptime(cp.get('date_of_birth'), '%Y-%m-%d').date()
                except:
                    pass
            
            new_patient = Patient(
                first_name=cp.get('first_name', ''),
                last_name=cp.get('last_name', ''),
                email=email,
                date_of_birth=dob,
                cliniko_patient_id=str(cp.get('id'))
            )
            
            db.session.add(new_patient)
            imported_count += 1
        
        db.session.commit()
        
        flash(f'Successfully imported {imported_count} patients from Cliniko (skipped {skipped_count} existing)', 'success')
        
    except Exception as e:
        logger.error(f"Error importing from Cliniko: {e}")
        flash(f'Error importing patients: {str(e)}', 'error')
    
    return redirect(url_for('patients.patients_list'))

# Patient Notes API Endpoints
@app.route('/api/patients/<int:patient_id>/notes', methods=['GET'])
@optional_login_required
def get_patient_notes(patient_id):
    """Get all notes for a patient"""
    try:
        notes = PatientNote.query.filter_by(patient_id=patient_id).order_by(PatientNote.created_at.desc()).all()
        
        notes_data = []
        for note in notes:
            note_dict = {
                'id': note.id,
                'subject': note.subject or (note.note_text.split('\n')[0][:200] if note.note_text else ''),
                'note_text': note.note_text,
                'note_type': note.note_type,
                'author': note.author or 'System',
                'created_at': note.created_at.isoformat(),
                'updated_at': note.updated_at.isoformat(),
                'appointment_id': note.appointment_id,
                'attachment_filename': note.attachment_filename,
                'attachment_path': note.attachment_path,
                'attachment_type': note.attachment_type,
                'attachment_size': note.attachment_size
            }
            
            # Include appointment details if linked
            if note.appointment_id:
                appointment = Appointment.query.get(note.appointment_id)
                if appointment:
                    note_dict['appointment'] = {
                        'title': appointment.title,
                        'start_time': appointment.start_time.isoformat(),
                        'appointment_type': appointment.appointment_type
                    }
            
            notes_data.append(note_dict)
        
        return jsonify({'success': True, 'notes': notes_data})
    except Exception as e:
        logger.error(f"Error getting patient notes: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/patients/<int:patient_id>/notes', methods=['POST'])
@optional_login_required
def create_patient_note(patient_id):
    """Create a new patient note (supports multipart/form-data for file uploads)"""
    try:
        # Check if this is a multipart request (file upload)
        if request.content_type and 'multipart/form-data' in request.content_type:
            # Handle file upload
            note_text = request.form.get('note_text', '')
            subject = request.form.get('subject', '')
            note_type = request.form.get('note_type', 'manual')
            author = request.form.get('author', 'Admin')
            appointment_id = request.form.get('appointment_id')
            
            # Extract subject from first line if not provided
            if not subject and note_text:
                first_line = note_text.split('\n')[0].strip()
                subject = first_line[:200] if len(first_line) > 200 else first_line
            
            note = PatientNote(
                patient_id=patient_id,
                appointment_id=int(appointment_id) if appointment_id and appointment_id != 'null' else None,
                subject=subject,
                note_text=note_text,
                note_type=note_type,
                author=author
            )
            
            # Handle file upload if present
            if 'attachment' in request.files:
                file = request.files['attachment']
                if file and file.filename:
                    # Secure the filename
                    from werkzeug.utils import secure_filename
                    filename = secure_filename(file.filename)
                    
                    # Create uploads directory if it doesn't exist
                    uploads_dir = os.path.join(app.root_path, 'static', 'uploads', 'notes')
                    os.makedirs(uploads_dir, exist_ok=True)
                    
                    # Generate unique filename
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    unique_filename = f"{patient_id}_{timestamp}_{filename}"
                    file_path = os.path.join(uploads_dir, unique_filename)
                    
                    # Save file
                    file.save(file_path)
                    
                    # Store relative path and metadata
                    note.attachment_filename = filename
                    note.attachment_path = f"uploads/notes/{unique_filename}"
                    note.attachment_type = file.content_type or 'application/octet-stream'
                    note.attachment_size = os.path.getsize(file_path)
                    
                    logger.info(f"File uploaded: {filename} ({note.attachment_size} bytes)")
            
            db.session.add(note)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'note': {
                    'id': note.id,
                    'subject': note.subject,
                    'note_text': note.note_text,
                    'note_type': note.note_type,
                    'author': note.author,
                    'created_at': note.created_at.isoformat(),
                    'updated_at': note.updated_at.isoformat(),
                    'appointment_id': note.appointment_id,
                    'attachment_filename': note.attachment_filename,
                    'attachment_path': note.attachment_path,
                    'attachment_type': note.attachment_type,
                    'attachment_size': note.attachment_size
                }
            })
        else:
            # Handle JSON request (legacy, no file)
            data = request.get_json()
            
            # Extract subject from first line if not provided
            note_text = data.get('note_text', '')
            subject = data.get('subject', '')
            if not subject and note_text:
                # Use first line as subject (max 200 chars)
                first_line = note_text.split('\n')[0].strip()
                subject = first_line[:200] if len(first_line) > 200 else first_line
            
            note = PatientNote(
                patient_id=patient_id,
                appointment_id=data.get('appointment_id'),
                subject=subject,
                note_text=note_text,
                note_type=data.get('note_type', 'manual'),
                author=data.get('author', 'Admin')
            )
            
            db.session.add(note)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'note': {
                    'id': note.id,
                    'subject': note.subject,
                    'note_text': note.note_text,
                    'note_type': note.note_type,
                    'author': note.author,
                    'created_at': note.created_at.isoformat(),
                    'updated_at': note.updated_at.isoformat(),
                    'appointment_id': note.appointment_id
                }
            })
    except Exception as e:
        logger.error(f"Error creating patient note: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/notes/<int:note_id>', methods=['PUT'])
@optional_login_required
def update_patient_note(note_id):
    """Update an existing patient note"""
    try:
        note = PatientNote.query.get_or_404(note_id)
        data = request.get_json()
        
        if 'note_text' in data:
            note.note_text = data['note_text']
        if 'note_type' in data:
            note.note_type = data['note_type']
        if 'author' in data:
            note.author = data['author']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'note': {
                'id': note.id,
                'note_text': note.note_text,
                'note_type': note.note_type,
                'author': note.author,
                'created_at': note.created_at.isoformat(),
                'updated_at': note.updated_at.isoformat()
            }
        })
    except Exception as e:
        logger.error(f"Error updating patient note: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/notes/<int:note_id>', methods=['DELETE'])
@optional_login_required
def delete_patient_note(note_id):
    """Delete a patient note and its attachment"""
    try:
        note = PatientNote.query.get_or_404(note_id)
        
        # Delete attached file if it exists
        if note.attachment_path:
            try:
                file_path = os.path.join(app.root_path, 'static', note.attachment_path)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Deleted attachment file: {file_path}")
            except Exception as file_error:
                logger.warning(f"Could not delete attachment file: {file_error}")
                # Continue with note deletion even if file deletion fails
        
        db.session.delete(note)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting patient note: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/notes/<int:note_id>/attachment', methods=['GET'])
@optional_login_required
def download_note_attachment(note_id):
    """Download or view note attachment"""
    try:
        note = PatientNote.query.get_or_404(note_id)
        
        if not note.attachment_path or not note.attachment_filename:
            return jsonify({'success': False, 'error': 'No attachment found'}), 404
        
        file_path = os.path.join(app.root_path, 'static', note.attachment_path)
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'error': 'Attachment file not found'}), 404
        
        # Determine if we should display inline (images, PDFs) or force download
        inline_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'application/pdf']
        as_attachment = note.attachment_type not in inline_types
        
        return send_file(
            file_path,
            mimetype=note.attachment_type or 'application/octet-stream',
            as_attachment=as_attachment,
            download_name=note.attachment_filename
        )
    except Exception as e:
        logger.error(f"Error downloading attachment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/notes/update-subjects', methods=['POST'])
@optional_login_required
def update_notes_with_subjects():
    """Update all existing notes to extract subjects from first line"""
    try:
        notes = PatientNote.query.filter(
            (PatientNote.subject == None) | (PatientNote.subject == '')
        ).all()
        
        updated_count = 0
        for note in notes:
            if note.note_text:
                # Extract first line as subject (max 200 chars)
                first_line = note.note_text.split('\n')[0].strip()
                if first_line:
                    note.subject = first_line[:200] if len(first_line) > 200 else first_line
                    updated_count += 1
        
        db.session.commit()
        
        logger.info(f"✅ Updated {updated_count} notes with subjects")
        
        return jsonify({
            'success': True,
            'updated_count': updated_count
        })
    except Exception as e:
        logger.error(f"Error updating notes with subjects: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

# Patient Correspondence Endpoints
@app.route('/api/patients/<int:patient_id>/correspondence', methods=['GET'])
@optional_login_required
def get_patient_correspondence(patient_id):
    """Get all correspondence for a patient"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        
        # Get all correspondence for this patient, ordered by most recent first
        correspondence = PatientCorrespondence.query.filter_by(
            patient_id=patient_id,
            is_deleted=False
        ).order_by(PatientCorrespondence.sent_at.desc()).all()
        
        return jsonify({
            'success': True,
            'correspondence': [{
                'id': c.id,
                'channel': c.channel,
                'direction': c.direction,
                'subject': c.subject,
                'body': c.body,
                'recipient_email': c.recipient_email,
                'recipient_phone': c.recipient_phone,
                'sender_email': c.sender_email,
                'sender_phone': c.sender_phone,
                'status': c.status,
                'external_id': c.external_id,
                'error_message': c.error_message,
                'call_duration': c.call_duration,
                'recording_url': c.recording_url,
                'call_sid': c.call_sid,
                'transcription_status': c.transcription_status,
                'sent_at': c.sent_at.isoformat() if c.sent_at else None,
                'delivered_at': c.delivered_at.isoformat() if c.delivered_at else None
            } for c in correspondence]
        })
    except Exception as e:
        logger.error(f"Error fetching correspondence: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/patients/<int:patient_id>/send-sms', methods=['POST'])
@optional_login_required
def send_patient_sms(patient_id):
    """Send SMS to patient via Twilio"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        data = request.json
        
        phone = data.get('phone')
        message = data.get('message')
        
        if not phone or not message:
            return jsonify({'success': False, 'error': 'Phone and message are required'}), 400
        
        # Send SMS using notification service
        from .notification_service import NotificationService
        notif_service = NotificationService()
        
        # Pass patient_id and user_id so NotificationService can log correspondence
        # Set log_correspondence=True to let NotificationService handle logging
        result = notif_service.send_sms(
            phone, 
            message, 
            patient_id=patient_id, 
            user_id=current_user.id if current_user.is_authenticated else None,
            log_correspondence=True
        )
        
        if result.get('success'):
            return jsonify({'success': True, 'message': 'SMS sent successfully'})
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Failed to send SMS')}), 400
    except Exception as e:
        logger.error(f"Error sending SMS: {e}")
        db.session.rollback()
        # Check if it's a duplicate key error and provide a helpful message
        error_str = str(e)
        if 'UniqueViolation' in error_str or 'duplicate key' in error_str.lower():
            logger.warning(f"⚠️  Duplicate key error detected. This may indicate a sequence issue. Error: {e}")
            return jsonify({
                'success': False, 
                'error': 'Database error: Please contact support. The SMS may have been sent but failed to log.'
            }), 500
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/patients/<int:patient_id>/generate-invite-password', methods=['POST'])
@optional_login_required
def generate_invite_password(patient_id):
    """Generate a temporary password for iOS app invite preview"""
    try:
        import secrets
        patient = Patient.query.get_or_404(patient_id)
        
        if not patient.email:
            return jsonify({'success': False, 'error': 'Patient must have an email address'}), 400
        
        # Generate a temporary password
        temp_password = secrets.token_urlsafe(12)  # 16 character random password
        
        return jsonify({
            'success': True,
            'temp_password': temp_password
        })
    except Exception as e:
        logger.error(f"Error generating password: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/patients/<int:patient_id>/send-ios-invite', methods=['POST'])
@optional_login_required
def send_ios_app_invite(patient_id):
    """Send iOS app invite to patient - creates account and sends SMS/email"""
    try:
        from werkzeug.security import generate_password_hash
        import secrets
        
        patient = Patient.query.get_or_404(patient_id)
        
        if not patient.email:
            return jsonify({'success': False, 'error': 'Patient must have an email address to receive invite'}), 400
        
        # Get request data
        data = request.json or {}
        send_methods = data.get('send_methods', ['email', 'sms'])  # Default to both
        temp_password = data.get('temp_password')
        
        # Generate password if not provided
        if not temp_password:
            temp_password = secrets.token_urlsafe(12)  # 16 character random password
        
        # Ensure PatientAuth table exists (create if it doesn't)
        try:
            # Try to create all tables (idempotent - won't recreate existing ones)
            db.create_all()
            logger.info("✅ Database tables verified/created")
        except Exception as e:
            logger.warning(f"Could not ensure PatientAuth table exists: {e}")
        
        # Check if PatientAuth already exists
        patient_auth = None
        try:
            patient_auth = PatientAuth.query.filter_by(patient_id=patient_id).first()
        except Exception as e:
            # Table might not exist - try to create it
            error_str = str(e).lower()
            if 'does not exist' in error_str or 'no such table' in error_str or 'relation' in error_str:
                logger.error(f"PatientAuth table does not exist: {e}")
                logger.info("Attempting to create PatientAuth table...")
                try:
                    # Try creating just the PatientAuth table
                    PatientAuth.__table__.create(db.engine, checkfirst=True)
                    logger.info("✅ PatientAuth table created")
                    patient_auth = None  # Will create new one below
                except Exception as create_error:
                    logger.error(f"Failed to create PatientAuth table: {create_error}")
                    return jsonify({
                        'success': False,
                        'error': 'Database table "patient_auth" does not exist. Please run this SQL on your database:\n\nCREATE TABLE patient_auth (id SERIAL PRIMARY KEY, patient_id INTEGER NOT NULL UNIQUE REFERENCES patients(id), auth_provider VARCHAR(20) NOT NULL, provider_user_id VARCHAR(200), email VARCHAR(120), password_hash VARCHAR(200), refresh_token VARCHAR(500), token_expires_at TIMESTAMP, is_active BOOLEAN DEFAULT TRUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);'
                    }), 500
            else:
                # Some other database error
                logger.error(f"Database error querying PatientAuth: {e}")
                return jsonify({
                    'success': False,
                    'error': f'Database error: {str(e)}'
                }), 500
        
        if patient_auth:
            # Update existing auth with new password
            patient_auth.set_password(temp_password)
            patient_auth.is_active = True
            patient_auth.auth_provider = 'email'
            patient_auth.email = patient.email
        else:
            # Create new PatientAuth
            patient_auth = PatientAuth(
                patient_id=patient_id,
                auth_provider='email',
                email=patient.email,
                is_active=True
            )
            patient_auth.set_password(temp_password)
            db.session.add(patient_auth)
        
        try:
            db.session.commit()
            logger.info(f"✅ PatientAuth record {'updated' if patient_auth else 'created'} for patient {patient_id}")
        except Exception as e:
            logger.error(f"Database commit failed: {e}", exc_info=True)
            db.session.rollback()
            error_str = str(e).lower()
            if 'does not exist' in error_str or 'no such table' in error_str or 'relation' in error_str:
                return jsonify({
                    'success': False,
                    'error': 'Database table "patient_auth" does not exist. Please create it using the SQL in DATABASE_MIGRATION_PATIENT_AUTH.md'
                }), 500
            else:
                return jsonify({
                    'success': False,
                    'error': f'Database error: {str(e)}'
                }), 500
        
        # Prepare invite message
        app_store_url = "https://apps.apple.com/app/capturecare"  # Update with actual App Store URL when published
        
        # Plain text message for SMS
        message = f"""Hi {patient.first_name}, 

You've been invited to use the CaptureCare patient app! 

Download the app and sign in with:
Email: {patient.email}
Password: {temp_password}

You can change your password after signing in.

Download: {app_store_url}

- CaptureCare Team"""
        
        # Send SMS if requested and phone number available
        sms_sent = False
        sms_error = None
        if 'sms' in send_methods and (patient.mobile or patient.phone):
            try:
                from .notification_service import NotificationService
                notif_service = NotificationService()
                phone = patient.mobile or patient.phone
                sms_message = f"CaptureCare App Invite: Download the app and sign in with email {patient.email} and password {temp_password}. Change password after login."
                sms_result = notif_service.send_sms(
                    phone,
                    sms_message,
                    patient_id=patient_id,
                    user_id=current_user.id if current_user.is_authenticated else None,
                    log_correspondence=True
                )
                sms_sent = sms_result.get('success', False)
                if not sms_sent:
                    sms_error = sms_result.get('error', 'SMS service not configured or failed')
                    logger.warning(f"SMS invite failed for patient {patient_id}: {sms_error}")
            except Exception as e:
                sms_error = str(e)
                logger.error(f"Could not send SMS invite: {e}", exc_info=True)
        
        # Send email if requested
        email_sent = False
        email_error = None
        if 'email' in send_methods:
            try:
                # Use NotificationService which handles email sending properly
                from .notification_service import NotificationService
                notif_service = NotificationService()
                
                # Render branded HTML template
                from datetime import datetime
                try:
                    body_html = render_template('emails/ios_app_invite.html', 
                                              patient=patient, 
                                              temp_password=temp_password,
                                              app_store_url=app_store_url,
                                              current_year=datetime.now().year)
                    logger.info(f"✅ iOS app invite email template rendered successfully")
                except Exception as template_error:
                    logger.error(f"Error rendering iOS app invite template: {template_error}", exc_info=True)
                    # Fallback to simple HTML
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
        .credentials-box {{ background-color: #f8f9fa; border-left: 4px solid #00698f; padding: 20px; margin: 25px 0; }}
        .download-button {{
            display: inline-block;
            background-color: #00698f;
            color: #ffffff !important;
            padding: 16px 32px;
            text-decoration: none;
            border-radius: 6px;
            font-size: 18px;
            font-weight: bold;
            margin: 20px 0;
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <div class="logo">CaptureCare®</div>
            <p>Humanising Digital Health</p>
        </div>
        <h1>Welcome to CaptureCare Patient App</h1>
        <p>Hello {patient.first_name},</p>
        <p>You've been invited to use the CaptureCare patient app!</p>
        <div class="credentials-box">
            <p><strong>Email:</strong> {patient.email}</p>
            <p><strong>Password:</strong> {temp_password}</p>
        </div>
        <div style="text-align: center;">
            <a href="{app_store_url}" class="download-button" style="color: #ffffff; text-decoration: none;">📱 DOWNLOAD THE APP</a>
        </div>
        <p style="font-size: 14px; color: #666;">Please change your password after signing in.</p>
    </div>
</body>
</html>
"""
                
                email_sent = notif_service.send_email(
                    to_email=patient.email,
                    subject="Welcome to CaptureCare Patient App",
                    body_html=body_html,
                    body_text=message,
                    patient_id=patient_id,
                    user_id=current_user.id if current_user.is_authenticated else None,
                    log_correspondence=True
                )
                
                if not email_sent:
                    email_error = "Email service not configured or failed"
                    logger.warning(f"Email invite failed for patient {patient_id}: {email_error}")
            except Exception as e:
                email_error = str(e)
                logger.error(f"Could not send email invite: {e}", exc_info=True)
        
        if sms_sent or email_sent:
            # At least one method succeeded - account is created, return success
            error_details = []
            if 'email' in send_methods and not email_sent:
                error_details.append(f"Email failed: {email_error or 'Email service not configured'}")
            if 'sms' in send_methods and not sms_sent:
                error_details.append(f"SMS failed: {sms_error or 'SMS service not configured'}")
            
            return jsonify({
                'success': True,
                'message': 'Invite sent successfully',
                'email_sent': email_sent,
                'sms_sent': sms_sent,
                'temp_password': temp_password,  # Include for display purposes
                'warnings': error_details if error_details else None
            })
        else:
            # Both methods failed - provide detailed error
            error_msg = 'Could not send invite via SMS or email.'
            if 'email' in send_methods and email_error:
                error_msg += f' Email: {email_error}.'
            if 'sms' in send_methods and sms_error:
                error_msg += f' SMS: {sms_error}.'
            if not error_msg.endswith('.'):
                error_msg += ' Please check patient contact information and service configuration.'
            
            return jsonify({
                'success': False,
                'error': error_msg,
                'email_error': email_error,
                'sms_error': sms_error
            }), 400
            
    except Exception as e:
        logger.error(f"Error sending iOS app invite: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/patients/<int:patient_id>/initiate-call', methods=['POST'])
@optional_login_required
def initiate_patient_call(patient_id):
    """Initiate outbound call to patient via Twilio"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        data = request.json
        
        phone = data.get('phone')
        
        if not phone:
            return jsonify({'success': False, 'error': 'Phone number is required'}), 400
        
        # Initiate call using notification service
        from .notification_service import NotificationService
        notif_service = NotificationService()
        
        result = notif_service.initiate_call(
            to_phone=phone,
            patient_id=patient_id,
            user_id=current_user.id
        )
        
        if result.get('success'):
            return jsonify({
                'success': True, 
                'message': 'Call initiated successfully',
                'call_sid': result.get('call_sid'),
                'status': result.get('status', 'queued')
            })
        else:
            return jsonify({
                'success': False, 
                'error': result.get('error', 'Failed to initiate call')
            }), 400
    except Exception as e:
        logger.error(f"Error initiating call: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/patients/<int:patient_id>/end-call', methods=['POST'])
@optional_login_required
def end_patient_call(patient_id):
    """Terminate the call in Twilio and save call notes and duration"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        data = request.json
        
        call_sid = data.get('call_sid')
        duration = data.get('duration', 0)
        notes = data.get('notes', '')
        
        if not call_sid:
            return jsonify({'success': False, 'error': 'Call SID is required'}), 400
        
        # First, terminate the call in Twilio
        try:
            from .notification_service import NotificationService
            notif_service = NotificationService()
            
            if notif_service.twilio_configured:
                # Fetch the call and update its status to 'completed' to hang it up
                call = notif_service.twilio_client.calls(call_sid).fetch()
                
                # Only update if call is still active (not already completed/canceled)
                if call.status in ['queued', 'ringing', 'in-progress', 'initiated']:
                    logger.info(f"📞 Terminating call {call_sid} (current status: {call.status})")
                    # Update call status to 'completed' to hang up
                    call.update(status='completed')
                    logger.info(f"✅ Call {call_sid} terminated successfully")
                else:
                    logger.info(f"📞 Call {call_sid} already ended (status: {call.status})")
            else:
                logger.warning(f"⚠️  Twilio not configured, cannot terminate call {call_sid}")
        except Exception as twilio_error:
            logger.error(f"❌ Error terminating call in Twilio: {twilio_error}")
            # Continue anyway - we'll still save the notes
        
        # Find the correspondence record by call_sid (external_id)
        correspondence = PatientCorrespondence.query.filter_by(
            patient_id=patient_id,
            channel='voice',
            external_id=call_sid
        ).first()
        
        if correspondence:
            # Update with notes and duration
            if notes:
                correspondence.body = notes
            correspondence.call_duration = duration
            correspondence.status = 'completed'
            db.session.commit()
            logger.info(f"✅ Updated call record with duration {duration}s and notes for patient {patient_id}")
            
            return jsonify({
                'success': True,
                'message': 'Call terminated and notes saved'
            })
        else:
            # Correspondence record not found - still return success if we terminated the call
            logger.warning(f"⚠️  Call record not found for SID: {call_sid}, but call was terminated")
            return jsonify({
                'success': True,
                'message': 'Call terminated (correspondence record not found)'
            })
    except Exception as e:
        logger.error(f"Error ending call: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/patients/<int:patient_id>/call-status/<call_sid>', methods=['GET'])
@optional_login_required
def get_call_status(patient_id, call_sid):
    """Get current status of an active call"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        
        # Get Twilio client
        from .notification_service import NotificationService
        notif_service = NotificationService()
        
        if not notif_service.twilio_configured:
            return jsonify({'success': False, 'error': 'Twilio not configured'}), 400
        
        try:
            # Fetch call status from Twilio
            call = notif_service.twilio_client.calls(call_sid).fetch()
            
            return jsonify({
                'success': True,
                'status': call.status,
                'duration': call.duration if call.duration else 0,
                'from': call.from_,
                'to': call.to
            })
        except Exception as e:
            logger.error(f"Error fetching call status: {e}")
            return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error getting call status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/patients/<int:patient_id>/video-token', methods=['POST'])
@optional_login_required
def generate_video_token(patient_id):
    """Generate Twilio Video access token for practitioner"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        
        # Get optional room_name from request body
        data = request.get_json() or {}
        existing_room_name = data.get('room_name')
        
        # Get credentials - Prioritize Secret Manager (Cloud) over .env file (local)
        # Only reload .env file if NOT using Secret Manager (local development)
        use_secret_manager = os.getenv('USE_SECRET_MANAGER', 'False').lower() == 'true'
        if not use_secret_manager:
            from dotenv import load_dotenv
            env_file_path = os.path.join(os.path.dirname(__file__), 'capturecare.env')
            if os.path.exists(env_file_path):
                load_dotenv(env_file_path, override=True)
        
        # Get credentials from environment (most up-to-date)
        # Priority: os.getenv (Secret Manager or .env) > app.config
        account_sid = os.getenv('TWILIO_ACCOUNT_SID', '') or app.config.get('TWILIO_ACCOUNT_SID', '')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN', '') or app.config.get('TWILIO_AUTH_TOKEN', '')
        api_key_sid = os.getenv('TWILIO_API_KEY_SID', '') or app.config.get('TWILIO_API_KEY_SID', '')
        api_key_secret = os.getenv('TWILIO_API_KEY_SECRET', '') or app.config.get('TWILIO_API_KEY_SECRET', '')
        
        # Strip whitespace from credentials
        account_sid = account_sid.strip() if account_sid else ''
        auth_token = auth_token.strip() if auth_token else ''
        api_key_sid = api_key_sid.strip() if api_key_sid else ''
        api_key_secret = api_key_secret.strip() if api_key_secret else ''
        
        logger.info(f"📹 Video token request:")
        logger.info(f"   Account SID: {'✅ ' + account_sid[:15] + '...' if account_sid else '❌ MISSING'}")
        logger.info(f"   Auth Token: {'✅ ' + auth_token[:10] + '...' if auth_token else '❌ MISSING'}")
        logger.info(f"   API Key SID: {'✅ ' + api_key_sid[:20] + '...' if api_key_sid else '❌ MISSING'}")
        logger.info(f"   API Key Secret: {'✅ ' + api_key_secret[:15] + '...' if api_key_secret else '❌ MISSING'}")
        
        # Validate API Key SID format
        if api_key_sid and not api_key_sid.startswith('SK'):
            logger.warning(f"⚠️  API Key SID doesn't start with 'SK': {api_key_sid[:20]}...")
        
        if not account_sid:
            return jsonify({
                'success': False,
                'error': 'Twilio Account SID not configured. Please add TWILIO_ACCOUNT_SID in Settings.'
            }), 400
        
        # PRIORITIZE API Keys if available (user added them to settings)
        use_api_keys = bool(api_key_sid and api_key_secret)
        
        if use_api_keys:
            logger.info(f"📹 Using Video API Keys (from Settings)")
        elif auth_token:
            logger.info(f"📹 Using Account SID + Auth Token (SMS credentials as fallback)")
        else:
            return jsonify({
                'success': False,
                'error': 'Twilio Video credentials not configured. Please add Video API Keys in Settings (Twilio Video section), or configure Account SID + Auth Token.'
            }), 400
        
        try:
            from twilio.jwt.access_token import AccessToken
            from twilio.jwt.access_token.grants import VideoGrant
            
            # Use existing room name if provided, otherwise generate new one
            if existing_room_name:
                room_name = existing_room_name
                logger.info(f"📹 Using existing room name: {room_name}")
            else:
                import uuid
                room_name = f"patient_{patient_id}_{uuid.uuid4().hex[:8]}"
                logger.info(f"📹 Generated new room name: {room_name}")
            
            # Create access token for practitioner
            identity = f"practitioner_{current_user.id if current_user.is_authenticated else 'anonymous'}"
            
            if use_api_keys:
                # Use Video API Keys (from Settings page)
                # AccessToken(account_sid, signing_key_sid, secret, identity=identity)
                # account_sid = Account SID (AC...) - The Twilio account
                # signing_key_sid = API Key SID (SK...) - Must belong to the same account
                # secret = API Key Secret - Must match the API Key SID
                # identity = user identity
                
                # Validate API Key format
                if not api_key_sid.startswith('SK'):
                    raise ValueError(f"API Key SID must start with 'SK', got: {api_key_sid[:20]}...")
                if not account_sid.startswith('AC'):
                    raise ValueError(f"Account SID must start with 'AC', got: {account_sid[:20]}...")
                
                # Generate Access Token according to Twilio documentation
                # AccessToken(account_sid, signing_key_sid, secret, identity=identity)
                # When using API Keys:
                #   - account_sid = Account SID (AC...) - becomes 'sub' (subject) in JWT
                #   - signing_key_sid = API Key SID (SK...) - becomes 'iss' (issuer) in JWT
                #   - secret = API Key Secret
                #   - identity = user identity
                logger.info(f"📹 Creating AccessToken with API Keys:")
                logger.info(f"   Account SID (subject): {account_sid}")
                logger.info(f"   API Key SID (issuer): {api_key_sid[:20]}...")
                logger.info(f"   Identity: {identity}")
                
                token = AccessToken(account_sid, api_key_sid, api_key_secret, identity=identity)
                logger.info(f"📹 ✅ AccessToken created successfully")
            else:
                # Fallback: Use Account SID + Auth Token (same credentials as SMS)
                # When using Auth Token, Account SID is used as both account_sid and signing_key_sid
                token = AccessToken(account_sid, account_sid, auth_token, identity=identity)
                logger.info(f"📹 Generated token using Account SID + Auth Token")
            
            # Grant access to video room
            video_grant = VideoGrant(room=room_name)
            token.add_grant(video_grant)
            
            # Token expires in 1 hour
            token.ttl = 3600
            
            # Generate JWT token
            jwt_token = token.to_jwt()
            
            # Get public base URL for patient join link
            base_url = app.config.get('BASE_URL', '') or os.getenv('BASE_URL', '') or os.getenv('PUBLIC_URL', '')
            if not base_url:
                # Fallback: try to construct from request (but warn if localhost)
                base_url = request.host_url.rstrip('/')
                if '127.0.0.1' in base_url or 'localhost' in base_url:
                    logger.warning("⚠️ BASE_URL not configured - patient links will use localhost and won't work for external patients!")
                    logger.warning("⚠️ Set BASE_URL environment variable to your public URL (e.g., ngrok URL or domain)")
            
            # Build patient join URL
            patient_join_url = f"{base_url}/video-room/{room_name}"
            
            # Note: We're using ad-hoc rooms (recommended by Twilio)
            # The room will be created automatically when the first participant connects
            # This is better for scaling than REST API room creation
            logger.info(f"📹 Using ad-hoc room creation (room created on first participant join)")
            logger.info(f"📹 Generated video token for room: {room_name}, identity: {identity}")
            logger.info(f"📹 Patient join URL: {patient_join_url}")
            
            return jsonify({
                'success': True,
                'token': jwt_token,
                'room_name': room_name,
                'patient_join_url': patient_join_url,
                'base_url': base_url
            })
            
        except ImportError:
            return jsonify({
                'success': False,
                'error': 'Twilio Video SDK not properly installed. Run: pip install twilio'
            }), 500
        except ValueError as e:
            # Validation errors - provide clear guidance
            error_msg = str(e)
            logger.error(f"❌ Validation error: {error_msg}")
            return jsonify({
                'success': False,
                'error': error_msg,
                'help': 'Please check your Twilio Video API Keys in Settings. Ensure the API Key SID belongs to the same account as your Account SID.'
            }), 400
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Error generating video token: {error_msg}")
            
            # Provide helpful error messages
            if 'issuer' in error_msg.lower() or 'subject' in error_msg.lower() or 'invalid access token' in error_msg.lower():
                return jsonify({
                    'success': False,
                    'error': f'Invalid Access Token issuer/subject: {error_msg}',
                    'help': (
                        'This error means the API Key SID does not belong to the Account SID.\n\n'
                        'To fix:\n'
                        '1. Verify Account SID (AC...) is correct\n'
                        '2. Verify API Key SID (SK...) belongs to the same account\n'
                        '3. Check API Key Secret matches the API Key SID\n'
                        '4. Ensure both are from your live Twilio account (not test credentials)\n\n'
                        f'Current values:\n'
                        f'Account SID: {account_sid[:15]}...\n'
                        f'API Key SID: {api_key_sid[:20]}...'
                    )
                }), 400
            elif 'authentication' in error_msg.lower() or '401' in error_msg.lower() or 'unauthorized' in error_msg.lower():
                return jsonify({
                    'success': False,
                    'error': f'Authentication error: {error_msg}',
                    'help': 'The API Key SID and Secret do not match, or the API Key does not belong to the Account SID. Please verify your credentials in Settings.'
                }), 400
            else:
                return jsonify({
                    'success': False,
                    'error': f'Error generating video token: {error_msg}',
                    'help': 'Please check your Twilio Video credentials in Settings and ensure they are correct.'
                }), 400
            
    except Exception as e:
        logger.error(f"Error generating video token: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/patients/<int:patient_id>/log-video-call', methods=['POST'])
@optional_login_required
def log_video_call(patient_id):
    """Log completed video call to correspondence"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        data = request.json
        
        room_name = data.get('room_name')
        duration = data.get('duration', 0)
        
        if not room_name:
            return jsonify({'success': False, 'error': 'Room name is required'}), 400
        
        # Create correspondence record for video call
        correspondence = PatientCorrespondence(
            patient_id=patient_id,
            user_id=current_user.id,
            channel='video',
            direction='outbound',
            subject=f'Video Consultation',
            body=f'Video consultation via room: {room_name}',
            status='completed',
            call_duration=duration,
            external_id=room_name
        )
        
        db.session.add(correspondence)
        db.session.commit()
        
        logger.info(f"📹 Logged video call for patient {patient_id}, duration: {duration}s")
        
        return jsonify({
            'success': True,
            'message': 'Video call logged successfully'
        })
        
    except Exception as e:
        logger.error(f"Error logging video call: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/webhook/sms', methods=['POST'])
def webhook_receive_sms():
    """
    Twilio webhook endpoint to receive inbound SMS messages
    Configure this URL in your Twilio phone number settings:
    https://your-domain.repl.co/api/webhook/sms
    """
    from_phone = None
    webhook_log = None
    
    try:
        # Log the incoming request details for debugging
        logger.info(f"📨 SMS Webhook - Content-Type: {request.content_type}")
        logger.info(f"📨 SMS Webhook - Form data: {dict(request.form)}")
        logger.info(f"📨 SMS Webhook - JSON data: {request.get_json(silent=True)}")
        logger.info(f"📨 SMS Webhook - Raw data: {request.data}")
        
        # Try to get data from different possible formats
        if request.is_json:
            # JSON payload
            data = request.get_json()
            from_phone = data.get('From') or data.get('from') or data.get('from_phone')
            to_phone = data.get('To') or data.get('to') or data.get('to_phone')
            message_body = data.get('Body') or data.get('body') or data.get('message')
            message_sid = data.get('MessageSid') or data.get('message_sid') or data.get('sid')
            message_status = data.get('SmsStatus') or data.get('status')
            raw_data = data
        elif request.form.get('Payload'):
            # Make.com webhook format - data is nested in Payload JSON
            payload_str = request.form.get('Payload')
            payload_data = json.loads(payload_str)
            
            # Extract SMS data from nested structure
            params = payload_data.get('webhook', {}).get('request', {}).get('parameters', {})
            from_phone = params.get('From')
            to_phone = params.get('To')
            message_body = params.get('Body')
            message_sid = params.get('MessageSid')
            message_status = params.get('SmsStatus')
            raw_data = payload_data
        else:
            # Form data (standard Twilio format)
            from_phone = request.form.get('From')
            to_phone = request.form.get('To')
            message_body = request.form.get('Body')
            message_sid = request.form.get('MessageSid')
            message_status = request.form.get('SmsStatus')
            raw_data = dict(request.form)
        
        logger.info(f"📨 Received SMS webhook from {from_phone}: {message_body}")
        
        # Normalize phone number for Australian format
        # Converts +61417518940 to 0417518940 for database matching
        def normalize_phone(phone):
            if not phone:
                return None
            # Strip ALL non-numeric characters (spaces, dashes, unicode, etc.)
            import re
            phone = re.sub(r'\D', '', phone)  # Keep only digits
            # Convert 61... to 0... (Australian format)
            if phone.startswith('61') and len(phone) == 11:
                phone = '0' + phone[2:]
            return phone
        
        # Try to find patient by phone number
        patient = None
        patient_matched = False
        patient_name = None
        
        if from_phone:
            normalized_from = normalize_phone(from_phone)
            logger.info(f"🔍 Normalized phone: {from_phone} → {normalized_from}")
            
            # Get all patients and check normalized phone numbers
            all_patients = Patient.query.all()
            logger.info(f"🔍 Checking {len(all_patients)} patients for phone match")
            
            for p in all_patients:
                normalized_mobile = normalize_phone(p.mobile)
                normalized_phone = normalize_phone(p.phone)
                
                logger.info(f"  Patient {p.first_name} {p.last_name}: mobile={p.mobile} → {normalized_mobile}, phone={p.phone} → {normalized_phone}")
                
                if normalized_from == normalized_mobile or normalized_from == normalized_phone:
                    patient = p
                    patient_matched = True
                    patient_name = f"{p.first_name} {p.last_name}"
                    logger.info(f"✅ Matched patient: {patient_name} (ID: {patient.id})")
                    break
            
            if not patient:
                logger.warning(f"⚠️  No patient found for normalized number: {normalized_from}")
        
        if patient:
            # Log the inbound SMS to correspondence
            correspondence = PatientCorrespondence(
                patient_id=patient.id,
                user_id=None,  # Inbound message has no user
                channel='sms',
                direction='inbound',
                body=message_body,
                sender_phone=from_phone,
                recipient_phone=to_phone,
                status=message_status,
                external_id=message_sid,
                sent_at=datetime.utcnow()
            )
            db.session.add(correspondence)
            
            # Log successful webhook
            webhook_log = CommunicationWebhookLog(
                webhook_type='sms',
                from_phone=from_phone,
                to_phone=to_phone,
                message_body=message_body,
                success=True,
                patient_matched=True,
                patient_id=patient.id,
                patient_name=patient_name,
                external_id=message_sid,
                raw_request_data=json.dumps(raw_data)
            )
            db.session.add(webhook_log)
            db.session.commit()
            
            logger.info(f"✅ Logged inbound SMS from patient {patient.id}")
            # Return TwiML XML response to Twilio
            return Response(
                '<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                mimetype='text/xml'
            )
        else:
            # Patient not found - still log the webhook attempt
            webhook_log = CommunicationWebhookLog(
                webhook_type='sms',
                from_phone=from_phone,
                to_phone=to_phone,
                message_body=message_body,
                success=False,
                patient_matched=False,
                error_message=f"No patient found with phone number: {from_phone}",
                external_id=message_sid,
                raw_request_data=json.dumps(raw_data)
            )
            db.session.add(webhook_log)
            db.session.commit()
            
            logger.warning(f"⚠️  Received SMS from unknown number: {from_phone}")
            # Return TwiML XML response to Twilio
            return Response(
                '<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                mimetype='text/xml'
            )
            
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error processing inbound SMS: {error_msg}")
        
        # Log the failed webhook attempt
        try:
            webhook_log = CommunicationWebhookLog(
                webhook_type='sms',
                from_phone=from_phone,
                to_phone=request.form.get('To') if request.form else None,
                message_body=request.form.get('Body') if request.form else None,
                success=False,
                patient_matched=False,
                error_message=error_msg,
                external_id=request.form.get('MessageSid') if request.form else None,
                raw_request_data=json.dumps(dict(request.form)) if request.form else None
            )
            db.session.add(webhook_log)
            db.session.commit()
        except:
            pass  # Don't let logging errors break the webhook
        
        # Return TwiML XML response to Twilio even on error
        return Response(
            '<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            mimetype='text/xml'
        )

@app.route('/api/webhook/call-status', methods=['POST'])
def call_status_webhook():
    """
    Twilio webhook endpoint for call status updates
    Fetches call summary when call completes and saves to patient notes
    """
    try:
        call_sid = request.form.get('CallSid')
        call_status = request.form.get('CallStatus')
        call_duration = request.form.get('CallDuration')
        
        logger.info(f"📞 Call status update - CallSid: {call_sid}, Status: {call_status}")
        
        # When call completes, fetch summary and save to notes
        if call_status == 'completed' and call_sid:
            # Find patient by call SID in correspondence
            correspondence = PatientCorrespondence.query.filter_by(call_sid=call_sid).first()
            
            if correspondence and correspondence.patient_id:
                # Wait a bit for summary to be available (can take up to 30 minutes, but partial available in ~10 min)
                import time
                import threading
                
                def fetch_summary_later():
                    """Fetch summary after a delay"""
                    time.sleep(10)  # Wait 10 seconds for partial summary to be available
                    
                    try:
                        # Fetch and save call summary
                        from .notification_service import NotificationService
                        notif_service = NotificationService()
                        notif_service.save_call_summary_to_notes(
                            patient_id=correspondence.patient_id,
                            call_sid=call_sid,
                            user_id=correspondence.user_id
                        )
                        logger.info(f"✅ Processed call summary for {call_sid}")
                    except Exception as e:
                        logger.error(f"❌ Error fetching call summary: {e}")
                
                # Run in background thread so webhook responds quickly
                threading.Thread(target=fetch_summary_later, daemon=True).start()
        
        return jsonify({'success': True}), 200
        
    except Exception as e:
        logger.error(f"❌ Error in call status webhook: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/webhook/call-recording', methods=['POST'])
def call_recording_webhook():
    """
    Twilio webhook endpoint for call recording status updates
    """
    try:
        call_sid = request.form.get('CallSid')
        recording_status = request.form.get('RecordingStatus')
        recording_url = request.form.get('RecordingUrl')
        recording_sid = request.form.get('RecordingSid')
        
        logger.info(f"📼 Recording status update - CallSid: {call_sid}, Status: {recording_status}")
        
        # Update correspondence with recording URL if available
        if recording_url and call_sid:
            correspondence = PatientCorrespondence.query.filter_by(call_sid=call_sid).first()
            if correspondence:
                correspondence.recording_url = recording_url
                db.session.commit()
                logger.info(f"✅ Updated recording URL for call {call_sid}")
        
        return jsonify({'success': True}), 200
        
    except Exception as e:
        logger.error(f"❌ Error in call recording webhook: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/webhook/call-transcription', methods=['POST'])
def webhook_receive_call_transcription():
    """
    Twilio webhook endpoint to receive call transcriptions
    Configure this URL in your Twilio number's Voice settings under "Record Call" options
    https://your-domain.repl.co/api/webhook/call-transcription
    
    Twilio sends transcription data after a call recording is transcribed.
    """
    call_from = None
    webhook_log = None
    
    try:
        # Validate Twilio signature for security
        if Config.TWILIO_AUTH_TOKEN:
            from twilio.request_validator import RequestValidator
            validator = RequestValidator(Config.TWILIO_AUTH_TOKEN)
            
            # Get the URL that Twilio hit (including query params if any)
            url = request.url
            
            # Get the signature from request headers
            signature = request.headers.get('X-Twilio-Signature', '')
            
            # Get all POST parameters
            post_vars = request.form.to_dict()
            
            # Validate the request came from Twilio
            if not validator.validate(url, post_vars, signature):
                logger.warning(f"⚠️  Invalid Twilio signature for call transcription webhook")
                return jsonify({'success': False, 'error': 'Invalid signature'}), 403
        
        # Get data from Twilio webhook
        call_sid = request.form.get('CallSid')
        call_from = request.form.get('From')
        call_to = request.form.get('To')
        call_status = request.form.get('CallStatus')
        call_duration = request.form.get('CallDuration')
        recording_url = request.form.get('RecordingUrl')
        recording_sid = request.form.get('RecordingSid')
        transcription_text = request.form.get('TranscriptionText')
        transcription_sid = request.form.get('TranscriptionSid')
        transcription_status = request.form.get('TranscriptionStatus')
        
        # Store raw request data for debugging
        raw_data = dict(request.form)
        
        logger.info(f"📞 Received call transcription webhook - CallSid: {call_sid}, From: {call_from}")
        
        # Determine call direction based on Twilio phone number
        call_direction = 'inbound'
        if call_from and call_from == Config.TWILIO_PHONE_NUMBER:
            call_direction = 'outbound'
            # For outbound, we called TO the patient, so swap from/to
            patient_phone = call_to
        else:
            # For inbound, patient called FROM their number
            patient_phone = call_from
        
        # Try to find patient by phone number
        patient = None
        patient_matched = False
        patient_name = None
        
        if patient_phone:
            # Try mobile first, then phone
            patient = Patient.query.filter(
                (Patient.mobile == patient_phone) | (Patient.phone == patient_phone)
            ).first()
            
            if patient:
                patient_matched = True
                patient_name = f"{patient.first_name} {patient.last_name}"
        
        if patient:
            # Log the call to correspondence
            correspondence = PatientCorrespondence(
                patient_id=patient.id,
                user_id=None,  # We don't know which user made/received the call
                channel='voice',
                direction=call_direction,
                body=transcription_text or f"Voice call - {call_duration}s",
                sender_phone=call_from if call_direction == 'inbound' else None,
                recipient_phone=call_to if call_direction == 'outbound' else None,
                call_sid=call_sid,
                call_duration=int(call_duration) if call_duration else None,
                recording_url=recording_url,
                transcription_status=transcription_status or 'completed',
                status=call_status or 'completed',
                external_id=call_sid,
                sent_at=datetime.utcnow()
            )
            db.session.add(correspondence)
            
            # Log successful webhook
            webhook_log = CommunicationWebhookLog(
                webhook_type='voice',
                from_phone=call_from,
                to_phone=call_to,
                message_body=transcription_text or f"Call recording ({call_duration}s)",
                success=True,
                patient_matched=True,
                patient_id=patient.id,
                patient_name=patient_name,
                external_id=call_sid,
                raw_request_data=json.dumps(raw_data)
            )
            db.session.add(webhook_log)
            db.session.commit()
            
            logger.info(f"✅ Logged call transcription for patient {patient.id}")
            return jsonify({'success': True, 'message': 'Call transcription logged'}), 200
        else:
            # Patient not found - still log the webhook attempt
            webhook_log = CommunicationWebhookLog(
                webhook_type='voice',
                from_phone=call_from,
                to_phone=call_to,
                message_body=transcription_text or f"Call recording ({call_duration}s)",
                success=False,
                patient_matched=False,
                error_message=f"No patient found with phone number: {patient_phone}",
                external_id=call_sid,
                raw_request_data=json.dumps(raw_data)
            )
            db.session.add(webhook_log)
            db.session.commit()
            
            logger.warning(f"⚠️  Received call from unknown number: {patient_phone}")
            return jsonify({'success': False, 'error': 'Patient not found'}), 200
            
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error processing call transcription: {error_msg}")
        
        # Log the failed webhook attempt
        try:
            webhook_log = CommunicationWebhookLog(
                webhook_type='voice',
                from_phone=call_from,
                to_phone=request.form.get('To') if request.form else None,
                message_body=request.form.get('TranscriptionText') if request.form else None,
                success=False,
                patient_matched=False,
                error_message=error_msg,
                external_id=request.form.get('CallSid') if request.form else None,
                raw_request_data=json.dumps(dict(request.form)) if request.form else None
            )
            db.session.add(webhook_log)
            db.session.commit()
        except:
            pass  # Don't let logging errors break the webhook
        
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/webhook/email', methods=['POST'])
def webhook_receive_email():
    """
    Email webhook endpoint to receive forwarded patient emails
    Forward emails to this URL (POST with JSON):
    https://your-domain.repl.co/api/webhook/email
    
    Expected JSON format:
    {
        "from_email": "patient@example.com",
        "to_email": "clinic@example.com", 
        "subject": "Email subject",
        "body": "Email body text",
        "html_body": "HTML email body (optional)",
        "message_id": "unique-message-id"
    }
    """
    try:
        data = request.get_json()
        
        from_email = data.get('from_email', '')
        to_email = data.get('to_email', '')
        subject = data.get('subject', '')
        body = data.get('body') or data.get('html_body', '')
        message_id = data.get('message_id', '')
        
        logger.info(f"📧 Received email from {from_email}: {subject}")
        
        # Try to find patient by email address
        patient = None
        if from_email:
            patient = Patient.query.filter(
                Patient.email.ilike(from_email)
            ).first()
        
        if patient:
            # Log the inbound email to correspondence
            correspondence = PatientCorrespondence(
                patient_id=patient.id,
                user_id=None,  # Inbound message has no user
                channel='email',
                direction='inbound',
                subject=subject,
                body=body,
                sender_email=from_email,
                recipient_email=to_email,
                status='received',
                external_id=message_id,
                sent_at=datetime.utcnow()
            )
            db.session.add(correspondence)
            db.session.commit()
            
            logger.info(f"✅ Logged inbound email from patient {patient.id}")
            return jsonify({'success': True, 'message': 'Email logged', 'patient_id': patient.id}), 200
        else:
            # Patient not found - log it but don't create correspondence
            logger.warning(f"⚠️  Received email from unknown address: {from_email}")
            return jsonify({'success': False, 'message': 'Patient not found', 'email': from_email}), 404
            
    except Exception as e:
        logger.error(f"❌ Error processing inbound email: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/correspondence/all', methods=['GET'])
@optional_login_required
def get_all_correspondence():
    """Get all correspondence across all patients with filtering"""
    try:
        # Get query parameters
        channel = request.args.get('channel')  # 'sms' or 'email'
        direction = request.args.get('direction')  # 'inbound' or 'outbound'
        workflow_status = request.args.get('workflow_status')  # 'pending', 'completed', etc.
        patient_search = request.args.get('patient_search', '')
        patient_filter = request.args.get('patient_filter', 'my_patients')  # 'my_patients' or 'all'
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        
        # Build query
        query = PatientCorrespondence.query.filter_by(is_deleted=False)
        
        # Check if user is a practitioner and filter by their patients by default
        is_practitioner = current_user.is_authenticated and not current_user.is_admin and current_user.role in ['practitioner', 'nurse']
        
        # Apply practitioner patient filter
        if is_practitioner and patient_filter == 'my_patients':
            # Get patient IDs who have appointments with this practitioner
            patient_ids = db.session.query(Appointment.patient_id).filter(
                Appointment.practitioner_id == current_user.id
            ).distinct().all()
            patient_ids = [pid[0] for pid in patient_ids]
            
            if patient_ids:
                query = query.filter(PatientCorrespondence.patient_id.in_(patient_ids))
            else:
                # No patients, return empty result
                return jsonify({
                    'success': True,
                    'correspondence': [],
                    'total': 0,
                    'limit': limit,
                    'offset': offset
                })
        
        # Apply filters
        if channel:
            query = query.filter_by(channel=channel)
        if direction:
            query = query.filter_by(direction=direction)
        if workflow_status:
            query = query.filter_by(workflow_status=workflow_status)
        
        # Patient search filter
        if patient_search:
            query = query.join(Patient).filter(
                (Patient.first_name.ilike(f'%{patient_search}%')) |
                (Patient.last_name.ilike(f'%{patient_search}%')) |
                (Patient.email.ilike(f'%{patient_search}%'))
            )
        
        # Get total count
        total = query.count()
        
        # Get correspondence with pagination
        correspondence = query.order_by(
            PatientCorrespondence.sent_at.desc()
        ).limit(limit).offset(offset).all()
        
        # Format response
        results = []
        for c in correspondence:
            patient = Patient.query.get(c.patient_id)
            results.append({
                'id': c.id,
                'patient_id': c.patient_id,
                'patient_name': f"{patient.first_name} {patient.last_name}" if patient else "Unknown",
                'channel': c.channel,
                'direction': c.direction,
                'subject': c.subject,
                'body': c.body,
                'recipient_email': c.recipient_email,
                'recipient_phone': c.recipient_phone,
                'sender_email': c.sender_email,
                'sender_phone': c.sender_phone,
                'status': c.status,
                'workflow_status': c.workflow_status,
                'external_id': c.external_id,
                'error_message': c.error_message,
                'sent_at': format_local(c.sent_at, '%d/%m/%Y, %H:%M:%S') if c.sent_at else None,
                'delivered_at': format_local(c.delivered_at, '%d/%m/%Y, %H:%M:%S') if c.delivered_at else None
            })
        
        return jsonify({
            'success': True,
            'correspondence': results,
            'total': total,
            'limit': limit,
            'offset': offset
        })
    except Exception as e:
        logger.error(f"Error fetching all correspondence: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/correspondence/<int:correspondence_id>/workflow-status', methods=['PUT'])
@optional_login_required
def update_correspondence_workflow_status(correspondence_id):
    """Update the workflow status of a correspondence"""
    try:
        data = request.get_json()
        new_status = data.get('workflow_status')
        
        # Validate status
        valid_statuses = ['pending', 'completed', 'follow_up_needed', 'no_action_required']
        if new_status not in valid_statuses:
            return jsonify({'success': False, 'error': 'Invalid workflow status'}), 400
        
        # Get correspondence
        correspondence = PatientCorrespondence.query.get(correspondence_id)
        if not correspondence:
            return jsonify({'success': False, 'error': 'Correspondence not found'}), 404
        
        # Update status
        correspondence.workflow_status = new_status
        db.session.commit()
        
        logger.info(f"✅ Updated correspondence {correspondence_id} workflow status to {new_status}")
        
        return jsonify({
            'success': True,
            'message': 'Workflow status updated',
            'workflow_status': new_status
        })
        
    except Exception as e:
        logger.error(f"Error updating workflow status: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/communication-webhook-logs', methods=['GET'])
@optional_login_required
def get_communication_webhook_logs():
    """Get recent communication webhook logs (SMS/Email) for debugging"""
    try:
        # Get query parameters
        webhook_type = request.args.get('type')  # 'sms' or 'email'
        limit = int(request.args.get('limit', 50))
        
        # Build query
        query = CommunicationWebhookLog.query
        
        # Filter by type if specified
        if webhook_type:
            query = query.filter_by(webhook_type=webhook_type)
        
        # Get logs ordered by most recent first
        logs = query.order_by(CommunicationWebhookLog.created_at.desc()).limit(limit).all()
        
        # Format response
        results = []
        for log in logs:
            results.append({
                'id': log.id,
                'webhook_type': log.webhook_type,
                'from_phone': log.from_phone,
                'to_phone': log.to_phone,
                'from_email': log.from_email,
                'to_email': log.to_email,
                'message_body': log.message_body,
                'message_subject': log.message_subject,
                'success': log.success,
                'patient_matched': log.patient_matched,
                'patient_id': log.patient_id,
                'patient_name': log.patient_name,
                'error_message': log.error_message,
                'external_id': log.external_id,
                'raw_request_data': log.raw_request_data,
                'created_at': log.created_at.isoformat() if log.created_at else None
            })
        
        return jsonify({
            'success': True,
            'logs': results,
            'count': len(results)
        })
    except Exception as e:
        logger.error(f"Error fetching webhook logs: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/test-twilio-video', methods=['POST'])
@optional_login_required
def test_twilio_video_credentials():
    """Test Twilio Video credentials (API Keys or Account SID + Auth Token)"""
    try:
        data = request.json
        account_sid = data.get('account_sid', '').strip()
        auth_token = data.get('auth_token', '').strip()
        api_key_sid = data.get('api_key_sid', '').strip()
        api_key_secret = data.get('api_key_secret', '').strip()
        
        if not account_sid:
            return jsonify({
                'success': False,
                'error': 'Account SID is required'
            }), 400
        
        try:
            from twilio.jwt.access_token import AccessToken
            from twilio.jwt.access_token.grants import VideoGrant
            
            # Try to generate a test token
            test_identity = 'test_user'
            use_api_keys = bool(api_key_sid and api_key_secret)
            
            if use_api_keys:
                # Test with API Keys
                token = AccessToken(account_sid, api_key_sid, api_key_secret, identity=test_identity)
                method = 'API Keys'
            elif auth_token:
                # Test with Account SID + Auth Token
                token = AccessToken(account_sid, account_sid, auth_token, identity=test_identity)
                method = 'Account SID + Auth Token (same as SMS)'
            else:
                return jsonify({
                    'success': False,
                    'error': 'Either API Keys or Auth Token is required',
                    'suggestion': 'Video can use your existing Account SID + Auth Token (same as SMS)'
                }), 400
            
            # Add video grant
            video_grant = VideoGrant(room='test_room')
            token.add_grant(video_grant)
            token.ttl = 60  # Short expiry for test
            
            # Generate token to verify it works
            jwt_token = token.to_jwt()
            
            return jsonify({
                'success': True,
                'message': f'Twilio Video credentials are valid! Successfully generated access token using {method}.',
                'method': method
            })
            
        except ImportError:
            return jsonify({
                'success': False,
                'error': 'Twilio library not installed',
                'suggestion': 'Install with: pip install twilio'
            }), 400
        except Exception as e:
            error_msg = str(e)
            if 'authentication' in error_msg.lower() or 'invalid' in error_msg.lower():
                return jsonify({
                    'success': False,
                    'error': f'Invalid credentials: {error_msg}',
                    'suggestion': 'Please check your API Key SID, API Key Secret, Account SID, and Auth Token'
                }), 400
            return jsonify({
                'success': False,
                'error': f'Twilio Video API error: {error_msg}',
                'suggestion': 'Verify your credentials are correct and have Video API access'
            }), 400
            
    except Exception as e:
        logger.error(f"Error testing Twilio Video credentials: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/test-twilio', methods=['POST'])
@optional_login_required
def test_twilio_credentials():
    """Test Twilio credentials without sending SMS"""
    try:
        data = request.json
        account_sid = data.get('account_sid', '').strip()
        auth_token = data.get('auth_token', '').strip()
        phone_number = data.get('phone_number', '').strip()
        
        # Validate inputs
        if not account_sid or not auth_token:
            return jsonify({
                'success': False, 
                'error': 'Account SID and Auth Token are required'
            }), 400
        
        # Check if Account SID looks valid
        if not account_sid.startswith('AC'):
            return jsonify({
                'success': False,
                'error': 'Invalid Account SID format',
                'suggestion': 'Account SID should start with "AC" (not "sk_" which is an API Key). Find your Account SID at console.twilio.com'
            }), 400
        
        # Try to create Twilio client and fetch account info
        from twilio.rest import Client
        
        try:
            client = Client(account_sid, auth_token)
            
            # Fetch account info to verify credentials
            account = client.api.accounts(account_sid).fetch()
            
            # Verify phone number if provided
            phone_validation = ""
            if phone_number:
                try:
                    # Check if phone number exists in account
                    incoming_phone = client.incoming_phone_numbers.list(
                        phone_number=phone_number,
                        limit=1
                    )
                    if incoming_phone:
                        phone_validation = f" Phone number {phone_number} verified."
                    else:
                        phone_validation = f" Warning: Phone number {phone_number} not found in your Twilio account."
                except Exception as pe:
                    phone_validation = f" Could not verify phone number: {str(pe)}"
            
            return jsonify({
                'success': True,
                'message': f'Twilio credentials are valid!{phone_validation}',
                'account_name': account.friendly_name or 'Twilio Account',
                'account_status': account.status
            })
            
        except Exception as e:
            error_msg = str(e)
            
            # Provide helpful error messages
            if 'authentication' in error_msg.lower() or 'unauthorized' in error_msg.lower():
                return jsonify({
                    'success': False,
                    'error': 'Authentication failed - Invalid Account SID or Auth Token',
                    'suggestion': 'Double-check your credentials at console.twilio.com. Make sure you\'re using the Auth Token (not an API Key).'
                }), 400
            elif 'Unable to create record' in error_msg:
                return jsonify({
                    'success': False,
                    'error': 'Invalid credentials',
                    'suggestion': 'Make sure Account SID starts with "AC" and Auth Token is correct. Get them from console.twilio.com.'
                }), 400
            else:
                return jsonify({
                    'success': False,
                    'error': f'Twilio API error: {error_msg}'
                }), 400
                
    except Exception as e:
        logger.error(f"Error testing Twilio credentials: {e}")
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}'
        }), 500

@app.route('/api/test-openai', methods=['POST'])
@optional_login_required
def test_openai_credentials():
    """Test OpenAI API credentials"""
    try:
        data = request.json
        api_key = data.get('api_key', '').strip()
        
        if not api_key:
            return jsonify({'success': False, 'error': 'API key is required'}), 400
        
        if not api_key.startswith('sk-'):
            return jsonify({'success': False, 'error': 'Invalid API key format. OpenAI keys start with "sk-"'}), 400
        
        import openai
        client = openai.OpenAI(api_key=api_key)
        
        # Make a simple test request
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=5
        )
        
        return jsonify({
            'success': True,
            'message': 'OpenAI API key is valid! Successfully connected to GPT-3.5-turbo.'
        })
        
    except Exception as e:
        error_msg = str(e)
        if 'authentication' in error_msg.lower() or 'api key' in error_msg.lower():
            return jsonify({'success': False, 'error': 'Invalid API key. Please check your OpenAI API key.'}), 400
        return jsonify({'success': False, 'error': f'OpenAI API error: {error_msg}'}), 400

@app.route('/api/test-xai', methods=['POST'])
@optional_login_required
def test_xai_credentials():
    """Test xAI (Grok) API credentials"""
    try:
        data = request.json
        api_key = data.get('api_key', '').strip()
        
        if not api_key:
            return jsonify({'success': False, 'error': 'API key is required'}), 400
        
        if not api_key.startswith('xai-'):
            return jsonify({'success': False, 'error': 'Invalid API key format. xAI keys start with "xai-"'}), 400
        
        import openai
        client = openai.OpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1"
        )
        
        # Make a simple test request with Grok 3 (latest stable model)
        response = client.chat.completions.create(
            model="grok-3",  # Latest Grok model (grok-beta was deprecated)
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=5
        )
        
        return jsonify({
            'success': True,
            'message': 'xAI API key is valid! Successfully connected to Grok.'
        })
        
    except Exception as e:
        error_msg = str(e)
        if 'authentication' in error_msg.lower() or 'api key' in error_msg.lower():
            return jsonify({'success': False, 'error': 'Invalid API key. Please check your xAI API key.'}), 400
        return jsonify({'success': False, 'error': f'xAI API error: {error_msg}'}), 400

@app.route('/api/test-cliniko', methods=['POST'])
@optional_login_required
def test_cliniko_credentials():
    """Test Cliniko API credentials"""
    try:
        data = request.json
        api_key = data.get('api_key', '').strip()
        shard = data.get('shard', 'au1').strip()
        
        if not api_key:
            return jsonify({'success': False, 'error': 'API key is required'}), 400
        
        if not shard:
            return jsonify({'success': False, 'error': 'Shard is required'}), 400
        
        # Test the Cliniko API by fetching user info
        from .patient_matcher import ClinikoIntegration
        cliniko_test = ClinikoIntegration(api_key, shard)
        
        # Try to get user info (this is a simple API call that will verify the credentials)
        import requests
        url = f"https://api.{shard}.cliniko.com/v1/users"
        headers = {
            'Authorization': f'Basic {api_key}',
            'Accept': 'application/json',
            'User-Agent': 'CaptureCare (support@capturecare.com)'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            user_count = len(data.get('users', []))
            return jsonify({
                'success': True,
                'message': f'Cliniko API key is valid! Connected to {shard} shard. Found {user_count} user(s).'
            })
        elif response.status_code == 401:
            return jsonify({'success': False, 'error': 'Invalid API key. Please check your Cliniko API key.'}), 400
        else:
            return jsonify({'success': False, 'error': f'Cliniko API returned status code {response.status_code}'}), 400
        
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'Request timed out. Please check your shard value.'}), 400
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'error': 'Could not connect to Cliniko API. Please check your shard value.'}), 400
    except Exception as e:
        error_msg = str(e)
        return jsonify({'success': False, 'error': f'Cliniko API error: {error_msg}'}), 400

@app.route('/api/test-heygen', methods=['POST'])
@optional_login_required
def test_heygen_credentials():
    """Test HeyGen API credentials"""
    try:
        data = request.json
        api_key = data.get('api_key', '').strip()
        
        if not api_key:
            return jsonify({'success': False, 'error': 'API key is required'}), 400
        
        import requests
        
        # Test by fetching avatars list
        headers = {'X-Api-Key': api_key}
        response = requests.get('https://api.heygen.com/v2/avatars', headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            avatar_count = len(data.get('data', {}).get('avatars', []))
            return jsonify({
                'success': True,
                'message': f'HeyGen API key is valid! Found {avatar_count} avatars available.'
            })
        elif response.status_code == 401:
            return jsonify({'success': False, 'error': 'Invalid API key. Please check your HeyGen API key.'}), 400
        else:
            return jsonify({'success': False, 'error': f'HeyGen API error: {response.text}'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': f'HeyGen API error: {str(e)}'}), 400

@app.route('/api/test-smtp', methods=['POST'])
@optional_login_required
def test_smtp_credentials():
    """Test SMTP/Email credentials"""
    try:
        data = request.json
        server = data.get('server', '').strip()
        port = data.get('port', '587')
        username = data.get('username', '').strip()
        password_raw = data.get('password', '').strip()
        from_email = data.get('from_email', '').strip()
        
        if not all([server, username, password_raw]):
            return jsonify({'success': False, 'error': 'Server, username, and password are required'}), 400
        
        # Fix: Clean password - replace non-breaking spaces with regular spaces
        # This handles Gmail app passwords and other passwords with special characters
        password = password_raw.replace('\xa0', ' ').replace('\u00a0', ' ').strip()
        
        import smtplib
        from email.mime.text import MIMEText
        
        logger.info(f"🧪 Testing SMTP connection to {server}:{port} as {username}")
        
        # Try to connect and authenticate
        smtp = smtplib.SMTP(server, int(port), timeout=30)
        smtp.starttls()
        logger.info(f"🔐 TLS started, attempting login...")
        smtp.login(username, password)
        logger.info(f"✅ SMTP authentication successful!")
        smtp.quit()
        
        return jsonify({
            'success': True,
            'message': f'SMTP connection successful! Connected to {server}:{port} and authenticated.'
        })
        
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"❌ SMTP Authentication failed: {e}")
        return jsonify({'success': False, 'error': 'Authentication failed. Check your username and password (use app password for Gmail).'}), 400
    except smtplib.SMTPException as e:
        logger.error(f"❌ SMTP error: {e}")
        return jsonify({'success': False, 'error': f'SMTP error: {str(e)}'}), 400
    except UnicodeEncodeError as e:
        logger.error(f"❌ Encoding error (likely non-breaking space in password): {e}")
        return jsonify({'success': False, 'error': 'Password encoding error. Please check your password for special characters and try again.'}), 400
    except Exception as e:
        logger.error(f"❌ Connection error: {e}")
        import traceback
        logger.error(f"   Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': f'Connection error: {str(e)}'}), 400

@app.route('/api/notification-templates', methods=['GET'])
@optional_login_required
def get_notification_templates():
    """Get notification templates for appointments"""
    try:
        from .models import NotificationTemplate
        
        templates = NotificationTemplate.query.filter_by(
            is_active=True,
            is_predefined=False
        ).all()
        
        return jsonify({
            'success': True,
            'templates': [{
                'id': t.id,
                'template_type': t.template_type,
                'template_name': t.template_name,
                'subject': t.subject,
                'message': t.message,
                'description': t.description
            } for t in templates]
        })
    except Exception as e:
        logger.error(f"Error fetching notification templates: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

# AI Health Report Endpoints
@app.route('/api/patients/<int:patient_id>/generate_report', methods=['GET'])
@optional_login_required
def api_generate_report(patient_id):
    """Generate AI health report via AJAX"""
    patient = Patient.query.get_or_404(patient_id)
    
    if not ai_reporter:
        return jsonify({'success': False, 'error': 'AI reporter not configured. Please add OpenAI API key.'}), 400
    
    # Get report type from query params
    report_type = request.args.get('report_type', 'patient')
    
    # Get health data
    health_data = HealthData.query.filter_by(patient_id=patient_id).order_by(HealthData.timestamp.desc()).limit(100).all()
    health_summary = {}
    for data in health_data:
        if data.measurement_type not in health_summary:
            health_summary[data.measurement_type] = []
        health_summary[data.measurement_type].append({
            'value': data.value,
            'unit': data.unit,
            'timestamp': data.timestamp
        })
    
    try:
        if report_type == 'patient':
            report = ai_reporter.generate_patient_report(patient, health_summary)
            title = 'Patient-Friendly Health Report'
        elif report_type == 'clinical':
            report = ai_reporter.generate_clinical_note(patient, health_summary)
            title = 'Clinical Note (SOAP Format)'
        elif report_type == 'video_script':
            report = ai_reporter.generate_video_script(patient, health_summary)
            title = 'Video Script for AI Avatar'
        else:
            return jsonify({'success': False, 'error': 'Invalid report type'}), 400
        
        return jsonify({
            'success': True,
            'report': report,
            'title': title,
            'patient_name': f"{patient.first_name} {patient.last_name}",
            'patient_email': patient.email
        })
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/patients/<int:patient_id>/send_report', methods=['POST'])
@optional_login_required
def api_send_report(patient_id):
    """Save clinical note/report to correspondence with optional email to patient, GP, or custom recipient"""
    patient = Patient.query.get_or_404(patient_id)
    
    try:
        # Get form data
        report_html = request.form.get('report_html')
        report_subject = request.form.get('subject', f"Health Report for {patient.first_name} {patient.last_name}")
        report_type = request.form.get('report_type', 'ai_report')
        recipient_type = request.form.get('recipient_type', '')  # '', 'patient', 'gp', 'custom'
        recipient_email = request.form.get('recipient_email', '')
        recipient_name = request.form.get('recipient_name', '')
        
        if not report_html:
            return jsonify({'success': False, 'error': 'Report content is required'}), 400
        
        # Handle file attachments
        attachments = []
        if 'attachments' in request.files:
            files = request.files.getlist('attachments')
            for file in files:
                if file and file.filename:
                    attachments.append({
                        'filename': file.filename,
                        'content': file.read()
                    })
        
        email_sent = False
        email_recipient = None
        
        # Send email if recipient specified
        if recipient_type and recipient_email:
            if not email_sender:
                return jsonify({'success': False, 'error': 'Email not configured. Please add SMTP settings in Settings page.'}), 400
            
            # Determine recipient for logging
            if recipient_type == 'patient':
                email_recipient = f"{patient.first_name} {patient.last_name} (Patient)"
            elif recipient_type == 'gp':
                email_recipient = f"{recipient_name} (GP)" if recipient_name else "GP"
            elif recipient_type == 'custom':
                email_recipient = recipient_email
            
            # Send email
            email_result = email_sender.send_health_report(
                to_email=recipient_email,
                patient_name=f"{patient.first_name} {patient.last_name}",
                report_content=report_html,
                subject=report_subject,
                attachments=attachments if attachments else None
            )
            
            if not email_result:
                logger.error(f"❌ Email sending failed for patient {patient_id} to {recipient_email}")
                return jsonify({'success': False, 'error': f'Failed to send email to {recipient_email}. Check server logs for details.'}), 400
            
            email_sent = True
            logger.info(f"✅ Sent health report email to {recipient_email} for patient {patient_id}")
        
        # Save to patient correspondence (always save)
        from .models import PatientCorrespondence
        correspondence = PatientCorrespondence(
            patient_id=patient_id,
            user_id=current_user.id if current_user.is_authenticated else None,
            channel='email' if email_sent else 'note',
            direction='outbound',
            subject=report_subject,
            body=report_html,
            recipient_email=recipient_email if recipient_email else None,
            status='sent' if email_sent else 'saved',
            sent_at=datetime.utcnow()
        )
        db.session.add(correspondence)
        
        # Also save to patient notes for historical record
        note = PatientNote(
            patient_id=patient_id,
            note_text=report_html,
            note_type=report_type,
            author=current_user.full_name if current_user.is_authenticated else 'System'
        )
        db.session.add(note)
        db.session.commit()
        
        # Build success message
        attachment_info = f" with {len(attachments)} attachment(s)" if attachments else ""
        
        if email_sent:
            message = f'Clinical note sent to {email_recipient}{attachment_info} and saved to Correspondence'
        else:
            message = f'Clinical note saved to Correspondence (no email sent)'
        
        return jsonify({
            'success': True,
            'message': message,
            'note_id': note.id,
            'correspondence_id': correspondence.id,
            'email_sent': email_sent
        })
    except Exception as e:
        logger.error(f"Error saving/sending report: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

# HeyGen Video Generation Endpoints
@app.route('/api/heygen/avatars', methods=['GET'])
@optional_login_required
def get_heygen_avatars():
    """Get available HeyGen avatars"""
    # Reload config to ensure secrets are loaded (for Cloud Run)
    from .config import Config
    
    # Create a new Config instance to reload secrets from Secret Manager
    config_instance = Config()
    
    try:
        # Get API key from config (which loads from Secret Manager in Cloud Run)
        api_key = Config.HEYGEN_API_KEY or os.getenv('HEYGEN_API_KEY')
        if not api_key:
            logger.warning("⚠️  HeyGen API key not found in config or environment")
            logger.warning(f"Config.HEYGEN_API_KEY: {bool(Config.HEYGEN_API_KEY)}, os.getenv: {bool(os.getenv('HEYGEN_API_KEY'))}")
            logger.warning(f"USE_SECRET_MANAGER: {Config.USE_SECRET_MANAGER}, GCP_PROJECT_ID: {Config.GCP_PROJECT_ID}")
            return jsonify({'success': False, 'error': 'HeyGen API not configured'}), 400
        
        logger.info(f"🔑 Using HeyGen API key: {api_key[:20]}..." if len(api_key) > 20 else f"🔑 Using HeyGen API key")
        
        # Create fresh HeyGen instance with current API key
        heygen_service = HeyGenService(api_key)
        avatars = heygen_service.get_avatars()
        
        if not avatars:
            logger.warning("⚠️  No avatars returned from HeyGen API")
            return jsonify({'success': False, 'error': 'No avatars found. Please check your HeyGen API key.'}), 400
        
        logger.info(f"✅ Retrieved {len(avatars)} avatars from HeyGen")
        return jsonify({'success': True, 'avatars': avatars})
    except requests.exceptions.HTTPError as e:
        error_msg = f"HeyGen API HTTP error: {e}"
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_detail = e.response.json()
                error_msg += f" - {error_detail}"
            except:
                error_msg += f" - Response: {e.response.text[:200]}"
        logger.error(error_msg)
        return jsonify({'success': False, 'error': error_msg}), 400
    except Exception as e:
        logger.error(f"Error fetching avatars: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/heygen/voices', methods=['GET'])
@optional_login_required
def get_heygen_voices():
    """Get available HeyGen voices"""
    # Reload config to ensure secrets are loaded (for Cloud Run)
    from .config import Config
    
    # Create a new Config instance to reload secrets from Secret Manager
    config_instance = Config()
    
    # Get API key from config (which loads from Secret Manager in Cloud Run)
    api_key = Config.HEYGEN_API_KEY or os.getenv('HEYGEN_API_KEY')
    if not api_key:
        logger.warning("⚠️  HeyGen API key not found in config or environment")
        return jsonify({'success': False, 'error': 'HeyGen API not configured'}), 400
    
    try:
        # Create fresh HeyGen instance with current API key
        heygen_service = HeyGenService(api_key)
        language = request.args.get('language')
        voices = heygen_service.get_voices(language)
        
        logger.info(f"✅ Retrieved {len(voices)} voices from HeyGen" + (f" (filtered for {language})" if language else ""))
        return jsonify({'success': True, 'voices': voices})
    except requests.exceptions.HTTPError as e:
        error_msg = f"HeyGen API HTTP error: {e}"
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_detail = e.response.json()
                error_msg += f" - {error_detail}"
            except:
                error_msg += f" - Response: {e.response.text[:200]}"
        logger.error(error_msg)
        return jsonify({'success': False, 'error': error_msg}), 400
    except Exception as e:
        logger.error(f"Error fetching voices: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/heygen/languages', methods=['GET'])
@optional_login_required
def get_heygen_languages():
    """Get available HeyGen voice languages"""
    # Reload config to ensure secrets are loaded (for Cloud Run)
    from .config import Config
    config_instance = Config()
    
    api_key = Config.HEYGEN_API_KEY or os.getenv('HEYGEN_API_KEY')
    if not api_key:
        return jsonify({'success': False, 'error': 'HeyGen API not configured'}), 400
    
    try:
        # Create fresh HeyGen instance with current API key
        heygen_service = HeyGenService(api_key)
        languages = heygen_service.get_languages()
        return jsonify({'success': True, 'languages': languages})
    except Exception as e:
        logger.error(f"Error fetching languages: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/heygen/generate', methods=['POST'])
@optional_login_required
def generate_heygen_video():
    """Generate HeyGen video from health report script"""
    # Reload config to ensure secrets are loaded (for Cloud Run)
    from .config import Config
    config_instance = Config()
    
    api_key = Config.HEYGEN_API_KEY or os.getenv('HEYGEN_API_KEY')
    if not api_key:
        return jsonify({'success': False, 'error': 'HeyGen API not configured'}), 400
    
    try:
        # Create fresh HeyGen instance with current API key
        heygen_service = HeyGenService(api_key)
        data = request.get_json()
        
        result = heygen_service.generate_video(
            script=data.get('script'),
            avatar_id=data.get('avatar_id'),
            voice_id=data.get('voice_id'),
            voice_gender=data.get('voice_gender'),
            voice_language=data.get('voice_language', 'English'),
            voice_speed=float(data.get('voice_speed', 1.0)),
            title=data.get('title', 'Health Report')
        )
        
        if result:
            return jsonify({'success': True, **result})
        else:
            return jsonify({'success': False, 'error': 'Video generation failed'}), 400
            
    except Exception as e:
        logger.error(f"Error generating video: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/heygen/status/<video_id>', methods=['GET'])
@optional_login_required
def get_heygen_status(video_id):
    """Check HeyGen video generation status"""
    # Reload config to ensure secrets are loaded (for Cloud Run)
    from .config import Config
    config_instance = Config()
    
    api_key = Config.HEYGEN_API_KEY or os.getenv('HEYGEN_API_KEY')
    if not api_key:
        return jsonify({'success': False, 'error': 'HeyGen API not configured'}), 400
    
    try:
        # Create fresh HeyGen instance with current API key
        heygen_service = HeyGenService(api_key)
        result = heygen_service.get_video_status(video_id)
        return jsonify({'success': True, **result})
    except Exception as e:
        logger.error(f"Error checking video status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/dashboard')
@optional_login_required
def dashboard():
    # Check if user is a practitioner (non-admin role)
    is_practitioner = current_user.is_authenticated and not current_user.is_admin and current_user.role in ['practitioner', 'nurse']
    
    if is_practitioner:
        # Practitioner Dashboard
        now = datetime.now()
        
        # Get upcoming appointments for this practitioner
        upcoming_appointments = Appointment.query.filter(
            Appointment.practitioner_id == current_user.id,
            Appointment.start_time >= now,
            Appointment.status != 'cancelled'
        ).order_by(Appointment.start_time.asc()).limit(10).all()
        
        # Get all patients who have appointments with this practitioner
        # Using a subquery to get unique patient IDs
        patient_ids = db.session.query(Appointment.patient_id).filter(
            Appointment.practitioner_id == current_user.id
        ).distinct().all()
        patient_ids = [pid[0] for pid in patient_ids]
        
        patients = Patient.query.filter(Patient.id.in_(patient_ids)).order_by(
            Patient.first_name, Patient.last_name
        ).all() if patient_ids else []
        
        # For each patient, get their last and next appointment with this practitioner
        patients_with_appointments = []
        for patient in patients:
            # Last appointment (completed or in the past)
            last_appt = Appointment.query.filter(
                Appointment.patient_id == patient.id,
                Appointment.practitioner_id == current_user.id,
                Appointment.start_time < now
            ).order_by(Appointment.start_time.desc()).first()
            
            # Next appointment (future)
            next_appt = Appointment.query.filter(
                Appointment.patient_id == patient.id,
                Appointment.practitioner_id == current_user.id,
                Appointment.start_time >= now,
                Appointment.status != 'cancelled'
            ).order_by(Appointment.start_time.asc()).first()
            
            patients_with_appointments.append({
                'patient': patient,
                'last_appointment': last_appt,
                'next_appointment': next_appt
            })
        
        return render_template('dashboard.html', 
                             is_practitioner=True,
                             upcoming_appointments=upcoming_appointments,
                             patients_with_appointments=patients_with_appointments)
    else:
        # Admin Dashboard (original)
        total_patients = Patient.query.count()
        connected_patients = Patient.query.filter(Patient.withings_user_id.isnot(None)).count()
        
        recent_data = HealthData.query.filter(
            HealthData.timestamp >= datetime.now() - timedelta(days=1)
        ).count()
        
        stats = {
            'total_patients': total_patients,
            'connected_patients': connected_patients,
            'recent_measurements': recent_data,
            'total_devices': Device.query.count()
        }
        
        all_patients = Patient.query.order_by(Patient.first_name, Patient.last_name).all()
        
        return render_template('dashboard.html', 
                             is_practitioner=False,
                             stats=stats, 
                             all_patients=all_patients)





# ============================================================================
# PATIENT API - Authentication & JWT Utilities
# ============================================================================

def get_jwt_secret():
    """Get JWT secret from environment or generate one"""
    secret = os.getenv('JWT_SECRET')
    if not secret:
        # Generate a secret if not set (for development)
        secret = secrets.token_urlsafe(32)
        logger.warning("JWT_SECRET not set, using generated secret (tokens will not persist across restarts)")
    return secret

def generate_jwt_token(patient_id, email, expires_in_hours=24):
    """Generate JWT access token for patient"""
    payload = {
        'patient_id': patient_id,
        'email': email,
        'exp': datetime.utcnow() + timedelta(hours=expires_in_hours),
        'iat': datetime.utcnow(),
        'type': 'access'
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm='HS256')

def generate_refresh_token(patient_id, email):
    """Generate JWT refresh token (longer expiry)"""
    payload = {
        'patient_id': patient_id,
        'email': email,
        'exp': datetime.utcnow() + timedelta(days=30),
        'iat': datetime.utcnow(),
        'type': 'refresh'
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm='HS256')

def verify_jwt_token(token):
    """Verify and decode JWT token"""
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def patient_auth_required(f):
    """Decorator to require patient JWT authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'error': 'Authorization header missing'}), 401
        
        try:
            token = auth_header.split(' ')[1]  # Bearer <token>
        except IndexError:
            return jsonify({'success': False, 'error': 'Invalid authorization header format'}), 401
        
        payload = verify_jwt_token(token)
        if not payload:
            return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401
        
        # Add patient info to request context
        request.patient_id = payload.get('patient_id')
        request.patient_email = payload.get('email')
        
        return f(*args, **kwargs)
    return decorated_function

# Patient API Health Check
@app.route('/api/patient', methods=['GET'])
def patient_api_health():
    """Health check for patient API"""
    return jsonify({
        'success': True,
        'message': 'CaptureCare Patient API is running',
        'version': '1.0.0',
        'endpoints': {
            'auth': {
                'login': '/api/patient/auth/login',
                'register': '/api/patient/auth/register',
                'apple': '/api/patient/auth/apple',
                'google': '/api/patient/auth/google',
                'refresh': '/api/patient/auth/refresh'
            },
            'profile': '/api/patient/profile',
            'health_data': '/api/patient/health-data',
            'appointments': '/api/patient/appointments'
        }
    })

# Patient Authentication Endpoints
@app.route('/api/patient/auth/login', methods=['POST'])
def patient_auth_login():
    """Patient email/password login"""
    try:
        data = request.json or {}
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'success': False, 'error': 'Email and password are required'}), 400
        
        # Find patient auth by email
        patient_auth = PatientAuth.query.filter_by(email=email, auth_provider='email', is_active=True).first()
        
        if not patient_auth or not patient_auth.check_password(password):
            return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
        
        # Get patient
        patient = patient_auth.patient
        if not patient:
            return jsonify({'success': False, 'error': 'Patient not found'}), 404
        
        # Generate tokens
        access_token = generate_jwt_token(patient.id, email)
        refresh_token = generate_refresh_token(patient.id, email)
        
        # Save refresh token
        patient_auth.refresh_token = refresh_token
        patient_auth.token_expires_at = datetime.utcnow() + timedelta(hours=24)
        db.session.commit()
        
        # Return patient data
        patient_data = {
            'id': patient.id,
            'first_name': patient.first_name,
            'last_name': patient.last_name,
            'email': patient.email,
            'phone': patient.phone or patient.mobile,
            'date_of_birth': patient.date_of_birth.isoformat() if patient.date_of_birth else None
        }
        
        return jsonify({
            'success': True,
            'access_token': access_token,
            'refresh_token': refresh_token,
            'patient': patient_data
        })
        
    except Exception as e:
        logger.error(f"Patient login error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/patient/auth/register', methods=['POST'])
def patient_auth_register():
    """Patient registration (creates new patient and auth)"""
    try:
        data = request.json or {}
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')
        
        if not email or not password:
            return jsonify({'success': False, 'error': 'Email and password are required'}), 400
        
        # Check if email already exists
        existing_auth = PatientAuth.query.filter_by(email=email).first()
        if existing_auth:
            return jsonify({'success': False, 'error': 'Email already registered'}), 400
        
        # Create new patient
        patient = Patient(
            first_name=first_name or 'Patient',
            last_name=last_name or 'User',
            email=email,
            created_at=datetime.utcnow()
        )
        db.session.add(patient)
        db.session.flush()  # Get patient ID
        
        # Create patient auth
        patient_auth = PatientAuth(
            patient_id=patient.id,
            auth_provider='email',
            email=email,
            is_active=True
        )
        patient_auth.set_password(password)
        db.session.add(patient_auth)
        db.session.commit()
        
        # Generate tokens
        access_token = generate_jwt_token(patient.id, email)
        refresh_token = generate_refresh_token(patient.id, email)
        
        # Save refresh token
        patient_auth.refresh_token = refresh_token
        patient_auth.token_expires_at = datetime.utcnow() + timedelta(hours=24)
        db.session.commit()
        
        patient_data = {
            'id': patient.id,
            'first_name': patient.first_name,
            'last_name': patient.last_name,
            'email': patient.email
        }
        
        return jsonify({
            'success': True,
            'access_token': access_token,
            'refresh_token': refresh_token,
            'patient': patient_data
        }), 201
        
    except Exception as e:
        logger.error(f"Patient registration error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/patient/auth/apple', methods=['POST'])
def patient_auth_apple():
    """Patient Apple Sign In authentication"""
    try:
        data = request.json or {}
        identity_token = data.get('identity_token')
        user_id = data.get('user_id')
        email = data.get('email', '').strip().lower() if data.get('email') else None
        
        if not identity_token or not user_id:
            return jsonify({'success': False, 'error': 'Apple identity token and user ID are required'}), 400
        
        # Find or create patient auth
        patient_auth = PatientAuth.query.filter_by(
            provider_user_id=user_id,
            auth_provider='apple'
        ).first()
        
        if not patient_auth:
            # Check if email exists for different provider
            if email:
                existing = PatientAuth.query.filter_by(email=email).first()
                if existing:
                    return jsonify({
                        'success': False,
                        'error': 'Email already registered with different provider'
                    }), 400
            
            # Create new patient
            patient = Patient(
                first_name='Patient',
                last_name='User',
                email=email,
                created_at=datetime.utcnow()
            )
            db.session.add(patient)
            db.session.flush()
            
            # Create patient auth
            patient_auth = PatientAuth(
                patient_id=patient.id,
                auth_provider='apple',
                provider_user_id=user_id,
                email=email,
                is_active=True
            )
            db.session.add(patient_auth)
            db.session.commit()
        
        patient = patient_auth.patient
        
        # Generate tokens
        access_token = generate_jwt_token(patient.id, email or f"apple_{user_id}")
        refresh_token = generate_refresh_token(patient.id, email or f"apple_{user_id}")
        
        patient_auth.refresh_token = refresh_token
        patient_auth.token_expires_at = datetime.utcnow() + timedelta(hours=24)
        db.session.commit()
        
        patient_data = {
            'id': patient.id,
            'first_name': patient.first_name,
            'last_name': patient.last_name,
            'email': patient.email
        }
        
        return jsonify({
            'success': True,
            'access_token': access_token,
            'refresh_token': refresh_token,
            'patient': patient_data
        })
        
    except Exception as e:
        logger.error(f"Apple auth error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/patient/auth/google', methods=['POST'])
def patient_auth_google():
    """Patient Google Sign In authentication"""
    try:
        data = request.json or {}
        id_token = data.get('id_token')
        email = data.get('email', '').strip().lower()
        user_id = data.get('sub') or data.get('user_id')
        
        if not email or not user_id:
            return jsonify({'success': False, 'error': 'Google email and user ID are required'}), 400
        
        # Find or create patient auth
        patient_auth = PatientAuth.query.filter_by(
            provider_user_id=user_id,
            auth_provider='google'
        ).first()
        
        if not patient_auth:
            # Check if email exists
            existing = PatientAuth.query.filter_by(email=email).first()
            if existing and existing.auth_provider != 'google':
                return jsonify({
                    'success': False,
                    'error': 'Email already registered with different provider'
                }), 400
            
            # Create new patient
            patient = Patient(
                first_name='Patient',
                last_name='User',
                email=email,
                created_at=datetime.utcnow()
            )
            db.session.add(patient)
            db.session.flush()
            
            # Create patient auth
            patient_auth = PatientAuth(
                patient_id=patient.id,
                auth_provider='google',
                provider_user_id=user_id,
                email=email,
                is_active=True
            )
            db.session.add(patient_auth)
            db.session.commit()
        
        patient = patient_auth.patient
        
        # Generate tokens
        access_token = generate_jwt_token(patient.id, email)
        refresh_token = generate_refresh_token(patient.id, email)
        
        patient_auth.refresh_token = refresh_token
        patient_auth.token_expires_at = datetime.utcnow() + timedelta(hours=24)
        db.session.commit()
        
        patient_data = {
            'id': patient.id,
            'first_name': patient.first_name,
            'last_name': patient.last_name,
            'email': patient.email
        }
        
        return jsonify({
            'success': True,
            'access_token': access_token,
            'refresh_token': refresh_token,
            'patient': patient_data
        })
        
    except Exception as e:
        logger.error(f"Google auth error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/patient/auth/refresh', methods=['POST'])
def patient_auth_refresh():
    """Refresh access token using refresh token"""
    try:
        data = request.json or {}
        refresh_token = data.get('refresh_token')
        
        if not refresh_token:
            return jsonify({'success': False, 'error': 'Refresh token is required'}), 400
        
        # Verify refresh token
        payload = verify_jwt_token(refresh_token)
        if not payload or payload.get('type') != 'refresh':
            return jsonify({'success': False, 'error': 'Invalid refresh token'}), 401
        
        patient_id = payload.get('patient_id')
        email = payload.get('email')
        
        # Verify patient auth exists
        patient_auth = PatientAuth.query.filter_by(patient_id=patient_id).first()
        if not patient_auth or patient_auth.refresh_token != refresh_token:
            return jsonify({'success': False, 'error': 'Invalid refresh token'}), 401
        
        # Generate new tokens
        new_access_token = generate_jwt_token(patient_id, email)
        new_refresh_token = generate_refresh_token(patient_id, email)
        
        # Update refresh token
        patient_auth.refresh_token = new_refresh_token
        patient_auth.token_expires_at = datetime.utcnow() + timedelta(hours=24)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'access_token': new_access_token,
            'refresh_token': new_refresh_token
        })
        
    except Exception as e:
        logger.error(f"Token refresh error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/patient/profile', methods=['GET'])
@patient_auth_required
def patient_profile():
    """Get patient profile (protected) - returns all patient fields"""
    try:
        patient = Patient.query.get_or_404(request.patient_id)
        
        return jsonify({
            'success': True,
            'patient': {
                'id': patient.id,
                'first_name': patient.first_name,
                'last_name': patient.last_name,
                'email': patient.email,
                'phone': patient.phone,
                'mobile': patient.mobile,
                'date_of_birth': patient.date_of_birth.isoformat() if patient.date_of_birth else None,
                'sex': patient.sex,
                'address_line1': patient.address_line1,
                'address_line2': patient.address_line2,
                'city': patient.city,
                'state': patient.state,
                'postcode': patient.postcode,
                'country': patient.country,
                'emergency_contact_name': patient.emergency_contact_name,
                'emergency_contact_phone': patient.emergency_contact_phone,
                'emergency_contact_email': patient.emergency_contact_email,
                'emergency_contact_relationship': patient.emergency_contact_relationship,
                'emergency_contact_consent': patient.emergency_contact_consent,
                'gp_name': patient.gp_name,
                'gp_address': patient.gp_address,
                'gp_phone': patient.gp_phone,
                'has_gp': patient.has_gp,
                'occupation': patient.occupation,
                'medicare_number': patient.medicare_number,
                'dva_number': patient.dva_number,
                'current_medications': patient.current_medications,
                'medical_alerts': patient.medical_alerts,
                'created_at': patient.created_at.isoformat() if patient.created_at else None
            }
        })
    except Exception as e:
        logger.error(f"Get profile error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/patient/health-data', methods=['GET'])
@patient_auth_required
def patient_health_data():
    """Get patient health data (protected) with robust error handling and connection retry"""
    max_retries = 3
    retry_delay = 0.5  # seconds
    
    for attempt in range(max_retries):
        try:
            patient_id = request.patient_id
            days = int(request.args.get('days', 30))
            metric_type = request.args.get('type')
            
            # Validate days parameter
            if days < 1 or days > 365:
                days = 30
            
            # Calculate timestamp with timezone awareness
            from datetime import timezone
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)
            
            # Build query with proper session handling
            try:
                # Use a fresh query to avoid stale connections
                query = db.session.query(HealthData).filter(
                    HealthData.patient_id == patient_id,
                    HealthData.timestamp >= cutoff_time
                )
                
                if metric_type:
                    query = query.filter(HealthData.measurement_type == metric_type)
                
                # Execute query with timeout protection
                health_data = query.order_by(HealthData.timestamp.asc()).all()
                
                # Process data safely
                data = []
                for item in health_data:
                    try:
                        data.append({
                            'id': item.id,
                            'type': item.measurement_type,
                            'value': float(item.value) if item.value is not None else None,
                            'unit': item.unit or '',
                            'timestamp': item.timestamp.isoformat() if item.timestamp else None,
                            'source': item.source or '',
                            'device_source': item.device_source or ''
                        })
                    except (AttributeError, ValueError, TypeError) as e:
                        logger.warning(f"Skipping invalid health data item {item.id}: {e}")
                        continue
                
                # Commit successful transaction
                db.session.commit()
                
                return jsonify({
                    'success': True,
                    'data': data,
                    'count': len(data)
                })
                
            except Exception as db_error:
                # Rollback on any database error
                db.session.rollback()
                
                # Check if it's a connection error that we should retry
                error_str = str(db_error).lower()
                is_connection_error = any(keyword in error_str for keyword in [
                    'lost synchronization',
                    'server closed the connection',
                    'connection',
                    'operationalerror',
                    'timeout',
                    'broken pipe'
                ])
                
                if is_connection_error and attempt < max_retries - 1:
                    logger.warning(f"Database connection error (attempt {attempt + 1}/{max_retries}): {db_error}")
                    import time
                    time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                    continue  # Retry
                else:
                    raise  # Re-raise if not retryable or last attempt
                    
        except Exception as e:
            # Final error handling
            db.session.rollback()
            
            if attempt == max_retries - 1:
                # Last attempt failed
                logger.error(f"Get health data error after {max_retries} attempts: {e}", exc_info=True)
                
                # Return user-friendly error message
                error_message = "Unable to load health data. Please try again."
                if "lost synchronization" in str(e).lower() or "connection" in str(e).lower():
                    error_message = "Database connection issue. Please try again in a moment."
                
                return jsonify({
                    'success': False,
                    'error': error_message,
                    'error_code': 'DATABASE_ERROR'
                }), 500
            else:
                # Will retry
                continue
    
    # Should never reach here, but just in case
    return jsonify({
        'success': False,
        'error': 'Unable to load health data. Please try again.'
    }), 500

@app.route('/api/patient/target-ranges', methods=['GET'])
@patient_auth_required
def patient_target_ranges():
    """Get patient target ranges (protected, read-only)"""
    try:
        patient_id = request.patient_id
        # Only return target ranges that are enabled for patient app
        # Handle case where column might not exist yet (graceful migration)
        try:
            target_ranges = TargetRange.query.filter_by(
                patient_id=patient_id
            ).filter(
                TargetRange.show_in_patient_app == True
            ).all()
        except Exception:
            # If column doesn't exist yet, return all target ranges
            target_ranges = TargetRange.query.filter_by(patient_id=patient_id).all()
        
        # Optimized: Use list comprehension
        ranges_list = [{
            'measurement_type': tr.measurement_type,
            'target_mode': tr.target_mode,
            'min_value': tr.min_value,
            'max_value': tr.max_value,
            'target_value': tr.target_value,
            'unit': tr.unit
        } for tr in target_ranges]
        
        return jsonify({
            'success': True,
            'target_ranges': ranges_list
        })
    except Exception as e:
        logger.error(f"Get target ranges error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/migrate/show-in-patient-app', methods=['POST'])
def migrate_show_in_patient_app():
    """One-time migration: Add show_in_patient_app column to target_ranges (no auth required)"""
    try:
        from sqlalchemy import text
        
        # Check if column already exists
        result = db.session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='target_ranges' 
            AND column_name='show_in_patient_app'
        """))
        
        if result.fetchone():
            return jsonify({
                'success': True,
                'message': 'Column already exists',
                'already_exists': True
            })
        
        # Add column
        db.session.execute(text("""
            ALTER TABLE target_ranges 
            ADD COLUMN show_in_patient_app BOOLEAN DEFAULT TRUE
        """))
        db.session.commit()
        
        # Update existing rows
        db.session.execute(text("""
            UPDATE target_ranges 
            SET show_in_patient_app = TRUE 
            WHERE show_in_patient_app IS NULL
        """))
        db.session.commit()
        
        logger.info("✅ Migration completed: Added show_in_patient_app column")
        return jsonify({
            'success': True,
            'message': 'Migration completed successfully',
            'already_exists': False
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Migration error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/migrate/create-indexes', methods=['POST'])
def create_database_indexes():
    """Create performance indexes (no auth required)"""
    try:
        from sqlalchemy import text
        
        indexes = [
            ("idx_health_data_patient_timestamp", """
                CREATE INDEX IF NOT EXISTS idx_health_data_patient_timestamp 
                ON health_data(patient_id, timestamp DESC)
            """),
            ("idx_health_data_measurement_type", """
                CREATE INDEX IF NOT EXISTS idx_health_data_measurement_type 
                ON health_data(measurement_type)
            """),
            ("idx_health_data_patient_type_timestamp", """
                CREATE INDEX IF NOT EXISTS idx_health_data_patient_type_timestamp 
                ON health_data(patient_id, measurement_type, timestamp DESC)
            """),
            ("idx_target_ranges_patient_measurement", """
                CREATE INDEX IF NOT EXISTS idx_target_ranges_patient_measurement 
                ON target_ranges(patient_id, measurement_type)
            """),
            ("idx_target_ranges_show_in_app", """
                CREATE INDEX IF NOT EXISTS idx_target_ranges_show_in_app 
                ON target_ranges(show_in_patient_app) 
                WHERE show_in_patient_app = TRUE
            """),
            ("idx_appointments_patient_date", """
                CREATE INDEX IF NOT EXISTS idx_appointments_patient_date 
                ON appointments(patient_id, start_time DESC)
            """),
            ("idx_devices_patient_id", """
                CREATE INDEX IF NOT EXISTS idx_devices_patient_id 
                ON devices(patient_id)
            """),
        ]
        
        # Try to create patient_auth indexes if table exists
        try:
            db.session.execute(text("SELECT 1 FROM patient_auth LIMIT 1"))
            indexes.extend([
                ("idx_patient_auth_patient_id", """
                    CREATE INDEX IF NOT EXISTS idx_patient_auth_patient_id 
                    ON patient_auth(patient_id)
                """),
                ("idx_patient_auth_email", """
                    CREATE INDEX IF NOT EXISTS idx_patient_auth_email 
                    ON patient_auth(email)
                """),
            ])
        except Exception:
            pass  # Table doesn't exist, skip those indexes
        
        created = []
        skipped = []
        errors = []
        
        for index_name, sql in indexes:
            try:
                db.session.execute(text(sql))
                db.session.commit()
                created.append(index_name)
            except Exception as e:
                db.session.rollback()
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    skipped.append(index_name)
                else:
                    errors.append(f"{index_name}: {str(e)}")
        
        return jsonify({
            'success': True,
            'created': created,
            'skipped': skipped,
            'errors': errors,
            'summary': f"{len(created)} created, {len(skipped)} already existed, {len(errors)} errors"
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Index creation error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/health')
def health_check():
    """Health check endpoint for load balancer monitoring"""
    try:
        # Check database connection
        db.session.execute(db.text('SELECT 1'))
        
        # Check if critical services are configured
        # Check both app.config and environment variables (for Secret Manager)
        withings_configured = bool(app.config.get('WITHINGS_CLIENT_ID') or os.getenv('WITHINGS_CLIENT_ID'))
        openai_configured = bool(app.config.get('OPENAI_API_KEY') or os.getenv('OPENAI_API_KEY'))
        cliniko_configured = bool(app.config.get('CLINIKO_API_KEY') or os.getenv('CLINIKO_API_KEY'))
        
        services_status = {
            'database': 'healthy',
            'withings': 'configured' if withings_configured else 'not_configured',
            'openai': 'configured' if openai_configured else 'not_configured',
            'cliniko': 'configured' if cliniko_configured else 'not_configured'
        }
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'services': services_status
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 503

@app.route('/admin/create-patient-auth-table', methods=['POST'])
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

# Google Login Routes
@app.route('/google/login')
def google_login():
    logger.info("Google login route accessed")
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_secrets_file('client_secrets.json', scopes=['https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/userinfo.profile', 'openid'])
    flow.redirect_uri = url_for('google_callback', _external=True)
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
    session['state'] = state
    return redirect(authorization_url)

@app.route('/google/callback')
def google_callback():
    import os
    from google_auth_oauthlib.flow import Flow
    from google.oauth2 import id_token
    from google.auth.transport import requests as google_requests
    import json
    
    # Allow OAuth to accept additional scopes without raising warnings
    os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
    
    # Load client secrets to get client_id
    with open('client_secrets.json', 'r') as f:
        client_secrets = json.load(f)
    client_id = client_secrets['web']['client_id']
    
    flow = Flow.from_client_secrets_file('client_secrets.json', scopes=['https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/userinfo.profile', 'openid'])
    flow.redirect_uri = url_for('google_callback', _external=True)
    
    # Get authorization response URL and force HTTPS (Cloud Run terminates SSL)
    authorization_response = request.url
    if authorization_response.startswith('http://'):
        authorization_response = authorization_response.replace('http://', 'https://', 1)
    
    # Fetch token (OAUTHLIB_RELAX_TOKEN_SCOPE allows additional scopes)
    flow.fetch_token(authorization_response=authorization_response)
    credentials = flow.credentials
    userinfo = id_token.verify_oauth2_token(credentials.id_token, google_requests.Request(), client_id)
    user = User.query.filter_by(email=userinfo['email']).first()
    if not user:
        user = User(username=userinfo['email'].split('@')[0], email=userinfo['email'], role='user')
        db.session.add(user)
        db.session.commit()
    login_user(user)
    return redirect(url_for('dashboard'))

logger.info("Google routes loaded successfully")

# Company-Wide Settings Routes
@app.route('/company-settings')
@login_required
def company_settings():
    """Admin page for managing company-wide settings (office hours, holidays, etc.)"""
    # Only admins can access
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('dashboard'))
    
    # Get all company-wide blocks
    company_blocks = AvailabilityException.query.filter_by(
        is_company_wide=True
    ).order_by(AvailabilityException.exception_date.asc()).all()
    
    # Get company office hours
    office_hours = AvailabilityPattern.query.filter_by(
        is_company_wide=True
    ).order_by(AvailabilityPattern.start_time.asc()).all()
    
    return render_template('company_settings.html', 
                         company_blocks=company_blocks,
                         office_hours=office_hours)

@app.route('/api/company-settings/blocks', methods=['POST'])
@login_required
def add_company_block():
    """Add a company-wide block (holiday, closure, etc.)"""
    # Only admins can access
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin privileges required'}), 403
    
    try:
        data = request.get_json()
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date', start_date_str)  # Single day if no end_date
        exception_type = data.get('exception_type', 'holiday')
        reason = data.get('reason', 'Company Holiday')
        is_all_day = data.get('is_all_day', True)
        
        if not start_date_str:
            return jsonify({'success': False, 'error': 'Start date is required'}), 400
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        # Create a block for each day in the range
        current_date = start_date
        blocks_created = []
        
        while current_date <= end_date:
            # Check if block already exists
            existing = AvailabilityException.query.filter_by(
                is_company_wide=True,
                exception_date=current_date
            ).first()
            
            if not existing:
                block = AvailabilityException(
                    user_id=None,  # NULL for company-wide
                    is_company_wide=True,
                    exception_date=current_date,
                    exception_type=exception_type,
                    is_all_day=is_all_day,
                    reason=reason
                )
                db.session.add(block)
                blocks_created.append(current_date.strftime('%Y-%m-%d'))
            
            # Move to next day
            current_date += timedelta(days=1)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Added {len(blocks_created)} company-wide blocks',
            'dates': blocks_created
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding company block: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/company-settings/blocks/<int:block_id>', methods=['DELETE'])
@login_required
def delete_company_block(block_id):
    """Delete a company-wide block"""
    # Only admins can access
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin privileges required'}), 403
    
    try:
        
        block = AvailabilityException.query.get_or_404(block_id)
        
        # Verify it's a company-wide block
        if not block.is_company_wide:
            return jsonify({'success': False, 'error': 'Not a company-wide block'}), 400
        
        db.session.delete(block)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Company-wide block deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting company block: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Company Office Hours Routes
@app.route('/api/company-settings/office-hours', methods=['POST'])
@login_required
def add_company_office_hours():
    """Add company-wide office hours pattern"""
    # Only admins can access
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin privileges required'}), 403
    
    try:
        data = request.get_json()
        title = data.get('title', 'Office Hours')
        start_time_str = data.get('start_time')
        end_time_str = data.get('end_time')
        weekdays = data.get('weekdays')  # e.g., "0,1,2,3,4" for Mon-Fri
        notes = data.get('notes', '')
        
        if not start_time_str or not end_time_str:
            return jsonify({'success': False, 'error': 'Start and end times are required'}), 400
        
        # Parse times
        from datetime import datetime
        start_time = datetime.strptime(start_time_str, '%H:%M').time()
        end_time = datetime.strptime(end_time_str, '%H:%M').time()
        
        # Create office hours pattern
        pattern = AvailabilityPattern(
            user_id=None,  # NULL for company-wide
            is_company_wide=True,
            title=title,
            frequency='weekly',
            weekdays=weekdays,
            start_time=start_time,
            end_time=end_time,
            is_active=True,
            notes=notes
        )
        
        db.session.add(pattern)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Office hours added successfully',
            'pattern_id': pattern.id
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding office hours: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/company-settings/office-hours/<int:pattern_id>', methods=['DELETE'])
@login_required
def delete_company_office_hours(pattern_id):
    """Delete company office hours pattern"""
    # Only admins can access
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin privileges required'}), 403
    
    try:
        pattern = AvailabilityPattern.query.get_or_404(pattern_id)
        
        # Verify it's a company-wide pattern
        if not pattern.is_company_wide:
            return jsonify({'success': False, 'error': 'Not a company-wide pattern'}), 400
        
        db.session.delete(pattern)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Office hours deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting office hours: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/company-settings/office-hours/<int:pattern_id>/toggle', methods=['POST'])
@login_required
def toggle_company_office_hours(pattern_id):
    """Toggle active/inactive status of office hours pattern"""
    # Only admins can access
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin privileges required'}), 403
    
    try:
        pattern = AvailabilityPattern.query.get_or_404(pattern_id)
        
        # Verify it's a company-wide pattern
        if not pattern.is_company_wide:
            return jsonify({'success': False, 'error': 'Not a company-wide pattern'}), 400
        
        # Toggle active status
        pattern.is_active = not pattern.is_active
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Office hours {"activated" if pattern.is_active else "deactivated"} successfully',
            'is_active': pattern.is_active
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error toggling office hours: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/debug/availability-blocks')
@login_required
def debug_availability_blocks():
    """Debug page to see all availability blocks"""
    from capturecare.models import AvailabilityException
    from datetime import date
    
    # Get all blocks around Christmas
    blocks = AvailabilityException.query.filter(
        AvailabilityException.exception_date >= date(2025, 12, 20),
        AvailabilityException.exception_date <= date(2026, 1, 10)
    ).order_by(AvailabilityException.exception_date).all()
    
    result = {
        'total_blocks': len(blocks),
        'company_wide_blocks': [],
        'individual_blocks': []
    }
    
    for block in blocks:
        block_data = {
            'id': block.id,
            'date': str(block.exception_date),
            'type': block.exception_type,
            'reason': block.reason,
            'is_all_day': block.is_all_day,
            'is_company_wide': block.is_company_wide,
            'user_id': block.user_id
        }
        
        if block.is_company_wide:
            result['company_wide_blocks'].append(block_data)
        else:
            result['individual_blocks'].append(block_data)
    
    return jsonify(result)

logger.info("Company settings routes loaded successfully")

# Run database migrations on startup
def run_startup_migrations():
    """Run necessary database migrations on application startup"""
    try:
        logger.info("🔧 Checking for pending database migrations...")
        from sqlalchemy import text, inspect
        
        # Check if created_by_id column exists
        inspector = inspect(db.engine)
        appointments_columns = [col['name'] for col in inspector.get_columns('appointments')]
        
        if 'created_by_id' not in appointments_columns:
            logger.info("⚙️  Adding created_by_id column to appointments table...")
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE appointments ADD COLUMN created_by_id INTEGER;"))
                conn.commit()
            logger.info("✅ Migration complete: created_by_id column added")
        
        # Check if allocated_practitioner_id column exists in patients table
        patients_columns = [col['name'] for col in inspector.get_columns('patients')]
        
        if 'allocated_practitioner_id' not in patients_columns:
            logger.info("⚙️  Adding allocated_practitioner_id column to patients table...")
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE patients ADD COLUMN allocated_practitioner_id INTEGER REFERENCES users(id);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_patients_allocated_practitioner ON patients(allocated_practitioner_id);"))
                conn.commit()
            logger.info("✅ Migration complete: allocated_practitioner_id column added")
        
        # Check if is_company_wide column exists in availability_exceptions table
        exceptions_columns = [col['name'] for col in inspector.get_columns('availability_exceptions')]
        
        if 'is_company_wide' not in exceptions_columns:
            logger.info("⚙️  Adding is_company_wide column to availability_exceptions table...")
            with db.engine.connect() as conn:
                # Add the column with default False
                conn.execute(text("ALTER TABLE availability_exceptions ADD COLUMN is_company_wide BOOLEAN DEFAULT FALSE NOT NULL;"))
                # Make user_id nullable for company-wide blocks
                conn.execute(text("ALTER TABLE availability_exceptions ALTER COLUMN user_id DROP NOT NULL;"))
                # Create index for faster company-wide lookups
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_availability_exceptions_company_wide ON availability_exceptions(is_company_wide, exception_date);"))
                conn.commit()
            logger.info("✅ Migration complete: is_company_wide column added to availability_exceptions")
        
        # Check if is_company_wide column exists in availability_patterns table
        patterns_columns = [col['name'] for col in inspector.get_columns('availability_patterns')]
        
        if 'is_company_wide' not in patterns_columns:
            logger.info("⚙️  Adding is_company_wide column to availability_patterns table...")
            with db.engine.connect() as conn:
                # Add the column with default False
                conn.execute(text("ALTER TABLE availability_patterns ADD COLUMN is_company_wide BOOLEAN DEFAULT FALSE NOT NULL;"))
                # Make user_id nullable for company-wide patterns
                conn.execute(text("ALTER TABLE availability_patterns ALTER COLUMN user_id DROP NOT NULL;"))
                # Create index for faster company-wide lookups
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_availability_patterns_company_wide ON availability_patterns(is_company_wide, is_active);"))
                conn.commit()
            logger.info("✅ Migration complete: is_company_wide column added to availability_patterns")
        
        logger.info("✅ Database schema is up to date")
        
        # CRITICAL: Fix sequences that may be out of sync (prevents duplicate key errors)
        logger.info("🔧 Checking and fixing database sequences...")
        with db.engine.connect() as conn:
            # Fix all major sequences to match current max IDs
            sequences_to_fix = [
                ('availability_patterns', 'availability_patterns_id_seq'),
                ('availability_exceptions', 'availability_exceptions_id_seq'),
                ('appointments', 'appointments_id_seq'),
                ('patients', 'patients_id_seq'),
                ('users', 'users_id_seq'),
                ('patient_notes', 'patient_notes_id_seq'),
                ('invoices', 'invoices_id_seq')
            ]
            
            for table_name, seq_name in sequences_to_fix:
                try:
                    # Reset sequence to max(id) + 1
                    conn.execute(text(f"""
                        SELECT setval('{seq_name}', 
                                     COALESCE((SELECT MAX(id) FROM {table_name}), 0) + 1, 
                                     false)
                    """))
                    conn.commit()
                except Exception as seq_error:
                    logger.warning(f"Could not fix sequence {seq_name}: {seq_error}")
            
            logger.info("✅ All sequences synchronized")
            
    except Exception as e:
        logger.warning(f"Migration check failed (non-critical): {e}")

# Run migrations with app context
with app.app_context():
    run_startup_migrations()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
