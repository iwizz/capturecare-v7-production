from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash, Response
from flask_cors import CORS
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
from models import db, Patient, HealthData, Device, User, TargetRange, Appointment, PatientNote, WebhookLog, Invoice, InvoiceItem, PatientCorrespondence, CommunicationWebhookLog, NotificationTemplate, AvailabilityPattern, AvailabilityException, PatientAuth
from config import Config
from withings_auth import WithingsAuthManager
from sync_health_data import HealthDataSynchronizer
from patient_matcher import ClinikoIntegration
from ai_health_reporter import AIHealthReporter
from email_sender import EmailSender
from calendar_sync import GoogleCalendarSync
from notification_service import NotificationService
from heygen_service import HeyGenService
from stripe_service import StripeService
import logging
import os
import json
import requests
import smtplib
from flask_migrate import Migrate

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

app.secret_key = app.config['SECRET_KEY']

# Force production security settings
os.environ['FLASK_DEBUG'] = '0'
SKIP_AUTH = False
app.config['DEBUG'] = False
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
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

CORS(app)
db.init_app(app)
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
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
from tz_utils import to_local, format_local

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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember', False) == 'on'
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account has been deactivated. Please contact an administrator.', 'error')
                return redirect(url_for('login'))
            
            # Make session permanent to work in iframe context
            session.permanent = True
            login_user(user, remember=True)  # Always remember for iframe context
            logger.info(f"User {username} logged in successfully")
            
            # Always redirect to index to avoid URL parameter issues in iframe
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
            logger.warning(f"Failed login attempt for username: {username}")
    
    return render_template('login.html')

