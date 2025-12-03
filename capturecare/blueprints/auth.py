from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, current_user, login_required
from models import db, User, PatientAuth, Patient
from datetime import datetime, timedelta
import logging
import os
import jwt
import secrets

# Create blueprint
auth_bp = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)

# Helper function to generate JWT token (used in patient API auth)
def get_jwt_secret():
    secret = os.getenv('JWT_SECRET')
    if not secret:
        secret = secrets.token_urlsafe(32)
        logger.warning("JWT_SECRET not set, using generated secret")
    return secret

def generate_jwt_token(patient_id, email, expires_in_hours=24):
    payload = {
        'patient_id': patient_id,
        'email': email,
        'exp': datetime.utcnow() + timedelta(hours=expires_in_hours),
        'iat': datetime.utcnow(),
        'type': 'access'
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm='HS256')

def generate_refresh_token(patient_id, email):
    payload = {
        'patient_id': patient_id,
        'email': email,
        'exp': datetime.utcnow() + timedelta(days=30),
        'iat': datetime.utcnow(),
        'type': 'refresh'
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm='HS256')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account has been deactivated. Please contact an administrator.', 'error')
                return redirect(url_for('auth.login'))
            
            session.permanent = True
            login_user(user, remember=True)
            logger.info(f"User {username} logged in successfully")
            
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
            logger.warning(f"Failed login attempt for username: {username}")
    
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    username = current_user.username
    logout_user()
    logger.info(f"User {username} logged out")
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('auth.login'))

@auth_bp.route('/setup-password', methods=['GET', 'POST'])
def setup_password():
    """Password setup page for new users"""
    token = request.args.get('token') or request.form.get('token')
    
    if not token:
        flash('Invalid or missing setup link.', 'error')
        return redirect(url_for('auth.login'))
    
    user = User.query.filter_by(password_setup_token=token).first()
    
    if not user:
        flash('Invalid setup link. Please contact your administrator.', 'error')
        return redirect(url_for('auth.login'))
    
    if user.password_setup_token_expires and user.password_setup_token_expires < datetime.utcnow():
        flash('This setup link has expired. Please contact your administrator for a new link.', 'error')
        return redirect(url_for('auth.login'))
    
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
        
        user.set_password(password)
        user.password_set = True
        user.password_setup_token = None
        user.password_setup_token_expires = None
        
        db.session.commit()
        
        flash('Password set successfully! You can now log in.', 'success')
        logger.info(f"User {user.username} completed password setup")
        
        return redirect(url_for('auth.login'))
    
    return render_template('setup_password.html', user=user, token=token)

# Google Login Routes
@auth_bp.route('/google/login')
def google_login():
    """
    Initiate Google OAuth 2.0 login flow.
    Follows Google's OAuth 2.0 best practices from official documentation.
    """
    logger.info("Google login route accessed")
    from google_auth_oauthlib.flow import Flow
    
    # Use hardcoded production URL with HTTPS - must exactly match Google Cloud Console
    # Using the actual working URL
    production_url = 'https://capturecare-310697189983.australia-southeast2.run.app'
    callback_url = f"{production_url}/google/callback"
    
    # Ensure HTTPS (double-check)
    if not callback_url.startswith('https://'):
        logger.error(f"CRITICAL ERROR: callback_url is not HTTPS! Was: {callback_url}")
        callback_url = callback_url.replace('http://', 'https://')
    
    logger.info(f"Using redirect_uri: {callback_url}")
    
    try:
        # Load client secrets
        import json
        with open('client_secrets.json', 'r') as f:
            client_secrets = json.load(f)
        
        # Verify the redirect_uri is in the client_secrets (best practice)
        registered_uris = client_secrets.get('web', {}).get('redirect_uris', [])
        if callback_url not in registered_uris:
            logger.warning(f"redirect_uri {callback_url} not found in client_secrets.json redirect_uris. Registered URIs: {registered_uris}")
        
        # Create Flow object - this is the recommended approach per Google docs
        flow = Flow.from_client_config(
            client_secrets,
            scopes=['https://www.googleapis.com/auth/userinfo.email', 
                   'https://www.googleapis.com/auth/userinfo.profile', 
                   'openid'],
            redirect_uri=callback_url  # Set redirect_uri during Flow creation
        )
        
        # Generate state for CSRF protection (required per Google docs)
        state = secrets.token_urlsafe(32)
        session['state'] = state
        
        # Use Flow's authorization_url() method - this is the recommended approach
        # It properly handles URL encoding and parameter formatting
        authorization_url, returned_state = flow.authorization_url(
            access_type='offline',  # Request refresh token
            include_granted_scopes='true',  # Enable incremental authorization
            state=state,  # CSRF protection
            prompt='consent'  # Force consent screen to ensure refresh token
        )
        
        # Verify the authorization URL contains HTTPS redirect_uri
        if 'redirect_uri=' in authorization_url:
            # Check for HTTP (should not be present)
            if 'redirect_uri=http://' in authorization_url or 'redirect_uri%3Dhttp%3A%2F%2F' in authorization_url:
                logger.error(f"ERROR: HTTP found in authorization URL! This should not happen.")
                logger.error(f"Authorization URL: {authorization_url[:500]}")
            else:
                logger.info(f"Authorization URL generated successfully with HTTPS redirect_uri")
        
        logger.info(f"Redirecting to Google OAuth 2.0 authorization server")
        return redirect(authorization_url)
        
    except Exception as e:
        logger.error(f"Error in Google login: {e}", exc_info=True)
        flash('Google login failed. Please try again.', 'error')
        return redirect(url_for('auth.login'))

