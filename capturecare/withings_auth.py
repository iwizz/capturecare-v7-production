import os
import json
import time
import requests
import secrets
import hmac
import hashlib
from urllib.parse import urlencode, parse_qs
from datetime import datetime, timedelta
from dotenv import load_dotenv
import logging
from google.cloud import storage

load_dotenv('capturecare/capturecare.env')

logger = logging.getLogger(__name__)

class WithingsAuthManager:
    def __init__(self, client_id, client_secret, redirect_uri):
        """Initialize Withings OAuth handler"""
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.tokens_dir = 'capturecare/tokens'
        
        self.use_cloud_storage = os.getenv('USE_CLOUD_STORAGE', 'False').lower() == 'true'
        self.gcs_bucket_name = os.getenv('GCS_BUCKET_NAME', '')
        self.gcs_tokens_prefix = os.getenv('GCS_TOKENS_PREFIX', 'tokens/')
        
        if self.use_cloud_storage and self.gcs_bucket_name:
            try:
                self.storage_client = storage.Client()
                self.bucket = self.storage_client.bucket(self.gcs_bucket_name)
                logger.info(f"✅ Cloud Storage initialized: {self.gcs_bucket_name}")
            except Exception as e:
                logger.warning(f"⚠️ Cloud Storage not available: {e}")
                self.use_cloud_storage = False
        else:
            self.use_cloud_storage = False
            os.makedirs(self.tokens_dir, exist_ok=True)
        
        self.auth_url = "https://account.withings.com/oauth2_user/authorize2"
        self.token_url = "https://wbsapi.withings.net/v2/oauth2"
        
        logger.info(f"✅ WithingsAuth initialized")
        logger.info(f"🔗 Auth URL: {self.auth_url}")
        logger.info(f"📧 Redirect URI: {self.redirect_uri}")
    
    def _generate_signature(self, params):
        """Generate HMAC-SHA256 signature for Withings API request"""
        sorted_params = sorted(params.items())
        query_string = '&'.join([f"{k}={v}" for k, v in sorted_params])
        
        signature = hmac.new(
            self.client_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    def get_authorization_url(self, patient_id=None, demo_mode=False):
        """
        Generate authorization URL for Withings OAuth
        
        Scopes requested:
        - user.info: Basic user information
        - user.metrics: Health measurements (weight, BP, heart rate, etc.)
        - user.activity: Activity data (steps, sleep, workouts, etc.)
        """
        state = f"{patient_id}_{secrets.token_urlsafe(16)}" if patient_id else secrets.token_urlsafe(16)
        
        if patient_id:
            self._store_auth_state(state, patient_id)
        
        params = {
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'scope': 'user.info,user.metrics,user.activity',
            'state': state
        }
        
        if demo_mode:
            params['mode'] = 'demo'
        
        auth_url = f"{self.auth_url}?{urlencode(params)}"
        
        logger.info(f"📧 Generated auth URL")
        logger.info(f"   Scopes requested: user.info, user.metrics, user.activity")
        
        return auth_url
    
    def _store_auth_state(self, state, patient_id):
        """Store auth state for verification"""
        state_file = os.path.join(self.tokens_dir, 'auth_states.json')
        
        try:
            with open(state_file, 'r') as f:
                content = f.read().strip()
                states = json.loads(content) if content else {}
        except (FileNotFoundError, json.JSONDecodeError):
            states = {}
        
        states[state] = {
            'patient_id': patient_id,
            'created_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(minutes=10)).isoformat()
        }
        
        with open(state_file, 'w') as f:
            json.dump(states, f, indent=2)
    
    def get_credentials(self, code, state=None):
        """Exchange authorization code for access and refresh tokens"""
        patient_id = None
        if state:
            patient_id = self._verify_auth_state(state)
        
        data = {
            'action': 'requesttoken',
            'grant_type': 'authorization_code',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'redirect_uri': self.redirect_uri
        }
        
        logger.info(f"🔄 Exchanging authorization code for tokens...")
        
        try:
            response = requests.post(self.token_url, data=data)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('status') != 0:
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"❌ Withings API error: {error_msg}")
                raise Exception(f"Withings API error: {error_msg}")
            
            token_data = result['body']
            
            token_data.update({
                'patient_id': patient_id,
                'created_at': datetime.now().isoformat(),
                'expires_at': (datetime.now() + timedelta(seconds=token_data.get('expires_in', 10800))).isoformat()
            })
            
            logger.info(f"✅ Successfully obtained tokens")
            
            return self._create_credentials_object(token_data)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Network error during token exchange: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Error during token exchange: {e}")
            raise
    
    def _create_credentials_object(self, token_data):
        """Create credentials object compatible with save_tokens method"""
        class Credentials:
            def __init__(self, data):
                self.access_token = data.get('access_token')
                self.refresh_token = data.get('refresh_token')
                self.userid = data.get('userid')
                self.token_expiry = data.get('expires_in', 10800)
                self.token_type = data.get('token_type', 'Bearer')
        
        return Credentials(token_data)
    
    def _verify_auth_state(self, state):
        """Verify auth state and return patient_id"""
        state_file = os.path.join(self.tokens_dir, 'auth_states.json')
        
        try:
            with open(state_file, 'r') as f:
                content = f.read().strip()
                states = json.loads(content) if content else {}
            
            state_info = states.get(state)
            if not state_info:
                return None
            
            expires_at = datetime.fromisoformat(state_info['expires_at'])
            if datetime.now() > expires_at:
                logger.warning("⚠️ Auth state has expired")
                return None
            
            del states[state]
            with open(state_file, 'w') as f:
                json.dump(states, f, indent=2)
            
            return state_info['patient_id']
            
        except FileNotFoundError:
            return None
    
    def _save_tokens_to_cloud_storage(self, patient_id, token_data):
        blob_name = f"{self.gcs_tokens_prefix}withings_{patient_id}.json"
        blob = self.bucket.blob(blob_name)
        blob.upload_from_string(json.dumps(token_data, default=str))
        logger.info(f"💾 Tokens uploaded to Cloud Storage for patient {patient_id}")

    def _delete_tokens_from_cloud_storage(self, patient_id):
        blob_name = f"{self.gcs_tokens_prefix}withings_{patient_id}.json"
        blob = self.bucket.blob(blob_name)
        if blob.exists():
            blob.delete()
            logger.info(f"🗑️ Tokens deleted from Cloud Storage for patient {patient_id}")

    def save_tokens(self, patient_id, credentials):
        """Save tokens for a patient"""
        from models import db, Patient
        
        patient = Patient.query.get(patient_id)
        if patient:
            patient.withings_access_token = credentials.access_token
            patient.withings_refresh_token = credentials.refresh_token
            patient.withings_user_id = str(credentials.userid)
            patient.withings_token_expiry = datetime.utcnow() + timedelta(seconds=credentials.token_expiry)
            db.session.commit()
            
            token_data = {
                'access_token': credentials.access_token,
                'refresh_token': credentials.refresh_token,
                'userid': credentials.userid,
                'token_expiry': credentials.token_expiry,
                'token_type': credentials.token_type
            }
            
            if self.use_cloud_storage:
                self._save_tokens_to_cloud_storage(patient_id, token_data)
            else:
                os.makedirs(self.tokens_dir, exist_ok=True)
                token_path = os.path.join(self.tokens_dir, f'withings_{patient_id}.json')
                with open(token_path, 'w') as f:
                    json.dump(token_data, f)
            
            logger.info(f"💾 Tokens stored for patient {patient_id}")
            return True
        return False
    
    def get_access_token(self, patient_id):
        """Get valid access token for a patient (refresh if needed)"""
        from models import Patient
        
        patient = Patient.query.get(patient_id)
        if not patient or not patient.withings_access_token:
            logger.error(f"No access token for patient {patient_id}")
            return None
        
        # Check if token needs refresh
        if patient.withings_token_expiry and patient.withings_token_expiry < datetime.utcnow():
            logger.info(f"Token expired for patient {patient_id}, refreshing...")
            if patient.withings_refresh_token:
                if self.refresh_token(patient_id):
                    # Reload patient to get new token
                    from models import db
                    db.session.refresh(patient)
                    return patient.withings_access_token
                else:
                    logger.error(f"Failed to refresh token for patient {patient_id}")
                    return None
            else:
                logger.error(f"No refresh token for patient {patient_id}")
                return None
        
        return patient.withings_access_token
    
    def get_api_client(self, patient_id):
        """Get WithingsApi client for a patient"""
        from models import Patient
        from withings_api import WithingsApi
        from withings_api.common import Credentials
        
        patient = Patient.query.get(patient_id)
        if not patient or not patient.withings_access_token:
            return None
        
        if patient.withings_token_expiry and patient.withings_token_expiry < datetime.utcnow():
            self.refresh_token(patient_id)
            patient = Patient.query.get(patient_id)
        
        credentials = Credentials(
            access_token=patient.withings_access_token,
            refresh_token=patient.withings_refresh_token,
            userid=int(patient.withings_user_id),
            token_expiry=int((patient.withings_token_expiry - datetime.utcnow()).total_seconds()),
            token_type='Bearer',
            client_id=self.client_id,
            consumer_secret=self.client_secret
        )
        
        api = WithingsApi(credentials)
        return api
    
    def refresh_token(self, patient_id):
        """Refresh access token for a patient"""
        from models import db, Patient
        
        patient = Patient.query.get(patient_id)
        if not patient or not patient.withings_refresh_token:
            return False
        
        data = {
            'action': 'requesttoken',
            'grant_type': 'refresh_token',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': patient.withings_refresh_token
        }
        
        try:
            response = requests.post(self.token_url, data=data)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('status') != 0:
                raise Exception(f"Withings API error: {result.get('error', 'Unknown error')}")
            
            token_data = result['body']
            
            patient.withings_access_token = token_data.get('access_token')
            patient.withings_refresh_token = token_data.get('refresh_token')
            patient.withings_token_expiry = datetime.utcnow() + timedelta(seconds=token_data.get('expires_in', 10800))
            db.session.commit()
            
            logger.info(f"🔄 Token refreshed for patient {patient_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error refreshing token: {e}")
            return False
    
    def reset_patient_connection(self, patient_id):
        """Reset Withings connection for a patient"""
        from models import db, Patient
        
        patient = Patient.query.get(patient_id)
        if patient:
            patient.withings_access_token = None
            patient.withings_refresh_token = None
            patient.withings_user_id = None
            patient.withings_token_expiry = None
            db.session.commit()
            
            if self.use_cloud_storage:
                self._delete_tokens_from_cloud_storage(patient_id)
            else:
                token_path = os.path.join(self.tokens_dir, f'withings_{patient_id}.json')
                if os.path.exists(token_path):
                    os.remove(token_path)
            
            logger.info(f"🗑️ Withings connection reset for patient {patient_id}")
            return True
        return False