@app.route('/logout')
@optional_login_required
def logout():
    username = current_user.username
    logout_user()
    logger.info(f"User {username} logged out")
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/setup-password', methods=['GET', 'POST'])
def setup_password():
    """Password setup page for new users"""
    token = request.args.get('token') or request.form.get('token')
    
    if not token:
        flash('Invalid or missing setup link.', 'error')
        return redirect(url_for('login'))
    
    # Find user with this token
    user = User.query.filter_by(password_setup_token=token).first()
    
    if not user:
        flash('Invalid setup link. Please contact your administrator.', 'error')
        return redirect(url_for('login'))
    
    # Check if token has expired
    if user.password_setup_token_expires and user.password_setup_token_expires < datetime.utcnow():
        flash('This setup link has expired. Please contact your administrator for a new link.', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not password or not confirm_password:
            flash('Please enter both password fields.', 'error')
            return render_template('setup_password.html', user=user, token=token)
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('setup_password.html', user=user, token=token)
        
        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
            return render_template('setup_password.html', user=user, token=token)
        
        # Set the password
        user.set_password(password)
        user.password_set = True
        user.password_setup_token = None
        user.password_setup_token_expires = None
        
        db.session.commit()
        
        flash('Password set successfully! You can now log in.', 'success')
        logger.info(f"User {user.username} completed password setup")
        
        return redirect(url_for('login'))
    
    return render_template('setup_password.html', user=user, token=token)

@app.route('/settings', methods=['GET', 'POST'])
@optional_login_required
def settings():
    """Settings page for editing API keys"""
    env_file_path = os.path.join(os.path.dirname(__file__), 'capturecare.env')
    
    if request.method == 'POST':
        logger.info("Settings save attempt")
        
        # Build the new env file content - preserve existing values if form field is empty
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
            # Preserve spaces in password - Gmail app passwords can contain spaces
            'SMTP_PASSWORD': request.form.get('SMTP_PASSWORD', '') or os.getenv('SMTP_PASSWORD', ''),
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
                        # Preserve spaces in passwords - quote if contains spaces or special chars
                        if key == 'SMTP_PASSWORD' and (' ' in value or '"' in value or "'" in value):
                            # Escape quotes and wrap in double quotes
                            escaped_value = value.replace('\\', '\\\\').replace('"', '\\"')
                            f.write(f'{key}="{escaped_value}"\n')
                        else:
                            f.write(f"{key}={value}\n")
                        # Also set in current environment immediately
                        os.environ[key] = value
                        # Update app.config immediately so video token generation works
                        app.config[key] = value
                        logger.info(f"Set {key} in environment and app.config")
            
            # Reload notification service credentials immediately
            notification_service.reload_credentials()
            
            # Save notification templates
            try:
                from models import NotificationTemplate
                
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
        
        return redirect(url_for('settings'))
    
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
    if calendar_sync:
        try:
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

@app.route('/user-management')
@optional_login_required
def user_management():
    """User management page - admin only"""
    if not current_user.is_admin:
        flash('You must be an administrator to access user management.', 'error')
        return redirect(url_for('index'))
    
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('user_management.html', users=users)

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
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <h2 style="color: #00698f;">Welcome to CaptureCare!</h2>
                <p>Hello {new_user.first_name or new_user.username},</p>
                <p>An account has been created for you on CaptureCare. Please set your password to get started.</p>
                <p><strong>Your username:</strong> {new_user.username}</p>
                <p><strong>Your email:</strong> {new_user.email}</p>
                <p>Click the button below to set your password:</p>
                <p style="margin: 30px 0;">
                    <a href="{setup_url}" style="background-color: #00698f; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Set Password</a>
                </p>
                <p style="color: #666; font-size: 14px;">Or copy and paste this link into your browser:<br>{setup_url}</p>
                <p style="color: #666; font-size: 14px;">This link will expire in 7 days.</p>
                <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                <p style="color: #999; font-size: 12px;">If you did not expect this email, please contact your administrator.</p>
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

@app.route('/my-availability')
@optional_login_required
def my_availability():
    """User availability management page"""
    return render_template('my_availability_v2.html')

@app.route('/api/my-availability', methods=['GET'])
@optional_login_required
def get_my_availability():
    """Get current user's availability slots"""
    try:
        from models import UserAvailability
        availability = UserAvailability.query.filter_by(user_id=current_user.id).all()
        
        return jsonify({
            'success': True,
            'availability': [{
                'id': slot.id,
                'day_of_week': slot.day_of_week,
                'start_time': slot.start_time.strftime('%H:%M') if slot.start_time else None,
                'end_time': slot.end_time.strftime('%H:%M') if slot.end_time else None,
                'is_recurring': slot.is_recurring,
                'specific_date': slot.specific_date.isoformat() if slot.specific_date else None
            } for slot in availability]
        })
    except Exception as e:
        logger.error(f"Error getting availability: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/my-availability', methods=['POST'])
@optional_login_required
def add_my_availability():
    """Add availability slot for current user"""
    try:
        from models import UserAvailability
        data = request.get_json()
        
        # Server-side validation
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        if 'day_of_week' not in data or data['day_of_week'] == '':
            return jsonify({'success': False, 'error': 'Day of week is required'}), 400
        
        if 'start_time' not in data or not data['start_time']:
            return jsonify({'success': False, 'error': 'Start time is required'}), 400
        
        if 'end_time' not in data or not data['end_time']:
            return jsonify({'success': False, 'error': 'End time is required'}), 400
        
        # Validate day_of_week
        try:
            day_of_week = int(data['day_of_week'])
            if not 0 <= day_of_week <= 6:
                return jsonify({'success': False, 'error': 'Day of week must be between 0 and 6'}), 400
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid day of week format'}), 400
        
        # Parse and validate times
        from datetime import time
        try:
            start_h, start_m = map(int, data['start_time'].split(':'))
            start_time = time(start_h, start_m)
        except (ValueError, AttributeError):
            return jsonify({'success': False, 'error': 'Invalid start time format'}), 400
        
        try:
            end_h, end_m = map(int, data['end_time'].split(':'))
            end_time = time(end_h, end_m)
        except (ValueError, AttributeError):
            return jsonify({'success': False, 'error': 'Invalid end time format'}), 400
        
        # Validate that end time is after start time
        if end_time <= start_time:
            return jsonify({'success': False, 'error': 'End time must be after start time'}), 400
        
        new_slot = UserAvailability(
            user_id=current_user.id,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            is_recurring=data.get('is_recurring', True)
        )
        
        db.session.add(new_slot)
        db.session.commit()
        
        logger.info(f"User {current_user.username} added availability: {day_of_week} {start_time}-{end_time}")
        
        return jsonify({
            'success': True,
            'slot': {
                'id': new_slot.id,
                'day_of_week': new_slot.day_of_week,
                'start_time': new_slot.start_time.strftime('%H:%M'),
                'end_time': new_slot.end_time.strftime('%H:%M'),
                'is_recurring': new_slot.is_recurring
            }
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding availability: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/my-availability/<int:slot_id>', methods=['DELETE'])
@optional_login_required
def delete_my_availability(slot_id):
    """Delete availability slot"""
    try:
        from models import UserAvailability
        slot = UserAvailability.query.filter_by(id=slot_id, user_id=current_user.id).first()
        
        if not slot:
            return jsonify({'success': False, 'error': 'Availability slot not found'}), 404
        
        db.session.delete(slot)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Availability slot deleted'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting availability: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/availability-patterns', methods=['GET'])
@optional_login_required
def get_availability_patterns():
    """Get all availability patterns for current user"""
    try:
        from models import AvailabilityPattern
        patterns = AvailabilityPattern.query.filter_by(user_id=current_user.id).all()
        
        return jsonify({
            'success': True,
            'patterns': [{
                'id': p.id,
                'title': p.title,
                'frequency': p.frequency,
                'weekdays': p.weekdays,
                'start_time': p.start_time.strftime('%H:%M') if p.start_time else None,
                'end_time': p.end_time.strftime('%H:%M') if p.end_time else None,
                'valid_from': p.valid_from.isoformat() if p.valid_from else None,
                'valid_until': p.valid_until.isoformat() if p.valid_until else None,
                'is_active': p.is_active,
                'color': p.color,
                'notes': p.notes
            } for p in patterns]
        })
    except Exception as e:
        logger.error(f"Error getting patterns: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/availability-patterns', methods=['POST'])
@optional_login_required
def create_availability_pattern():
    """Create a new availability pattern"""
    try:
        from models import AvailabilityPattern
        from datetime import time, date
        data = request.get_json()
        
        if not data.get('title'):
            return jsonify({'success': False, 'error': 'Title is required'}), 400
        
        if not data.get('frequency'):
            return jsonify({'success': False, 'error': 'Frequency is required'}), 400
        
        if not data.get('start_time') or not data.get('end_time'):
            return jsonify({'success': False, 'error': 'Start and end times are required'}), 400
        
        start_h, start_m = map(int, data['start_time'].split(':'))
        start_time = time(start_h, start_m)
        
        end_h, end_m = map(int, data['end_time'].split(':'))
        end_time = time(end_h, end_m)
        
        if end_time <= start_time:
            return jsonify({'success': False, 'error': 'End time must be after start time'}), 400
        
        valid_from = None
        valid_until = None
        if data.get('valid_from'):
            valid_from = date.fromisoformat(data['valid_from'])
        if data.get('valid_until'):
            valid_until = date.fromisoformat(data['valid_until'])
        
        pattern = AvailabilityPattern(
            user_id=current_user.id,
            title=data['title'],
            frequency=data['frequency'],
            weekdays=data.get('weekdays'),
            start_time=start_time,
            end_time=end_time,
            valid_from=valid_from,
            valid_until=valid_until,
            is_active=data.get('is_active', True),
            color=data.get('color'),
            notes=data.get('notes')
        )
        
        db.session.add(pattern)
        db.session.commit()
        
        logger.info(f"User {current_user.username} created pattern: {pattern.title}")
        
        return jsonify({
            'success': True,
            'pattern': {
                'id': pattern.id,
                'title': pattern.title,
                'frequency': pattern.frequency,
                'weekdays': pattern.weekdays,
                'start_time': pattern.start_time.strftime('%H:%M'),
                'end_time': pattern.end_time.strftime('%H:%M')
            }
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating pattern: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/availability-patterns/<int:pattern_id>', methods=['PUT'])
@optional_login_required
def update_availability_pattern(pattern_id):
    """Update an existing availability pattern"""
    try:
        from models import AvailabilityPattern
        from datetime import time, date
        
        pattern = AvailabilityPattern.query.filter_by(id=pattern_id, user_id=current_user.id).first()
        
        if not pattern:
            return jsonify({'success': False, 'error': 'Pattern not found'}), 404
        
        data = request.get_json()
        
        # Update basic fields
        if data.get('title'):
            pattern.title = data['title']
        
        if data.get('frequency'):
            pattern.frequency = data['frequency']
        
        if 'weekdays' in data:
            pattern.weekdays = data.get('weekdays')
        
        # Update times
        if data.get('start_time'):
            start_h, start_m = map(int, data['start_time'].split(':'))
            pattern.start_time = time(start_h, start_m)
        
        if data.get('end_time'):
            end_h, end_m = map(int, data['end_time'].split(':'))
            pattern.end_time = time(end_h, end_m)
            
            # Validate times
            if pattern.start_time and pattern.end_time and pattern.end_time <= pattern.start_time:
                return jsonify({'success': False, 'error': 'End time must be after start time'}), 400
        
        # Update validity period
        if 'valid_from' in data:
            pattern.valid_from = date.fromisoformat(data['valid_from']) if data['valid_from'] else None
        
        if 'valid_until' in data:
            pattern.valid_until = date.fromisoformat(data['valid_until']) if data['valid_until'] else None
        
        # Update status
        if 'is_active' in data:
            pattern.is_active = data['is_active']
        
        if 'color' in data:
            pattern.color = data.get('color')
        
        if 'notes' in data:
            pattern.notes = data.get('notes')
        
        db.session.commit()
        
        logger.info(f"User {current_user.username} updated pattern {pattern_id}: {pattern.title}")
        
        return jsonify({
            'success': True,
            'pattern': {
                'id': pattern.id,
                'title': pattern.title,
                'frequency': pattern.frequency,
                'weekdays': pattern.weekdays,
                'start_time': pattern.start_time.strftime('%H:%M'),
                'end_time': pattern.end_time.strftime('%H:%M'),
                'valid_from': pattern.valid_from.isoformat() if pattern.valid_from else None,
                'valid_until': pattern.valid_until.isoformat() if pattern.valid_until else None,
                'is_active': pattern.is_active
            }
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating pattern: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/availability-patterns/<int:pattern_id>', methods=['DELETE'])
@optional_login_required
def delete_availability_pattern(pattern_id):
    """Delete an availability pattern"""
    try:
        from models import AvailabilityPattern
        pattern = AvailabilityPattern.query.filter_by(id=pattern_id, user_id=current_user.id).first()
        
        if not pattern:
            return jsonify({'success': False, 'error': 'Pattern not found'}), 404
        
        db.session.delete(pattern)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Pattern deleted successfully'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting pattern: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/availability-exceptions', methods=['GET'])
@optional_login_required
def get_availability_exceptions():
    """Get all availability exceptions (holidays/blocked dates) for current user or specified user_id"""
    try:
        from models import AvailabilityException
        user_id = request.args.get('user_id')
        
        # If user_id provided, use it; otherwise use current_user
        if user_id:
            user_id = int(user_id)
            exceptions = AvailabilityException.query.filter_by(user_id=user_id).all()
        else:
            exceptions = AvailabilityException.query.filter_by(user_id=current_user.id).all()
        
        return jsonify({
            'success': True,
            'exceptions': [{
                'id': e.id,
                'exception_date': e.exception_date.isoformat(),
                'exception_type': e.exception_type,
                'is_all_day': e.is_all_day,
                'start_time': e.start_time.strftime('%H:%M') if e.start_time else None,
                'end_time': e.end_time.strftime('%H:%M') if e.end_time else None,
                'reason': e.reason
            } for e in exceptions]
        })
    except Exception as e:
        logger.error(f"Error getting exceptions: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/availability-exceptions', methods=['POST'])
@optional_login_required
def create_availability_exception():
    """Create a new availability exception (holiday/blocked date) - supports date ranges"""
    try:
        from models import AvailabilityException
        from datetime import time, date, timedelta
        data = request.get_json()
        
        is_range = data.get('is_range', False)
        
        # Handle date range
        if is_range:
            if not data.get('from_date') or not data.get('to_date'):
                return jsonify({'success': False, 'error': 'From and to dates are required for range'}), 400
            
            from_date = date.fromisoformat(data['from_date'])
            to_date = date.fromisoformat(data['to_date'])
            
            if to_date < from_date:
                return jsonify({'success': False, 'error': 'End date must be after start date'}), 400
        else:
            if not data.get('exception_date'):
                return jsonify({'success': False, 'error': 'Date is required'}), 400
            
            from_date = date.fromisoformat(data['exception_date'])
            to_date = from_date
        
        # Parse times if partial day
        start_time = None
        end_time = None
        is_all_day = data.get('is_all_day', True)
        
        if not is_all_day:
            if not data.get('start_time') or not data.get('end_time'):
                return jsonify({'success': False, 'error': 'Start and end times required for partial day blocks'}), 400
            
            h, m = map(int, data['start_time'].split(':'))
            start_time = time(h, m)
            
            h, m = map(int, data['end_time'].split(':'))
            end_time = time(h, m)
        
        # Create exceptions for each date in range
        exceptions_created = []
        current_date = from_date
        while current_date <= to_date:
            exception = AvailabilityException(
                user_id=current_user.id,
                exception_date=current_date,
                exception_type=data.get('exception_type', 'blocked'),
                is_all_day=is_all_day,
                start_time=start_time,
                end_time=end_time,
                reason=data.get('reason')
            )
            db.session.add(exception)
            exceptions_created.append(exception)
            current_date += timedelta(days=1)
        
        db.session.commit()
        
        logger.info(f"User {current_user.username} created {len(exceptions_created)} exception(s) from {from_date} to {to_date}")
        
        return jsonify({
            'success': True,
            'count': len(exceptions_created),
            'message': f'{len(exceptions_created)} date(s) blocked successfully'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating exception: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/availability-exceptions/<int:exception_id>', methods=['DELETE'])
@optional_login_required
def delete_availability_exception(exception_id):
    """Delete an availability exception"""
    try:
        from models import AvailabilityException
        exception = AvailabilityException.query.filter_by(id=exception_id, user_id=current_user.id).first()
        
        if not exception:
            return jsonify({'success': False, 'error': 'Exception not found'}), 404
        
        db.session.delete(exception)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Exception deleted successfully'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting exception: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/users/practitioners')
@optional_login_required
def api_get_practitioners():
    """Get all active users (practitioners/nurses) with their colors"""
    try:
        users = User.query.filter_by(is_active=True).order_by(User.first_name).all()
        
        user_list = []
        for user in users:
            user_list.append({
                'id': user.id,
                'name': user.full_name,
                'role': user.role,
                'color': user.calendar_color
            })
        
        return jsonify({'success': True, 'users': user_list})
    except Exception as e:
        logger.error(f"Error fetching practitioners: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/public-holidays')
@optional_login_required
def api_public_holidays():
    """Get Australian public holidays for the current year and next year"""
    try:
        from datetime import date, timedelta
        
        current_year = date.today().year
        holidays = []
        
        # Australian public holidays (nationwide)
        # Format: (month, day, name)
        au_holidays_template = [
            (1, 1, "New Year's Day"),
            (1, 26, "Australia Day"),
            (4, 25, "ANZAC Day"),
            (12, 25, "Christmas Day"),
            (12, 26, "Boxing Day")
        ]
        
        # Generate holidays for current year and next year
        for year in [current_year, current_year + 1]:
            for month, day, name in au_holidays_template:
                holidays.append({
                    'date': f'{year}-{month:02d}-{day:02d}',
                    'name': name,
                    'type': 'public_holiday'
                })
            
            # Easter-related holidays (approximate - would need proper calculation)
            # Good Friday (varies, approximate for 2025-2026)
            if year == 2025:
                holidays.append({'date': '2025-04-18', 'name': 'Good Friday', 'type': 'public_holiday'})
                holidays.append({'date': '2025-04-21', 'name': 'Easter Monday', 'type': 'public_holiday'})
            elif year == 2026:
                holidays.append({'date': '2026-04-03', 'name': 'Good Friday', 'type': 'public_holiday'})
                holidays.append({'date': '2026-04-06', 'name': 'Easter Monday', 'type': 'public_holiday'})
            
            # Queen's Birthday (second Monday in June)
            june_1 = date(year, 6, 1)
            days_to_monday = (7 - june_1.weekday()) % 7
            if days_to_monday == 0:
                days_to_monday = 7
            first_monday = june_1 + timedelta(days=days_to_monday)
            second_monday = first_monday + timedelta(days=7)
            holidays.append({
                'date': second_monday.isoformat(),
                'name': "King's Birthday",
                'type': 'public_holiday'
            })
        
        return jsonify({
            'success': True,
            'holidays': holidays
        })
    except Exception as e:
        logger.error(f"Error fetching public holidays: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/team-availability')
@optional_login_required
def api_team_availability():
    """Get availability patterns and exceptions for selected users"""
    try:
        from models import AvailabilityPattern, AvailabilityException
        
        # Get user filter from query params
        user_ids_str = request.args.get('users', '')
        user_ids = [int(uid) for uid in user_ids_str.split(',') if uid.strip()] if user_ids_str else []
        
        # Query patterns
        pattern_query = AvailabilityPattern.query.join(User).filter(User.is_active == True)
        if user_ids:
            pattern_query = pattern_query.filter(AvailabilityPattern.user_id.in_(user_ids))
        
        patterns = pattern_query.all()
        
        # Query exceptions
        exception_query = AvailabilityException.query.join(User).filter(User.is_active == True)
        if user_ids:
            exception_query = exception_query.filter(AvailabilityException.user_id.in_(user_ids))
        
        exceptions = exception_query.all()
        
        # Format patterns
        pattern_list = []
        for pattern in patterns:
            pattern_list.append({
                'id': pattern.id,
                'user_id': pattern.user_id,
                'user_name': pattern.user.full_name,
                'user_color': pattern.user.calendar_color,
                'title': pattern.title,
                'frequency': pattern.frequency,
                'weekdays': pattern.weekdays,
                'start_time': pattern.start_time.strftime('%H:%M') if pattern.start_time else None,
                'end_time': pattern.end_time.strftime('%H:%M') if pattern.end_time else None,
                'valid_from': pattern.valid_from.isoformat() if pattern.valid_from else None,
                'valid_until': pattern.valid_until.isoformat() if pattern.valid_until else None,
                'is_active': pattern.is_active
            })
        
        # Format exceptions
        exception_list = []
        for exception in exceptions:
            exception_list.append({
                'id': exception.id,
                'user_id': exception.user_id,
                'user_name': exception.user.full_name,
                'date': exception.exception_date.isoformat(),
                'exception_type': exception.exception_type,
                'is_all_day': exception.is_all_day,
                'start_time': exception.start_time.strftime('%H:%M') if exception.start_time else None,
                'end_time': exception.end_time.strftime('%H:%M') if exception.end_time else None,
                'reason': exception.reason
            })
        
        return jsonify({
            'success': True,
            'patterns': pattern_list,
            'exceptions': exception_list
        })
    except Exception as e:
        logger.error(f"Error fetching team availability: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/patients')
@optional_login_required
def patients_list():
    patients = Patient.query.all()
    logger.info(f"📋 Patients list route: Found {len(patients)} patients")
    if patients:
        for p in patients[:3]:  # Log first 3
            logger.info(f"  - Patient {p.id}: {p.first_name} {p.last_name} ({p.email})")
    else:
        logger.warning("⚠️ No patients found in database query!")
    return render_template('patients.html', patients=patients)

@app.route('/communications')
@optional_login_required
def communications():
    """Central communications page showing all SMS and email correspondence"""
    return render_template('communications.html')

@app.route('/patients/add', methods=['GET', 'POST'])
@optional_login_required
def add_patient():
    if request.method == 'POST':
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        dob_str = request.form.get('date_of_birth')
        
        date_of_birth = datetime.strptime(dob_str, '%Y-%m-%d').date() if dob_str else None
        
        patient = Patient(
            first_name=first_name,
            last_name=last_name,
            email=email,
            date_of_birth=date_of_birth
        )
        
        db.session.add(patient)
        db.session.commit()
        
        if cliniko:
            cliniko_id = cliniko.match_patient(patient)
            if cliniko_id:
                patient.cliniko_patient_id = cliniko_id
                db.session.commit()
                flash(f'Patient linked to Cliniko ID: {cliniko_id}', 'success')
        
        flash(f'Patient {first_name} {last_name} added successfully!', 'success')
        return redirect(url_for('patient_detail', patient_id=patient.id))
    
    return render_template('add_patient.html')

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
    
    # Query health data within date range
    health_data = HealthData.query.filter(
        HealthData.patient_id == patient_id,
        HealthData.timestamp >= start_date,
        HealthData.timestamp < end_date
    ).order_by(HealthData.timestamp.asc()).all()
    
    devices = Device.query.filter_by(patient_id=patient_id).all()
    
    # Organize health data by type with chronological order
    health_summary = {}
    latest_values = {}
    
    for data in health_data:
        if data.measurement_type not in health_summary:
            health_summary[data.measurement_type] = []
        health_summary[data.measurement_type].append({
            'value': data.value,
            'unit': data.unit,
            'timestamp': data.timestamp.isoformat(),
            'timestamp_display': data.timestamp.strftime('%Y-%m-%d %H:%M')
        })
        # Track latest value
        latest_values[data.measurement_type] = {
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
    target_ranges = TargetRange.query.filter_by(patient_id=patient_id).all()
    target_ranges_dict = {}
    for tr in target_ranges:
        target_ranges_dict[tr.measurement_type] = {
            'min': tr.min_value if tr.min_value is not None else '',
            'max': tr.max_value if tr.max_value is not None else '',
            'target': tr.target_value if tr.target_value is not None else ''
        }
    
    # Get all active practitioners for appointment booking
    practitioners = User.query.filter_by(is_active=True).order_by(User.first_name).all()
    
    # Get public base URL for video room links
    base_url = app.config.get('BASE_URL', '') or os.getenv('BASE_URL', '') or os.getenv('PUBLIC_URL', '')
    
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
                         today=datetime.now().strftime('%Y-%m-%d'))

@app.route('/video-room/<room_name>')
def video_room_patient(room_name):
    """Public page for patients to join video consultation"""
    # Reload .env file to get latest settings
    from dotenv import load_dotenv
    env_file_path = os.path.join(os.path.dirname(__file__), 'capturecare.env')
    if os.path.exists(env_file_path):
        load_dotenv(env_file_path, override=True)
    
    # Get credentials from environment (most up-to-date)
    account_sid = os.getenv('TWILIO_ACCOUNT_SID', '') or app.config.get('TWILIO_ACCOUNT_SID', '')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN', '') or app.config.get('TWILIO_AUTH_TOKEN', '')
    api_key_sid = os.getenv('TWILIO_API_KEY_SID', '') or app.config.get('TWILIO_API_KEY_SID', '')
    api_key_secret = os.getenv('TWILIO_API_KEY_SECRET', '') or app.config.get('TWILIO_API_KEY_SECRET', '')
    
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

@app.route('/api/patients/<int:patient_id>/target-ranges', methods=['GET'])
@optional_login_required
def get_target_ranges(patient_id):
    """Get all target ranges for a patient"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        target_ranges = TargetRange.query.filter_by(patient_id=patient_id).all()
        
        ranges_list = []
        for tr in target_ranges:
            ranges_list.append({
                'id': tr.id,
                'measurement_type': tr.measurement_type,
                'target_mode': tr.target_mode,
                'min_value': tr.min_value,
                'max_value': tr.max_value,
                'target_value': tr.target_value,
                'unit': tr.unit,
                'source': tr.source,
                'auto_apply_ai': tr.auto_apply_ai,
                'suggested_min': tr.suggested_min,
                'suggested_max': tr.suggested_max,
                'suggested_value': tr.suggested_value,
                'last_ai_generated_at': tr.last_ai_generated_at.isoformat() if tr.last_ai_generated_at else None
            })
        
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
            
            existing = TargetRange.query.filter_by(
                patient_id=patient_id,
                measurement_type=measurement_type
            ).first()
            
            if existing:
                existing.target_mode = target_mode
                existing.min_value = min_val
                existing.max_value = max_val
                existing.target_value = target_val
                existing.unit = unit
                existing.source = source
                existing.auto_apply_ai = auto_apply
                existing.updated_at = datetime.utcnow()
            else:
                new_range = TargetRange(
                    patient_id=patient_id,
                    measurement_type=measurement_type,
                    target_mode=target_mode,
                    min_value=min_val,
                    max_value=max_val,
                    target_value=target_val,
                    unit=unit,
                    source=source,
                    auto_apply_ai=auto_apply
                )
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
        
        query = HealthData.query.filter(
            HealthData.patient_id == patient_id,
            HealthData.measurement_type == 'heart_rate'
        )
        
        if device_source == 'scale_or_null':
            query = query.filter(
                db.or_(
                    HealthData.device_source == 'scale',
                    HealthData.device_source.is_(None)
                )
            )
        elif device_source != 'all':
            query = query.filter_by(device_source=device_source)
        
        if date_str:
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
        
        dates_query = db.session.query(
            db.func.date(HealthData.timestamp).label('date')
        ).filter(
            HealthData.patient_id == patient_id,
            HealthData.measurement_type == 'heart_rate'
        )
        
        if device_source == 'scale_or_null':
            dates_query = dates_query.filter(
                db.or_(
                    HealthData.device_source == 'scale',
                    HealthData.device_source.is_(None)
                )
            )
        elif device_source != 'all':
            dates_query = dates_query.filter_by(device_source=device_source)
        
        available_dates = [str(d.date) for d in dates_query.distinct().order_by(db.text('date')).all()]
        
        return jsonify({
            'data': data,
            'available_dates': available_dates,
            'current_date': date_str if date_str else None
        })
    
    except Exception as e:
        logger.error(f"Error fetching heart rate data: {e}")
        return jsonify({'error': str(e)}), 400

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
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
        except ValueError:
            start_date = datetime.now() - timedelta(days=30)
            end_date = datetime.now()
        
        daily_data = db.session.query(
            db.func.date(HealthData.timestamp).label('date'),
            db.func.min(HealthData.value).label('min_hr'),
            db.func.max(HealthData.value).label('max_hr'),
            db.func.avg(HealthData.value).label('avg_hr')
        ).filter(
            HealthData.patient_id == patient_id,
            HealthData.device_source == 'watch',
            HealthData.measurement_type == 'heart_rate',
            HealthData.timestamp >= start_date,
            HealthData.timestamp < end_date
        ).group_by(
            db.func.date(HealthData.timestamp)
        ).order_by(db.text('date')).all()
        
        data = [{
            'date': str(d.date),
            'min': d.min_hr,
            'max': d.max_hr,
            'avg': round(d.avg_hr, 1)
        } for d in daily_data]
        
        return jsonify({'data': data})
    
    except Exception as e:
        logger.error(f"Error fetching daily min/max heart rate: {e}")
        return jsonify({'error': str(e)}), 400

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
    
    return redirect(url_for('patients_list'))

@app.route('/patients/<int:patient_id>/reset-withings', methods=['POST'])
@optional_login_required
def reset_withings(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    withings_auth.reset_patient_connection(patient_id)
    flash('Withings connection reset. Please revoke the app at https://account.withings.com/partner/apps then reconnect.', 'info')
    return redirect(url_for('patient_detail', patient_id=patient_id))

@app.route('/patients/<int:patient_id>/authorize-withings')
@optional_login_required
def authorize_withings(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    session['patient_id'] = patient_id
    
    auth_url = withings_auth.get_authorization_url(patient_id=patient_id)
    return redirect(auth_url)

@app.route('/api/patients/<int:patient_id>/send-withings-email', methods=['POST'])
@optional_login_required
def send_withings_email(patient_id):
    """Send Withings connection link to patient via email"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        
        if not patient.email:
            return jsonify({'success': False, 'error': 'Patient email not set'}), 400
        
        # Generate the Withings authorization URL
        auth_url = withings_auth.get_authorization_url(patient_id=patient_id)
        
        # Create branded HTML email
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f3f4f6;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f3f4f6; padding: 40px 20px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); overflow: hidden;">
                    <!-- Header with gradient -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #14b8a6 0%, #0d9488 100%); padding: 40px 30px; text-align: center;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 32px; font-weight: bold; letter-spacing: -0.5px;">
                                CaptureCare®
                            </h1>
                            <p style="margin: 10px 0 0 0; color: #e0f2f1; font-size: 16px;">
                                Humanising Digital Health
                            </p>
                        </td>
                    </tr>
                    
                    <!-- Main content -->
                    <tr>
                        <td style="padding: 40px 30px;">
                            <h2 style="margin: 0 0 20px 0; color: #1f2937; font-size: 24px; font-weight: 600;">
                                Hi {patient.first_name},
                            </h2>
                            
                            <p style="margin: 0 0 20px 0; color: #4b5563; font-size: 16px; line-height: 1.6;">
                                We're excited to help you track your health data! To get started, we need to connect your Withings device to your CaptureCare account.
                            </p>
                            
                            <!-- Feature boxes -->
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin: 30px 0;">
                                <tr>
                                    <td style="background-color: #ecfdf5; border-left: 4px solid #14b8a6; padding: 20px; border-radius: 8px;">
                                        <h3 style="margin: 0 0 12px 0; color: #0d9488; font-size: 18px; font-weight: 600;">
                                            📊 What You'll Get
                                        </h3>
                                        <ul style="margin: 0; padding-left: 20px; color: #374151;">
                                            <li style="margin-bottom: 8px;">Real-time health monitoring</li>
                                            <li style="margin-bottom: 8px;">AI-powered health insights</li>
                                            <li style="margin-bottom: 8px;">Personalized health reports</li>
                                            <li style="margin-bottom: 0;">Secure data synchronization</li>
                                        </ul>
                                    </td>
                                </tr>
                            </table>
                            
                            <p style="margin: 30px 0 20px 0; color: #4b5563; font-size: 16px; line-height: 1.6;">
                                Click the button below to securely connect your Withings account:
                            </p>
                            
                            <!-- CTA Button -->
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin: 30px 0;">
                                <tr>
                                    <td align="center">
                                        <a href="{auth_url}" style="display: inline-block; background: linear-gradient(135deg, #14b8a6 0%, #0d9488 100%); color: #ffffff; text-decoration: none; padding: 16px 40px; border-radius: 8px; font-weight: 600; font-size: 16px; box-shadow: 0 4px 6px rgba(20, 184, 166, 0.3);">
                                            🔗 Connect Your Withings Device
                                        </a>
                                    </td>
                                </tr>
                            </table>
                            
                            <!-- Instructions -->
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin: 30px 0; background-color: #f9fafb; border-radius: 8px; padding: 20px;">
                                <tr>
                                    <td>
                                        <h3 style="margin: 0 0 15px 0; color: #1f2937; font-size: 16px; font-weight: 600;">
                                            📝 What Happens Next?
                                        </h3>
                                        <ol style="margin: 0; padding-left: 20px; color: #4b5563; line-height: 1.8;">
                                            <li>Click the button above</li>
                                            <li>Log into your Withings account</li>
                                            <li>Authorize CaptureCare to access your health data</li>
                                            <li>You'll be redirected back to CaptureCare automatically</li>
                                        </ol>
                                    </td>
                                </tr>
                            </table>
                            
                            <p style="margin: 30px 0 0 0; color: #6b7280; font-size: 14px; line-height: 1.6;">
                                <strong>Security Note:</strong> Your data is encrypted and securely stored. We only access the health information you authorize, and you can disconnect your device at any time.
                            </p>
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f9fafb; padding: 30px; text-align: center; border-top: 1px solid #e5e7eb;">
                            <p style="margin: 0 0 10px 0; color: #6b7280; font-size: 14px;">
                                Need help? Contact our support team
                            </p>
                            <p style="margin: 0; color: #9ca3af; font-size: 12px;">
                                © 2025 CaptureCare. All rights reserved.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
        """
        
        # Plain text version
        text_body = f"""
Hi {patient.first_name},

We're excited to help you track your health data! To get started, we need to connect your Withings device to your CaptureCare account.

What You'll Get:
• Real-time health monitoring
• AI-powered health insights
• Personalized health reports
• Secure data synchronization

Connect your Withings device by clicking this link:
{auth_url}

What Happens Next?
1. Click the link above
2. Log into your Withings account
3. Authorize CaptureCare to access your health data
4. You'll be redirected back to CaptureCare automatically

Security Note: Your data is encrypted and securely stored. We only access the health information you authorize, and you can disconnect your device at any time.

Need help? Contact our support team.

© 2025 CaptureCare. All rights reserved.
        """
        
        # Send the email
        try:
            success = notification_service.send_email(
                to_email=patient.email,
                subject=f"🔗 Connect Your Withings Device to CaptureCare",
                body_html=html_body,
                body_text=text_body,
                patient_id=patient_id,
                user_id=current_user.id
            )
            
            if success:
                logger.info(f"✅ Sent Withings connection email to patient {patient_id} ({patient.email})")
                return jsonify({'success': True, 'message': 'Email sent successfully'})
            else:
                logger.error(f"❌ Email sending returned False for patient {patient_id}")
                return jsonify({'success': False, 'error': 'Failed to send email - check server logs'}), 500
        except Exception as email_error:
            logger.error(f"❌ Exception in send_email: {email_error}")
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'error': f'Email error: {str(email_error)}'}), 500
            
    except Exception as e:
        logger.error(f"❌ Error sending Withings email to patient {patient_id}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/withings/callback')
def withings_callback():
    code = request.args.get('code')
    state = request.args.get('state')
    
    if not code:
        flash('Authorization failed - no code received', 'error')
        return redirect(url_for('index'))
    
    try:
        credentials = withings_auth.get_credentials(code, state)
        patient_id = credentials.userid if hasattr(credentials, 'userid') else session.get('patient_id')
        
        if state:
            patient_id_from_state = int(state.split('_')[0]) if '_' in state else None
            if patient_id_from_state:
                patient_id = patient_id_from_state
        
        if not patient_id:
            flash('Unable to identify patient', 'error')
            return redirect(url_for('index'))
        
        withings_auth.save_tokens(patient_id, credentials)
        
        flash('Withings device authorized successfully!', 'success')
        return redirect(url_for('patient_detail', patient_id=patient_id))
    
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Withings callback error: {error_msg}")
        
        if "Scope has changed" in error_msg or "scope" in error_msg.lower():
            withings_auth.reset_patient_connection(patient_id)
            flash('Scope configuration changed. Please go to https://account.withings.com/partner/apps and revoke "CaptureCare" app, then click Connect Withings again.', 'warning')
        else:
            flash(f'Authorization error: {error_msg}', 'error')
        
        return redirect(url_for('patient_detail', patient_id=patient_id))

@app.route('/api/patients/<int:patient_id>/sync-info', methods=['GET'])
@optional_login_required
def sync_patient_info(patient_id):
    """Get sync information (last record date, etc.)"""
    try:
        last_data = HealthData.query.filter_by(patient_id=patient_id).order_by(HealthData.timestamp.desc()).first()
        
        if last_data:
            return jsonify({
                'success': True,
                'last_record': {
                    'timestamp': last_data.timestamp.isoformat(),
                    'type': last_data.measurement_type
                }
            })
        else:
            return jsonify({
                'success': True,
                'last_record': None
            })
    except Exception as e:
        logger.error(f"Error getting sync info: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/patients/<int:patient_id>/sync', methods=['POST'])
@optional_login_required
def sync_patient(patient_id):
    # Auto-detect: get last sync date or pull all available data
    patient = Patient.query.get_or_404(patient_id)
    
    # Check if full sync is requested
    full_sync = request.form.get('full_sync') == 'true'
    
    if full_sync:
        # Force full sync: get all available data (last year)
        days_back = 365
        flash(f"⏳ Pulling ALL historical data (up to 1 year)...", 'info')
    else:
        # Check for last health data entry to determine incremental sync
        last_data = HealthData.query.filter_by(patient_id=patient_id).order_by(HealthData.timestamp.desc()).first()
        
        startdate = None
        if last_data:
            # Incremental sync: go back 1 day before last record to catch any missed data
            # This ensures we don't miss any data even if there were gaps
            startdate = last_data.timestamp - timedelta(days=1)
            days_back = min((datetime.now() - startdate).days + 1, 365)
            flash(f"⏳ Syncing new data from {startdate.strftime('%Y-%m-%d')} (1 day before last record on {last_data.timestamp.strftime('%Y-%m-%d')}) to catch any missed data...", 'info')
        else:
            # Initial sync: get all available data (last year)
            days_back = 365
            flash(f"⏳ Performing initial sync of all available data (up to 1 year)...", 'info')
    
    send_email = request.form.get('send_email') == 'true'
    
    # Pass startdate if we have it, otherwise use days_back
    if startdate:
        result = synchronizer.sync_patient_data(patient_id, startdate=startdate, send_email=send_email)
    else:
        result = synchronizer.sync_patient_data(patient_id, days_back=days_back, send_email=send_email)
    
    # Check if this is an AJAX request (from fetch API)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
        if result['success']:
            total_records = result.get('measurements', 0) + result.get('activities', 0) + result.get('sleep', 0)
            return jsonify({
                'success': True,
                'message': f'Sync complete! Added {result.get("measurements", 0)} measurements, {result.get("activities", 0)} activities, {result.get("sleep", 0)} sleep records ({total_records} total)',
                'measurements': result.get('measurements', 0),
                'activities': result.get('activities', 0),
                'sleep': result.get('sleep', 0),
                'total': total_records
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Unknown error')
            }), 400
    
    # Regular form submission - use flash messages and redirect
    if result['success']:
        total_records = result.get('measurements', 0) + result.get('activities', 0) + result.get('sleep', 0)
        flash(f"✅ Sync complete! Added {result.get('measurements', 0)} measurements, {result.get('activities', 0)} activities, {result.get('sleep', 0)} sleep records ({total_records} total)", 'success')
    else:
        flash(f"❌ Sync failed: {result.get('error', 'Unknown error')}", 'error')
    
    return redirect(url_for('patient_detail', patient_id=patient_id))

@app.route('/patients/<int:patient_id>/report', methods=['GET', 'POST'])
@optional_login_required
def generate_report(patient_id):
    """Legacy route - redirects to patient report"""
    return generate_patient_report(patient_id)

@app.route('/patients/<int:patient_id>/report/patient', methods=['POST'])
@optional_login_required
def generate_patient_report(patient_id):
    """Generate patient-friendly health report for email"""
    patient = Patient.query.get_or_404(patient_id)
    
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
    
    if not ai_reporter:
        flash('AI reporter not configured. Please add OpenAI API key.', 'error')
        return redirect(url_for('patient_detail', patient_id=patient_id))
    
    try:
        report = ai_reporter.generate_patient_report(patient, health_summary)
        report_type = 'Patient Report'
        
        send_email = request.form.get('send_email') == 'true'
        if send_email and email_sender:
            email_result = email_sender.send_health_report(
                to_email=patient.email,
                patient_name=f"{patient.first_name} {patient.last_name}",
                report_content=report
            )
            if email_result:
                flash(f'✅ Patient report generated and emailed to {patient.email}!', 'success')
            else:
                flash('⚠️ Report generated but email failed to send.', 'warning')
        else:
            flash('✅ Patient report generated successfully!', 'success')
        
        return render_template('health_report.html', 
                             patient=patient,
                             report=report,
                             report_type=report_type)
    except Exception as e:
        logger.error(f"Error generating patient report: {e}")
        flash(f'❌ Error generating report: {str(e)}', 'error')
        return redirect(url_for('patient_detail', patient_id=patient_id))

@app.route('/patients/<int:patient_id>/report/clinical', methods=['POST'])
@optional_login_required
def generate_clinical_note(patient_id):
    """Generate clinical treatment note and optionally post to Cliniko"""
    patient = Patient.query.get_or_404(patient_id)
    
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
    
    if not ai_reporter:
        flash('AI reporter not configured. Please add OpenAI API key.', 'error')
        return redirect(url_for('patient_detail', patient_id=patient_id))
    
    try:
        clinical_note = ai_reporter.generate_clinical_note(patient, health_summary)
        report_type = 'Clinical Note (SOAP Format)'
        
        post_to_cliniko = request.form.get('post_to_cliniko') == 'true'
        if post_to_cliniko and cliniko and patient.cliniko_patient_id:
            cliniko_result = cliniko.create_treatment_note(patient.cliniko_patient_id, clinical_note)
            if cliniko_result:
                flash(f'✅ Clinical note generated and posted to Cliniko!', 'success')
            else:
                flash('⚠️ Clinical note generated but Cliniko posting failed.', 'warning')
        elif post_to_cliniko and not patient.cliniko_patient_id:
            flash('⚠️ Patient not linked to Cliniko. Clinical note generated but not posted.', 'warning')
        else:
            flash('✅ Clinical note generated successfully!', 'success')
        
        return render_template('health_report.html', 
                             patient=patient,
                             report=clinical_note,
                             report_type=report_type)
    except Exception as e:
        logger.error(f"Error generating clinical note: {e}")
        flash(f'❌ Error generating clinical note: {str(e)}', 'error')
        return redirect(url_for('patient_detail', patient_id=patient_id))

@app.route('/patients/<int:patient_id>/report/video', methods=['POST'])
@optional_login_required
def generate_video_script(patient_id):
    """Generate video avatar script and optionally send via SMS"""
    patient = Patient.query.get_or_404(patient_id)
    
    health_data = HealthData.query.filter_by(patient_id=patient_id).order_by(HealthData.timestamp.desc()).limit(50).all()
    health_summary = {}
    for data in health_data:
        if data.measurement_type not in health_summary:
            health_summary[data.measurement_type] = []
        health_summary[data.measurement_type].append({
            'value': data.value,
            'unit': data.unit,
            'timestamp': data.timestamp
        })
    
    if not ai_reporter:
        flash('AI reporter not configured. Please add OpenAI API key.', 'error')
        return redirect(url_for('patient_detail', patient_id=patient_id))
    
    try:
        video_script = ai_reporter.generate_video_script(patient, health_summary)
        report_type = 'Video Avatar Script (60-90 seconds)'
        
        word_count = len(video_script.split())
        flash(f'✅ Video script generated ({word_count} words ~ {word_count//2.5:.0f} seconds)!', 'success')
        
        return render_template('health_report.html', 
                             patient=patient,
                             report=video_script,
                             report_type=report_type)
    except Exception as e:
        logger.error(f"Error generating video script: {e}")
        flash(f'❌ Error generating video script: {str(e)}', 'error')
        return redirect(url_for('patient_detail', patient_id=patient_id))

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
        db.or_(
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
                'timestamp': log.created_at.isoformat()
            })
        
        return jsonify({'logs': logs_data})
    except Exception as e:
        logger.error(f"Error fetching webhook logs: {e}")
        return jsonify({'logs': []})

@app.route('/patients/<int:patient_id>/appointments', methods=['GET'])
@optional_login_required
def list_appointments(patient_id):
    """Get all appointments for a patient"""
    patient = Patient.query.get_or_404(patient_id)
    appointments = Appointment.query.filter_by(patient_id=patient_id).order_by(Appointment.start_time.desc()).all()
    
    appointments_list = []
    for appt in appointments:
        appointments_list.append({
            'id': appt.id,
            'title': appt.title,
            'type': appt.appointment_type,
            'start_time': appt.start_time.isoformat(),
            'end_time': appt.end_time.isoformat(),
            'duration_minutes': appt.duration_minutes,
            'location': appt.location,
            'practitioner': appt.practitioner,
            'notes': appt.notes,
            'status': appt.status
        })
    
    return jsonify(appointments_list)

@app.route('/patients/<int:patient_id>/appointments', methods=['POST'])
@optional_login_required
def create_appointment(patient_id):
    """Create a new appointment for a patient"""
    patient = Patient.query.get_or_404(patient_id)
    
    try:
        data = request.get_json()
        
        title = data.get('title', f'Appointment with {patient.first_name} {patient.last_name}')
        start_time_str = data.get('start_time')
        duration_minutes = int(data.get('duration_minutes', 60))
        
        start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        appointment = Appointment(
            patient_id=patient_id,
            title=title,
            appointment_type=data.get('appointment_type'),
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration_minutes,
            location=data.get('location'),
            practitioner=data.get('practitioner'),
            notes=data.get('notes'),
            status='scheduled'
        )
        
        if calendar_sync and data.get('add_to_calendar', True):
            description = f"Patient: {patient.first_name} {patient.last_name}\nEmail: {patient.email}"
            if data.get('notes'):
                description += f"\n\nNotes: {data.get('notes')}"
            
            event_id = calendar_sync.create_event(
                summary=title,
                start_time=start_time,
                end_time=end_time,
                description=description,
                location=data.get('location'),
                attendees=[patient.email] if patient.email else None
            )
            
            if event_id:
                appointment.google_calendar_event_id = event_id
                logger.info(f"Appointment synced to Google Calendar: {event_id}")
        
        db.session.add(appointment)
        db.session.commit()
        
        notification_results = notification_service.send_appointment_confirmation(patient, appointment)
        
        notification_msg = []
        if notification_results['sms_sent']:
            notification_msg.append('SMS sent')
        if notification_results['email_sent']:
            notification_msg.append('Email sent')
        
        success_msg = 'Appointment created successfully!'
        if notification_msg:
            success_msg += f' ({", ".join(notification_msg)})'
        
        flash(success_msg, 'success')
        return jsonify({
            'success': True, 
            'appointment_id': appointment.id,
            'message': success_msg,
            'notifications': notification_results
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating appointment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/patients/<int:patient_id>/appointments/<int:appointment_id>', methods=['PUT'])
@optional_login_required
def update_appointment(patient_id, appointment_id):
    """Update an existing appointment"""
    patient = Patient.query.get_or_404(patient_id)
    appointment = Appointment.query.filter_by(id=appointment_id, patient_id=patient_id).first_or_404()
    
    try:
        data = request.get_json()
        send_email = data.get('send_email', False)
        
        if 'title' in data:
            appointment.title = data['title']
        
        if 'appointment_type' in data:
            appointment.appointment_type = data['appointment_type']
        
        if 'start_time' in data:
            start_time = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
            appointment.start_time = start_time
            appointment.end_time = start_time + timedelta(minutes=appointment.duration_minutes)
        
        if 'duration_minutes' in data:
            appointment.duration_minutes = int(data['duration_minutes'])
            appointment.end_time = appointment.start_time + timedelta(minutes=appointment.duration_minutes)
        
        if 'location' in data:
            appointment.location = data['location']
        
        if 'practitioner' in data:
            appointment.practitioner = data['practitioner']
        
        if 'notes' in data:
            appointment.notes = data['notes']
        
        if 'status' in data:
            appointment.status = data['status']
        
        if calendar_sync and appointment.google_calendar_event_id:
            calendar_sync.update_event(
                event_id=appointment.google_calendar_event_id,
                summary=appointment.title,
                start_time=appointment.start_time,
                end_time=appointment.end_time,
                location=appointment.location
            )
        
        db.session.commit()
        
        if send_email:
            notification_result = notification_service.send_appointment_update(patient, appointment)
            if notification_result['email_sent']:
                return jsonify({'success': True, 'message': 'Appointment updated successfully and email sent to patient'})
            else:
                return jsonify({'success': True, 'message': 'Appointment updated successfully but email could not be sent'})
        
        return jsonify({'success': True, 'message': 'Appointment updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating appointment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/patients/<int:patient_id>/appointments/<int:appointment_id>', methods=['DELETE'])
@optional_login_required
def delete_appointment(patient_id, appointment_id):
    """Delete an appointment"""
    patient = Patient.query.get_or_404(patient_id)
    appointment = Appointment.query.filter_by(id=appointment_id, patient_id=patient_id).first_or_404()
    
    try:
        if calendar_sync and appointment.google_calendar_event_id:
            calendar_sync.delete_event(appointment.google_calendar_event_id)
        
        db.session.delete(appointment)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Appointment deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting appointment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/patients/<int:patient_id>/invoices', methods=['GET'])
@optional_login_required
def get_patient_invoices(patient_id):
    """Get all invoices for a patient"""
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
        return redirect(url_for('patients_list'))
    
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
    
    return redirect(url_for('patients_list'))

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
                'appointment_id': note.appointment_id
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
        logger.error(f"Error getting patient notes: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/patients/<int:patient_id>/notes', methods=['POST'])
@optional_login_required
def create_patient_note(patient_id):
    """Create a new patient note"""
    try:
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
    """Delete a patient note"""
    try:
        note = PatientNote.query.get_or_404(note_id)
        db.session.delete(note)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting patient note: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

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
        from notification_service import NotificationService
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
                from notification_service import NotificationService
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
                from notification_service import NotificationService
                notif_service = NotificationService()
                
                # Convert plain text message to HTML for email
                html_message = message.replace('\n', '<br>')
                
                email_sent = notif_service.send_email(
                    to_email=patient.email,
                    subject="CaptureCare Patient App Invite",
                    body_html=f"<html><body>{html_message}</body></html>",
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
        from notification_service import NotificationService
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
            from notification_service import NotificationService
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
        from notification_service import NotificationService
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
            
            # Generate unique room name
            import uuid
            room_name = f"patient_{patient_id}_{uuid.uuid4().hex[:8]}"
            
            # Create access token for practitioner
            identity = f"practitioner_{current_user.id}"
            
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
                        from notification_service import NotificationService
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
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        
        # Build query
        query = PatientCorrespondence.query.filter_by(is_deleted=False)
        
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
        from patient_matcher import ClinikoIntegration
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
        from models import NotificationTemplate
        
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
    """Send edited health report with optional attachments via email and save to patient notes"""
    patient = Patient.query.get_or_404(patient_id)
    
    if not email_sender:
        return jsonify({'success': False, 'error': 'Email not configured. Please add SMTP settings.'}), 400
    
    try:
        # Get form data
        report_html = request.form.get('report_html')
        report_subject = request.form.get('subject', f"Health Report for {patient.first_name} {patient.last_name}")
        report_type = request.form.get('report_type', 'ai_report')
        
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
        
        # Send email
        email_result = email_sender.send_health_report(
            to_email=patient.email,
            patient_name=f"{patient.first_name} {patient.last_name}",
            report_content=report_html,
            subject=report_subject,
            attachments=attachments if attachments else None
        )
        
        if not email_result:
            logger.error(f"❌ Email sending failed for patient {patient_id}")
            return jsonify({'success': False, 'error': 'Failed to send email. Check server logs for details.'}), 400
        
        # Save to patient notes
        note = PatientNote(
            patient_id=patient_id,
            note_text=report_html,
            note_type=report_type,
            author='AI System'
        )
        db.session.add(note)
        db.session.commit()
        
        attachment_info = f" with {len(attachments)} attachment(s)" if attachments else ""
        
        return jsonify({
            'success': True,
            'message': f'Report sent to {patient.email}{attachment_info} and saved to patient notes',
            'note_id': note.id
        })
    except Exception as e:
        logger.error(f"Error sending report: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

# HeyGen Video Generation Endpoints
@app.route('/api/heygen/avatars', methods=['GET'])
@optional_login_required
def get_heygen_avatars():
    """Get available HeyGen avatars"""
    # Reload config to ensure secrets are loaded (for Cloud Run)
    from config import Config
    
    # Create a new Config instance to reload secrets from Secret Manager
    config_instance = Config()
    
    # Get API key from config (which loads from Secret Manager in Cloud Run)
    api_key = Config.HEYGEN_API_KEY or os.getenv('HEYGEN_API_KEY')
    if not api_key:
        logger.warning("⚠️  HeyGen API key not found in config or environment")
        logger.warning(f"Config.HEYGEN_API_KEY: {bool(Config.HEYGEN_API_KEY)}, os.getenv: {bool(os.getenv('HEYGEN_API_KEY'))}")
        logger.warning(f"USE_SECRET_MANAGER: {Config.USE_SECRET_MANAGER}, GCP_PROJECT_ID: {Config.GCP_PROJECT_ID}")
        return jsonify({'success': False, 'error': 'HeyGen API not configured'}), 400
    
    logger.info(f"🔑 Using HeyGen API key: {api_key[:20]}..." if len(api_key) > 20 else f"🔑 Using HeyGen API key")
    
    try:
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
    from config import Config
    
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
    from config import Config
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
    from config import Config
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
    from config import Config
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
    
    return render_template('dashboard.html', stats=stats, all_patients=all_patients)

# Master Calendar Routes
@app.route('/calendar')
@optional_login_required
def master_calendar():
    """Master calendar view showing all appointments"""
    patients = Patient.query.order_by(Patient.first_name).all()
    practitioners = User.query.filter_by(is_active=True).order_by(User.first_name).all()
    return render_template('calendar.html', patients=patients, practitioners=practitioners)

@app.route('/api/calendar/events', methods=['GET'])
@optional_login_required
def get_calendar_events():
    """Get all calendar events in FullCalendar format"""
    try:
        practitioner_id = request.args.get('practitioner_id')
        
        query = Appointment.query
        if practitioner_id:
            query = query.filter_by(practitioner_id=int(practitioner_id))
        
        appointments = query.all()
        events = [apt.to_calendar_event() for apt in appointments]
        
        return jsonify({'success': True, 'events': events})
    except Exception as e:
        logger.error(f"Error fetching calendar events: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/calendar/appointments', methods=['POST'])
@optional_login_required
def create_calendar_appointment():
    """Create new appointment from calendar"""
    try:
        data = request.get_json()
        
        # Parse date and time
        start_datetime = datetime.strptime(f"{data['date']} {data['time']}", '%Y-%m-%d %H:%M')
        duration_minutes = data.get('duration_minutes', 60)
        end_datetime = start_datetime + timedelta(minutes=duration_minutes)
        
        practitioner_id = data.get('practitioner_id')
        
        # Check for double booking if practitioner is specified
        if practitioner_id:
            conflicting_appointments = Appointment.query.filter(
                Appointment.practitioner_id == practitioner_id,
                Appointment.status != 'cancelled',
                db.or_(
                    # New appointment starts during existing appointment
                    db.and_(
                        Appointment.start_time <= start_datetime,
                        Appointment.end_time > start_datetime
                    ),
                    # New appointment ends during existing appointment
                    db.and_(
                        Appointment.start_time < end_datetime,
                        Appointment.end_time >= end_datetime
                    ),
                    # New appointment completely contains existing appointment
                    db.and_(
                        Appointment.start_time >= start_datetime,
                        Appointment.end_time <= end_datetime
                    )
                )
            ).all()
            
            if conflicting_appointments:
                conflict_info = ', '.join([f"{apt.title} at {apt.start_time.strftime('%I:%M %p')}" 
                                          for apt in conflicting_appointments[:3]])
                return jsonify({
                    'success': False,
                    'error': f'Time slot conflicts with existing appointment(s): {conflict_info}'
                }), 400
        
        # Validate availability
        if practitioner_id:
            target_date = start_datetime.date()
            patterns = AvailabilityPattern.query.filter_by(
                user_id=practitioner_id,
                is_active=True
            ).all()
            
            # Check if time falls within any availability pattern
            time_only = start_datetime.time()
            has_availability = False
            
            for pattern in patterns:
                # Check validity period
                if pattern.valid_from and target_date < pattern.valid_from:
                    continue
                if pattern.valid_until and target_date > pattern.valid_until:
                    continue
                
                # Check if pattern applies to this day
                day_of_week_num = target_date.weekday()
                applies = False
                if pattern.frequency == 'daily':
                    applies = True
                elif pattern.frequency == 'weekdays' and day_of_week_num < 5:
                    applies = True
                elif pattern.frequency in ['weekly', 'custom']:
                    if pattern.weekdays:
                        day_numbers = [int(d.strip()) for d in pattern.weekdays.split(',') if d.strip().isdigit()]
                        applies = day_of_week_num in day_numbers
                
                if applies and pattern.start_time <= time_only < pattern.end_time:
                    has_availability = True
                    break
            
            if not has_availability:
                return jsonify({
                    'success': False,
                    'error': 'Selected time is not within practitioner availability. Please select an available time slot.'
                }), 400
        
        appointment = Appointment(
            patient_id=data['patient_id'],
            practitioner_id=practitioner_id,
            title=data['title'],
            appointment_type=data.get('appointment_type', 'consultation'),
            start_time=start_datetime,
            end_time=end_datetime,
            duration_minutes=duration_minutes,
            location=data.get('location'),
            notes=data.get('notes'),
            status='scheduled'
        )
        
        db.session.add(appointment)
        db.session.commit()
        
        # Sync with Google Calendar if enabled
        if calendar_sync:
            try:
                patient = Patient.query.get(data['patient_id'])
                event_id = calendar_sync.create_appointment_event(patient, appointment)
                if event_id:
                    appointment.google_calendar_event_id = event_id
                    db.session.commit()
            except Exception as e:
                logger.warning(f"Google Calendar sync failed: {e}")
        
        # Send notifications
        if notification_service:
            try:
                patient = Patient.query.get(data['patient_id'])
                notification_service.send_appointment_confirmation(patient, appointment)
            except Exception as e:
                logger.warning(f"Notification send failed: {e}")
        
        return jsonify({
            'success': True,
            'appointment': appointment.to_calendar_event()
        })
    except Exception as e:
        logger.error(f"Error creating appointment: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/calendar/appointments/<int:appointment_id>', methods=['PUT'])
@optional_login_required
def update_calendar_appointment(appointment_id):
    """Update appointment from calendar"""
    try:
        appointment = Appointment.query.get_or_404(appointment_id)
        data = request.get_json()
        
        # Parse date and time if provided
        if 'date' in data and 'time' in data:
            start_datetime = datetime.strptime(f"{data['date']} {data['time']}", '%Y-%m-%d %H:%M')
            duration_minutes = data.get('duration_minutes', appointment.duration_minutes)
            end_datetime = start_datetime + timedelta(minutes=duration_minutes)
            
            appointment.start_time = start_datetime
            appointment.end_time = end_datetime
            appointment.duration_minutes = duration_minutes
        
        # Update other fields
        if 'patient_id' in data:
            appointment.patient_id = data['patient_id']
        if 'practitioner_id' in data:
            appointment.practitioner_id = data.get('practitioner_id')
        if 'title' in data:
            appointment.title = data['title']
        if 'appointment_type' in data:
            appointment.appointment_type = data['appointment_type']
        if 'location' in data:
            appointment.location = data['location']
        if 'notes' in data:
            appointment.notes = data['notes']
        
        db.session.commit()
        
        # Sync with Google Calendar
        if calendar_sync and appointment.google_calendar_event_id:
            try:
                calendar_sync.update_appointment_event(appointment.patient, appointment)
            except Exception as e:
                logger.warning(f"Google Calendar sync failed: {e}")
        
        return jsonify({
            'success': True,
            'appointment': appointment.to_calendar_event()
        })
    except Exception as e:
        logger.error(f"Error updating appointment: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/calendar/appointments/<int:appointment_id>/move', methods=['PUT'])
@optional_login_required
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
        if calendar_sync and appointment.google_calendar_event_id:
            try:
                calendar_sync.update_appointment_event(appointment.patient, appointment)
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

@app.route('/api/calendar/appointments/<int:appointment_id>/notify', methods=['POST'])
@optional_login_required
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
        notification_service = NotificationService()
        result = notification_service.send_sms(phone, message)
        
        if result.get('success'):
            return jsonify({'success': True, 'message': 'SMS sent successfully'})
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Failed to send SMS')}), 400
            
    except Exception as e:
        logger.error(f"Error sending notification: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/calendar/appointments/<int:appointment_id>', methods=['DELETE'])
@optional_login_required
def delete_calendar_appointment(appointment_id):
    """Delete appointment from calendar"""
    try:
        appointment = Appointment.query.get_or_404(appointment_id)
        
        # Delete from Google Calendar
        if calendar_sync and appointment.google_calendar_event_id:
            try:
                calendar_sync.delete_appointment_event(appointment.google_calendar_event_id)
            except Exception as e:
                logger.warning(f"Google Calendar delete failed: {e}")
        
        db.session.delete(appointment)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting appointment: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/calendar/availability-blocks', methods=['GET'])
@optional_login_required
def get_availability_blocks():
    """Get availability blocks for all practitioners for calendar display"""
    try:
        start_date_str = request.args.get('start')
        end_date_str = request.args.get('end')
        practitioner_id = request.args.get('practitioner_id')
        
        if not start_date_str or not end_date_str:
            return jsonify({'success': False, 'error': 'Start and end dates required'}), 400
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        # Get practitioners to show
        if practitioner_id:
            practitioners = [User.query.get(int(practitioner_id))]
        else:
            practitioners = User.query.filter_by(is_active=True).all()
        
        availability_blocks = []
        
        for practitioner in practitioners:
            # Get all active patterns
            patterns = AvailabilityPattern.query.filter_by(
                user_id=practitioner.id,
                is_active=True
            ).all()
            
            # Get exceptions in date range
            exceptions = AvailabilityException.query.filter(
                AvailabilityException.user_id == practitioner.id,
                AvailabilityException.exception_date >= start_date,
                AvailabilityException.exception_date <= end_date
            ).all()
            
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
                            if pattern.weekdays:
                                day_numbers = [int(d.strip()) for d in pattern.weekdays.split(',') if d.strip().isdigit()]
                                applies = day_of_week_num in day_numbers
                        
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
        logger.error(f"Error getting availability blocks: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/calendar/block-slot', methods=['POST'])
@optional_login_required
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
            from datetime import timedelta
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

@app.route('/api/calendar/availability/<int:practitioner_id>', methods=['GET'])
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
        
        # Get exceptions for this date
        exceptions = AvailabilityException.query.filter_by(
            user_id=practitioner_id,
            exception_date=target_date
        ).all()
        
        # Check if entire day is blocked
        full_day_block = any(ex.is_all_day and ex.exception_type in ['blocked', 'holiday', 'vacation'] 
                            for ex in exceptions)
        
        if not full_day_block:
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
                    # Check if exception blocks this time
                    partial_block_times = [(ex.start_time, ex.end_time) 
                                          for ex in exceptions 
                                          if not ex.is_all_day]
                    
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
        
        return jsonify({
            'success': True,
            'date': date_str,
            'practitioner': practitioner.full_name,
            'available_slots': filtered_slots,
            'booked_slots': booked_slots,
            'is_blocked': full_day_block,
            'duration_minutes': duration_minutes
        })
    except Exception as e:
        logger.error(f"Error getting availability: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

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
    from google_auth_oauthlib.flow import Flow
    from google.oauth2 import idtoken
    flow = Flow.from_client_secrets_file('client_secrets.json', scopes=['https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/userinfo.profile', 'openid'])
    flow.redirect_uri = url_for('google_callback', _external=True)
    authorization_response = request.url
    flow.fetch_token(authorization_response=authorization_response)
    credentials = flow.credentials
    userinfo = idtoken.verify_oauth2_token(credentials.id_token, flow.client_config['client_id'])
    user = User.query.filter_by(email=userinfo['email']).first()
    if not user:
        user = User(username=userinfo['email'].split('@')[0], email=userinfo['email'], role='user')
        db.session.add(user)
        db.session.commit()
    login_user(user)
    return redirect(url_for('dashboard'))

logger.info("Google routes loaded successfully")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
