from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_, desc
from datetime import datetime

from ..models import db, Lead, Patient, User

leads_bp = Blueprint('leads', __name__, url_prefix='/leads')

@leads_bp.route('/')
@login_required
def leads_list():
    """Display all leads with filtering and search"""
    # Get filter parameters
    status_filter = request.args.get('status', 'all')
    search_query = request.args.get('search', '').strip()

    # Base query
    query = Lead.query

    # Apply status filter
    if status_filter != 'all':
        query = query.filter(Lead.status == status_filter)

    # Apply search filter
    if search_query:
        query = query.filter(
            or_(
                Lead.first_name.ilike(f'%{search_query}%'),
                Lead.last_name.ilike(f'%{search_query}%'),
                Lead.email.ilike(f'%{search_query}%')
            )
        )

    # Order by creation date (newest first)
    leads = query.order_by(desc(Lead.created_at)).all()

    return render_template('leads.html',
                         leads=leads,
                         current_filter=status_filter,
                         search_query=search_query)

@leads_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_lead():
    """Add a new lead"""
    if request.method == 'POST':
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        mobile = request.form.get('mobile')
        source = request.form.get('source')
        notes = request.form.get('notes')

        # Validate required fields
        if not all([first_name, last_name, email]):
            flash('First name, last name, and email are required.', 'error')
            return redirect(url_for('leads.add_lead'))

        # Check if lead with this email already exists
        existing_lead = Lead.query.filter_by(email=email).first()
        if existing_lead:
            flash('A lead with this email already exists.', 'error')
            return redirect(url_for('leads.add_lead'))

        # Create new lead
        new_lead = Lead(
            first_name=first_name,
            last_name=last_name,
            email=email,
            mobile=mobile,
            source=source,
            status='new',
            notes=notes,
            created_by_id=current_user.id
        )

        try:
            db.session.add(new_lead)
            db.session.commit()
            flash('Lead added successfully!', 'success')
            return redirect(url_for('leads.leads_list'))
        except Exception as e:
            db.session.rollback()
            flash('Error adding lead. Please try again.', 'error')
            return redirect(url_for('leads.add_lead'))

    return render_template('add_lead.html')

@leads_bp.route('/<int:lead_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_lead(lead_id):
    """Edit an existing lead"""
    lead = Lead.query.get_or_404(lead_id)

    if request.method == 'POST':
        lead.first_name = request.form.get('first_name')
        lead.last_name = request.form.get('last_name')
        lead.email = request.form.get('email')
        lead.mobile = request.form.get('mobile')
        lead.source = request.form.get('source')
        lead.status = request.form.get('status')
        new_notes = request.form.get('notes')

        # Handle notes history
        if new_notes != lead.notes:
            timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            history_entry = f"[{timestamp}] {current_user.full_name}: {new_notes}"
            if lead.notes_history:
                lead.notes_history += "\n" + history_entry
            else:
                lead.notes_history = history_entry
            lead.notes = new_notes

        try:
            db.session.commit()
            flash('Lead updated successfully!', 'success')
            return redirect(url_for('leads.leads_list'))
        except Exception as e:
            db.session.rollback()
            flash('Error updating lead. Please try again.', 'error')

    return render_template('edit_lead.html', lead=lead)

@leads_bp.route('/<int:lead_id>/convert', methods=['GET', 'POST'])
@login_required
def convert_lead(lead_id):
    """Convert a lead to a patient"""
    lead = Lead.query.get_or_404(lead_id)

    if request.method == 'POST':
        # Create new patient from lead data
        new_patient = Patient(
            first_name=lead.first_name,
            last_name=lead.last_name,
            email=lead.email,
            phone=lead.mobile,
            created_at=datetime.utcnow()
        )

        try:
            db.session.add(new_patient)
            db.session.commit()

            # Update lead with conversion info
            lead.converted_to_patient_id = new_patient.id
            lead.converted_at = datetime.utcnow()
            lead.status = 'converted'

            db.session.commit()

            flash(f'Lead {lead.full_name} successfully converted to patient!', 'success')
            return redirect(url_for('patients.patients_list'))

        except Exception as e:
            db.session.rollback()
            flash('Error converting lead to patient. Please try again.', 'error')

    return render_template('convert_lead.html', lead=lead)

@leads_bp.route('/<int:lead_id>/delete', methods=['POST'])
@login_required
def delete_lead(lead_id):
    """Delete a lead"""
    lead = Lead.query.get_or_404(lead_id)

    try:
        db.session.delete(lead)
        db.session.commit()
        flash('Lead deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting lead. Please try again.', 'error')

    return redirect(url_for('leads.leads_list'))

@leads_bp.route('/api/search')
@login_required
def api_search_leads():
    """API endpoint for lead search"""
    query = request.args.get('q', '').strip()
    limit = int(request.args.get('limit', 10))

    if not query:
        return jsonify([])

    leads = Lead.query.filter(
        or_(
            Lead.first_name.ilike(f'%{query}%'),
            Lead.last_name.ilike(f'%{query}%'),
            Lead.email.ilike(f'%{query}%')
        )
    ).limit(limit).all()

    results = [{
        'id': lead.id,
        'text': f"{lead.full_name} ({lead.email})",
        'first_name': lead.first_name,
        'last_name': lead.last_name,
        'email': lead.email
    } for lead in leads]

    return jsonify(results)
