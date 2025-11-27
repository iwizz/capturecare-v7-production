import os
from dotenv import load_dotenv
from datetime import timezone, timedelta

# Load .env file from the same directory as this config.py file
_config_dir = os.path.dirname(os.path.abspath(__file__))
_env_path = os.path.join(_config_dir, 'capturecare.env')
load_dotenv(_env_path)
print(f"🔧 Loaded .env from: {_env_path}")
print(f"🔧 SMTP_USERNAME from .env: {os.getenv('SMTP_USERNAME')}")

class Config:
    GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID', '')
    USE_SECRET_MANAGER = os.getenv('USE_SECRET_MANAGER', 'False').lower() == 'true'
    
    def __init__(self):
        if self.USE_SECRET_MANAGER and self.GCP_PROJECT_ID:
            self._load_secrets_from_gcp()
            # Reload all config attributes after secrets are loaded
            self._reload_config_attributes()
    
    def _load_secrets_from_gcp(self):
        try:
            from google.cloud import secretmanager
            import logging
            logger = logging.getLogger(__name__)
            
            client = secretmanager.SecretManagerServiceClient()
            
            secrets = {
                'WITHINGS_CLIENT_ID': 'withings-client-id',
                'WITHINGS_CLIENT_SECRET': 'withings-client-secret',
                'CLINIKO_API_KEY': 'cliniko-api-key',
                'CLINIKO_SHARD': 'cliniko-shard',
                'OPENAI_API_KEY': 'openai-api-key',
                'XAI_API_KEY': 'xai-api-key',
                'HEYGEN_API_KEY': 'heygen-api-key',
                'TWILIO_ACCOUNT_SID': 'twilio-account-sid',
                'TWILIO_AUTH_TOKEN': 'twilio-auth-token',
                'TWILIO_PHONE_NUMBER': 'twilio-phone-number',
                'TWILIO_API_KEY_SID': 'twilio-api-key-sid',
                'TWILIO_API_KEY_SECRET': 'twilio-api-key-secret',
                'SMTP_SERVER': 'smtp-server',
                'SMTP_PORT': 'smtp-port',
                'SMTP_USERNAME': 'smtp-username',
                'SMTP_PASSWORD': 'smtp-password',
                'SMTP_FROM_EMAIL': 'smtp-from-email',
                'GOOGLE_CLIENT_ID': 'google-client-id',
                'GOOGLE_CLIENT_SECRET': 'google-client-secret',
            }
            
            for env_var, secret_name in secrets.items():
                try:
                    name = f"projects/{self.GCP_PROJECT_ID}/secrets/{secret_name}/versions/latest"
                    response = client.access_secret_version(request={"name": name})
                    # CRITICAL: Do NOT strip() - preserve spaces in passwords (especially SMTP_PASSWORD)
                    secret_value = response.payload.data.decode('UTF-8')
                    # Only strip if it's not a password field
                    if 'PASSWORD' not in env_var:
                        secret_value = secret_value.strip()
                    os.environ[env_var] = secret_value
                    if 'TWILIO' in env_var or 'API_KEY' in env_var:
                        logger.info(f"✅ Loaded secret {secret_name}: {secret_value[:20]}..." if len(secret_value) > 20 else f"✅ Loaded secret {secret_name}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not load secret {secret_name}: {e}")
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to load secrets: {e}")
    
    def _reload_config_attributes(self):
        """Reload config attributes after secrets are loaded into os.environ"""
        # Update both instance AND class attributes so that code using Config.ATTRIBUTE works
        Config.WITHINGS_CLIENT_ID = self.WITHINGS_CLIENT_ID = os.getenv('WITHINGS_CLIENT_ID', '')
        Config.WITHINGS_CLIENT_SECRET = self.WITHINGS_CLIENT_SECRET = os.getenv('WITHINGS_CLIENT_SECRET', '')
        Config.CLINIKO_API_KEY = self.CLINIKO_API_KEY = os.getenv('CLINIKO_API_KEY', '')
        Config.CLINIKO_SHARD = self.CLINIKO_SHARD = os.getenv('CLINIKO_SHARD', 'au1')
        Config.OPENAI_API_KEY = self.OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
        Config.XAI_API_KEY = self.XAI_API_KEY = os.getenv('XAI_API_KEY', '')
        Config.HEYGEN_API_KEY = self.HEYGEN_API_KEY = os.getenv('HEYGEN_API_KEY', '')
        Config.TWILIO_ACCOUNT_SID = self.TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID', '')
        Config.TWILIO_AUTH_TOKEN = self.TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN', '')
        Config.TWILIO_PHONE_NUMBER = self.TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER', '')
        Config.TWILIO_API_KEY_SID = self.TWILIO_API_KEY_SID = os.getenv('TWILIO_API_KEY_SID', '')
        Config.TWILIO_API_KEY_SECRET = self.TWILIO_API_KEY_SECRET = os.getenv('TWILIO_API_KEY_SECRET', '')
        Config.SMTP_SERVER = self.SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        Config.SMTP_PORT = self.SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
        Config.SMTP_USERNAME = self.SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
        # Fix: Clean password - replace non-breaking spaces with regular spaces
        _smtp_password_raw = os.getenv('SMTP_PASSWORD', '')
        # CRITICAL: Do NOT strip() - preserve spaces in Gmail app passwords
        # Only replace non-breaking spaces with regular spaces, but keep all other spaces
        Config.SMTP_PASSWORD = self.SMTP_PASSWORD = _smtp_password_raw.replace('\xa0', ' ').replace('\u00a0', ' ') if _smtp_password_raw else ''
        Config.SMTP_FROM_EMAIL = self.SMTP_FROM_EMAIL = os.getenv('SMTP_FROM_EMAIL', '')
    
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Database Configuration - FIXED: Use PostgreSQL in production
    db_url = os.getenv('DATABASE_URL', '')
    if not db_url:
        # Only use SQLite as fallback for local development
        # Use absolute path to ensure we use the correct database file
        _config_dir = os.path.dirname(os.path.abspath(__file__))
        _db_path = os.path.join(_config_dir, 'instance', 'capturecare.db')
        # Ensure instance directory exists
        os.makedirs(os.path.dirname(_db_path), exist_ok=True)
        db_url = f'sqlite:///{_db_path}'
    elif db_url.startswith('postgres://'):
        # Fix postgres:// to postgresql:// for SQLAlchemy compatibility
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    
    SQLALCHEMY_DATABASE_URI = db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Connection pool settings - only for PostgreSQL, not SQLite
    if db_url and 'postgresql' in db_url:
        # Connection pool settings for Cloud SQL (PostgreSQL)
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_size': 5,
            'pool_recycle': 3600,
            'pool_pre_ping': True,  # Verify connections before using
            'connect_args': {
                'connect_timeout': 10,
                'options': '-c statement_timeout=30000'
            }
        }
    else:
        # SQLite doesn't support connect_timeout or pool settings
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_pre_ping': True
        }
    
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = None
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_NAME = 'capturecare_session'
    SESSION_TYPE = 'filesystem'
    
    WITHINGS_CLIENT_ID = os.getenv('WITHINGS_CLIENT_ID', '')
    WITHINGS_CLIENT_SECRET = os.getenv('WITHINGS_CLIENT_SECRET', '')
    WITHINGS_REDIRECT_URI = os.getenv('WITHINGS_REDIRECT_URI', 'http://localhost:5000/withings/callback')
    
    CLINIKO_API_KEY = os.getenv('CLINIKO_API_KEY', '')
    CLINIKO_SHARD = os.getenv('CLINIKO_SHARD', 'au1')
    
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    XAI_API_KEY = os.getenv('XAI_API_KEY', '')
    
    HEYGEN_API_KEY = os.getenv('HEYGEN_API_KEY', '')
    
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID', '')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN', '')
    TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER', '')
    # Optional: API Keys for Twilio Video (more secure, but can use Auth Token as fallback)
    TWILIO_API_KEY_SID = os.getenv('TWILIO_API_KEY_SID', '')
    TWILIO_API_KEY_SECRET = os.getenv('TWILIO_API_KEY_SECRET', '')
    
    # Public Base URL for patient-facing links (video rooms, webhooks, etc.)
    # For local development with external access, use ngrok or your public IP
    # Example: https://your-ngrok-url.ngrok.io or https://your-domain.com
    BASE_URL = os.getenv('BASE_URL', os.getenv('PUBLIC_URL', ''))
    
    GOOGLE_SHEETS_CREDENTIALS = os.getenv('GOOGLE_SHEETS_CREDENTIALS', '')
    GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID', '')
    
    SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
    # Fix: Clean password - replace non-breaking spaces with regular spaces
    _smtp_password_raw = os.getenv('SMTP_PASSWORD', '')
    # CRITICAL: Do NOT strip() - preserve spaces in Gmail app passwords
    SMTP_PASSWORD = _smtp_password_raw.replace('\xa0', ' ').replace('\u00a0', ' ') if _smtp_password_raw else ''
    SMTP_FROM_EMAIL = os.getenv('SMTP_FROM_EMAIL', '')
    
    DEFAULT_TIMEZONE = timezone(timedelta(hours=10))
    TIMEZONE_NAME = 'Australia/Sydney'
