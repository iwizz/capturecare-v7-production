from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from ..models import db, Patient, HealthData, Device, TargetRange, User
from datetime import datetime, timedelta
import logging
import os
from sqlalchemy import orm, text

# Create blueprint
patients_bp = Blueprint('patients', __name__)
logger = logging.getLogger(__name__)

@patients_bp.route('/patients')
@login_required
def patients_list():
    patients = Patient.query.all()
    logger.info(f"📋 Patients list route: Found {len(patients)} patients")
    return render_template('patients.html', patients=patients)

@patients_bp.route('/patients/add', methods=['GET', 'POST'])
@login_required
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
        
        # Try to link with Cliniko if configured
        # Need to access cliniko integration from app context or recreate
        # For now, we'll skip the complex integration logic in this refactor step 
        # and add it back properly via a service
        
        flash(f'Patient {first_name} {last_name} added successfully!', 'success')
        return redirect(url_for('patients.patient_detail', patient_id=patient.id))
    
    return render_template('add_patient.html')

@patients_bp.route('/patients/<int:patient_id>')
@login_required
def patient_detail(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    
    end_date_str = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
    start_date_str = request.args.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
    except ValueError:
        start_date = datetime.now() - timedelta(days=30)
        end_date = datetime.now()
    
    health_data = HealthData.query.filter(
        HealthData.patient_id == patient_id,
        HealthData.timestamp >= start_date,
        HealthData.timestamp < end_date
    ).order_by(HealthData.timestamp.asc()).all()
    
    devices = Device.query.filter_by(patient_id=patient_id).all()
    
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
        if measurement_type not in latest_values or data.timestamp > latest_values[measurement_type]['timestamp']:
            latest_values[measurement_type] = {
                'value': data.value,
                'unit': data.unit,
                'timestamp': data.timestamp
            }
    
    cliniko_notes = []
    # Add cliniko notes fetching back later via service
    
    patient_age = None
    if patient.date_of_birth:
        today = datetime.now().date()
        patient_age = int((today - patient.date_of_birth).days / 365.25)
    
    # Target ranges logic
    try:
        target_ranges = TargetRange.query.filter_by(patient_id=patient_id).all()
    except Exception:
        db.session.rollback()
        # Fallback logic for missing columns
        try:
            result = db.session.execute(
                text("SELECT measurement_type, min_value, max_value, target_value FROM target_ranges WHERE patient_id = :patient_id"),
                {'patient_id': patient_id}
            )
            target_ranges = []
            for row in result:
                class SimpleTargetRange:
                    def __init__(self, measurement_type, min_value, max_value, target_value):
                        self.measurement_type = measurement_type
                        self.min_value = min_value
                        self.max_value = max_value
                        self.target_value = target_value
                target_ranges.append(SimpleTargetRange(row[0], row[1], row[2], row[3]))
        except Exception as e:
            logger.error(f"Error loading target ranges: {e}")
            target_ranges = []
            
    target_ranges_dict = {}
    for tr in target_ranges:
        target_ranges_dict[tr.measurement_type] = {
            'min': tr.min_value if tr.min_value is not None else '',
            'max': tr.max_value if tr.max_value is not None else '',
            'target': tr.target_value if tr.target_value is not None else '',
            'show_in_patient_app': getattr(tr, 'show_in_patient_app', True)
        }
    
    practitioners = User.query.filter_by(is_active=True).order_by(User.first_name).all()
    base_url = current_app.config.get('BASE_URL', '') or os.getenv('BASE_URL', '')
    
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

@patients_bp.route('/communications')
@login_required
def communications():
    """Central communications page"""
    # Check if user is a practitioner
    is_practitioner = not current_user.is_admin and current_user.role in ['practitioner', 'nurse']
    return render_template('communications.html', is_practitioner=is_practitioner)