@auth_bp.route('/google/callback')
def google_callback():
    from google_auth_oauthlib.flow import Flow
    from google.oauth2 import idtoken
    
    # Use hardcoded production URL with HTTPS - MUST match google_login
    # Using the actual working URL
    production_url = 'https://capturecare-310697189983.australia-southeast2.run.app'
    callback_url = f"{production_url}/google/callback"
    
    # Ensure HTTPS (double-check)
    if not callback_url.startswith('https://'):
        callback_url = callback_url.replace('http://', 'https://')
    
    logger.info(f"Google OAuth callback - Setting redirect_uri to: {callback_url}")
    
    # Load client secrets and modify redirect_uris to only include our HTTPS URL
    import json
    with open('client_secrets.json', 'r') as f:
        client_secrets = json.load(f)
    
    # Force redirect_uris to only have our HTTPS URL (must match google_login)
    client_secrets['web']['redirect_uris'] = [callback_url]
    
    # Create Flow from modified client secrets (in-memory)
    flow = Flow.from_client_config(client_secrets, scopes=['https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/userinfo.profile', 'openid'])
    
    # CRITICAL: Set redirect_uri explicitly
    flow.redirect_uri = callback_url
    
    logger.info(f"Flow redirect_uri after setting: {flow.redirect_uri}")
    
    # CRITICAL: Verify state parameter (CSRF protection - required per Google docs)
    if 'state' not in request.args:
        logger.error("Missing state parameter in callback - possible security issue")
        flash('Invalid request. Please try again.', 'error')
        return redirect(url_for('auth.login'))
    
    if 'state' not in session or request.args.get('state') != session.get('state'):
        logger.error("State mismatch - possible CSRF attack")
        flash('Security validation failed. Please try again.', 'error')
        return redirect(url_for('auth.login'))
    
    # Check for error response from Google
    if 'error' in request.args:
        error = request.args.get('error')
        logger.error(f"Google OAuth error: {error}")
        if error == 'access_denied':
            flash('Google login was cancelled.', 'info')
        else:
            flash(f'Google login failed: {error}', 'error')
        return redirect(url_for('auth.login'))
    
    # Check for authorization code
    if 'code' not in request.args:
        logger.error("Missing authorization code in callback")
        flash('Authorization failed. Please try again.', 'error')
        return redirect(url_for('auth.login'))
    
    authorization_response = request.url
    try:
        flow.fetch_token(authorization_response=authorization_response)
        credentials = flow.credentials
        
        # Verify the ID token with request object for additional security
        userinfo = idtoken.verify_oauth2_token(
            credentials.id_token, 
            flow.client_config['client_id'],
            request=request
        )
        
        user = User.query.filter_by(email=userinfo['email']).first()
        if not user:
            # User doesn't exist - don't auto-create, require admin to create account first
            logger.warning(f"Google login attempted for unregistered email: {userinfo['email']}")
            flash('No account found with this Google email. Please contact your administrator to create an account.', 'error')
            return redirect(url_for('auth.login'))
        
        if not user.is_active:
            logger.warning(f"Google login attempted for inactive account: {user.username}")
            flash('Your account has been deactivated. Please contact an administrator.', 'error')
            return redirect(url_for('auth.login'))
        
        # Clear the state from session (one-time use)
        session.pop('state', None)
            
        session.permanent = True
        login_user(user, remember=True)
        logger.info(f"User {user.username} ({user.email}) logged in via Google OAuth")
        flash('Logged in with Google successfully!', 'success')
        return redirect(url_for('index'))
    except Exception as e:
        logger.error(f"Google login error: {e}", exc_info=True)
        flash('Google login failed. Please try again.', 'error')
        return redirect(url_for('auth.login'))


