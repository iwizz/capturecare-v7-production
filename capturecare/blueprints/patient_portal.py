from flask import Blueprint, request, jsonify, current_app
from models import db, Patient, HealthData, TargetRange, PatientAuth
from datetime import datetime, timedelta
from functools import wraps
from extensions import cache
import jwt
import os
import logging
import secrets

# Create blueprint
patient_portal_bp = Blueprint('patient_portal', __name__)
logger = logging.getLogger(__name__)

# JWT Utilities (duplicated from web_dashboard.py until fully refactored)
def get_jwt_secret():
    """Get JWT secret from environment or generate one"""
    secret = os.getenv('JWT_SECRET')
    if not secret:
        # Generate a secret if not set (for development)
        # Note: In production, this should always be set in environment variables
        # If we generate it here, it won't persist across restarts, invalidating all tokens
        # For this refactor, we'll assume it's set or accept the limitation
        logger.warning("JWT_SECRET not set, using fallback or generated secret")
        return current_app.config.get('SECRET_KEY', 'fallback-secret-key')
    return secret

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

# Routes

@patient_portal_bp.route('/api/patient', methods=['GET'])
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

@patient_portal_bp.route('/api/patient/auth/login', methods=['POST'])
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

@patient_portal_bp.route('/api/patient/auth/register', methods=['POST'])
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

@patient_portal_bp.route('/api/patient/auth/apple', methods=['POST'])
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
                    })
            
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

@patient_portal_bp.route('/api/patient/auth/google', methods=['POST'])
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
                })
            
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

@patient_portal_bp.route('/api/patient/auth/refresh', methods=['POST'])
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

@patient_portal_bp.route('/api/patient/profile', methods=['GET'])
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

def make_health_data_cache_key(*args, **kwargs):
    """Create a unique cache key based on patient_id and query parameters"""
    # patient_id is attached to request by the @patient_auth_required decorator
    patient_id = getattr(request, 'patient_id', 'anon')
    days = request.args.get('days', '30')
    metric_type = request.args.get('type', 'all')
    return f"health_data:{patient_id}:{days}:{metric_type}"

@patient_portal_bp.route('/api/patient/health-data', methods=['GET'])
@patient_auth_required
@cache.cached(timeout=300, key_prefix=make_health_data_cache_key)
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

@patient_portal_bp.route('/api/patient/target-ranges', methods=['GET'])
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

