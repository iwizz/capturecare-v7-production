"""Admin-only endpoints for system maintenance"""

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from functools import wraps
from ..models import db, Appointment, Patient, User
from sqlalchemy import or_
import logging

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            return jsonify({'success': False, 'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/cleanup-unknown-appointments', methods=['POST'])
@login_required
@admin_required
def cleanup_unknown_appointments():
    """Delete appointments with Unknown Patient or Unknown Practitioner"""
    try:
        deleted_count = 0
        
        # Find appointments with null patient_id or practitioner_id
        null_appointments = Appointment.query.filter(
            or_(
                Appointment.patient_id.is_(None),
                Appointment.practitioner_id.is_(None)
            )
        ).all()
        
        for apt in null_appointments:
            db.session.delete(apt)
            deleted_count += 1
        
        # Find patients with "Unknown" in their name
        unknown_patients = Patient.query.filter(
            or_(
                Patient.first_name.ilike('%unknown%'),
                Patient.last_name.ilike('%unknown%')
            )
        ).all()
        
        unknown_patient_ids = [p.id for p in unknown_patients]
        
        if unknown_patient_ids:
            appointments_with_unknown_patients = Appointment.query.filter(
                Appointment.patient_id.in_(unknown_patient_ids)
            ).all()
            
            for apt in appointments_with_unknown_patients:
                db.session.delete(apt)
                deleted_count += 1
        
        # Find practitioners with "Unknown" in their name
        unknown_practitioners = User.query.filter(
            or_(
                User.first_name.ilike('%unknown%'),
                User.last_name.ilike('%unknown%')
            )
        ).all()
        
        unknown_practitioner_ids = [u.id for u in unknown_practitioners]
        
        if unknown_practitioner_ids:
            appointments_with_unknown_practitioners = Appointment.query.filter(
                Appointment.practitioner_id.in_(unknown_practitioner_ids)
            ).all()
            
            for apt in appointments_with_unknown_practitioners:
                db.session.delete(apt)
                deleted_count += 1
        
        db.session.commit()
        
        logger.info(f"Admin cleanup: Deleted {deleted_count} unknown appointments")
        
        return jsonify({
            'success': True, 
            'message': f'Successfully deleted {deleted_count} unknown appointments',
            'deleted_count': deleted_count
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error cleaning up unknown appointments: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_bp.route('/stats', methods=['GET'])
@login_required
@admin_required
def get_admin_stats():
    """Get system statistics"""
    try:
        # Count unknown appointments
        unknown_count = Appointment.query.filter(
            or_(
                Appointment.patient_id.is_(None),
                Appointment.practitioner_id.is_(None)
            )
        ).count()
        
        # Find patients with "Unknown" in name
        unknown_patients = Patient.query.filter(
            or_(
                Patient.first_name.ilike('%unknown%'),
                Patient.last_name.ilike('%unknown%')
            )
        ).all()
        
        unknown_patient_ids = [p.id for p in unknown_patients]
        appointments_with_unknown_patients = 0
        if unknown_patient_ids:
            appointments_with_unknown_patients = Appointment.query.filter(
                Appointment.patient_id.in_(unknown_patient_ids)
            ).count()
        
        # Find practitioners with "Unknown" in name
        unknown_practitioners = User.query.filter(
            or_(
                User.first_name.ilike('%unknown%'),
                User.last_name.ilike('%unknown%')
            )
        ).all()
        
        unknown_practitioner_ids = [u.id for u in unknown_practitioners]
        appointments_with_unknown_practitioners = 0
        if unknown_practitioner_ids:
            appointments_with_unknown_practitioners = Appointment.query.filter(
                Appointment.practitioner_id.in_(unknown_practitioner_ids)
            ).count()
        
        total_unknown = unknown_count + appointments_with_unknown_patients + appointments_with_unknown_practitioners
        
        return jsonify({
            'success': True,
            'stats': {
                'null_appointments': unknown_count,
                'unknown_patient_appointments': appointments_with_unknown_patients,
                'unknown_practitioner_appointments': appointments_with_unknown_practitioners,
                'total_unknown': total_unknown
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting admin stats: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
