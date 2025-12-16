#!/usr/bin/env python3
"""
Quick script to check for patient Liz in the production database
"""
import os
import sys

# Add capturecare to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'capturecare'))

from flask import Flask
from models import db, Patient
from config import Config

# Create Flask app
app = Flask(__name__)
config = Config()

# Force production database connection
# This will use DATABASE_URL from environment if set
app.config['SQLALCHEMY_DATABASE_URI'] = config.SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

print(f"🔍 Connecting to database: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")

with app.app_context():
    try:
        # Search for patients with "liz" or "lina" in their name
        patients = Patient.query.filter(
            db.or_(
                Patient.first_name.ilike('%liz%'),
                Patient.last_name.ilike('%liz%'),
                Patient.first_name.ilike('%lina%'),
                Patient.last_name.ilike('%lina%')
            )
        ).all()
        
        if patients:
            print(f'\n✅ Found {len(patients)} patient(s):\n')
            for patient in patients:
                print('━' * 60)
                print(f'ID: {patient.id}')
                print(f'Name: {patient.first_name} {patient.last_name}')
                print(f'Email: {patient.email}')
                print(f'DOB: {patient.date_of_birth}')
                print(f'Mobile: {patient.mobile}')
                print(f'Phone: {patient.phone}')
                if patient.address_line1:
                    print(f'Address: {patient.address_line1}')
                    if patient.city:
                        print(f'         {patient.city} {patient.state} {patient.postcode}')
                print(f'Withings User ID: {patient.withings_user_id or "Not connected"}')
                print(f'Cliniko Patient ID: {patient.cliniko_patient_id or "Not linked"}')
                print(f'Created: {patient.created_at}')
                print()
        else:
            print('\n❌ No patients found with "liz" or "lina" in their name\n')
        
        # Show total patient count
        total_patients = Patient.query.count()
        print(f'📊 Total patients in database: {total_patients}')
        
        # Show all patients if there aren't many
        if total_patients <= 20:
            print(f'\n📋 All patients:')
            all_patients = Patient.query.order_by(Patient.last_name, Patient.first_name).all()
            for p in all_patients:
                print(f'  - ID {p.id}: {p.first_name} {p.last_name} ({p.email})')
        
    except Exception as e:
        print(f'\n❌ Error querying database: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)

