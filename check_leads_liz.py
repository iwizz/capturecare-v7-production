#!/usr/bin/env python3
"""
Check for leads named Liz/Loiz in the database
"""
import os
import sys

# Add capturecare to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'capturecare'))

from flask import Flask
from models import db, Lead
from config import Config

# Create Flask app
app = Flask(__name__)
config = Config()

app.config['SQLALCHEMY_DATABASE_URI'] = config.SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

print(f"🔍 Checking for leads table in database...")
print(f"   Database: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")

with app.app_context():
    try:
        # Try to query the leads table
        print('\n🔍 Searching for leads with "liz", "loiz", "lois", or "lina"...\n')
        
        leads = Lead.query.filter(
            db.or_(
                Lead.first_name.ilike('%liz%'),
                Lead.last_name.ilike('%liz%'),
                Lead.first_name.ilike('%loiz%'),
                Lead.last_name.ilike('%loiz%'),
                Lead.first_name.ilike('%lois%'),
                Lead.last_name.ilike('%lois%'),
                Lead.first_name.ilike('%lina%'),
                Lead.last_name.ilike('%lina%')
            )
        ).all()
        
        if leads:
            print(f'✅ Found {len(leads)} lead(s):\n')
            for lead in leads:
                print('━' * 60)
                print(f'ID: {lead.id}')
                print(f'Name: {lead.first_name} {lead.last_name}')
                print(f'Email: {lead.email}')
                print(f'Mobile: {lead.mobile}')
                print(f'Source: {lead.source}')
                print(f'Status: {lead.status}')
                print(f'Notes: {lead.notes}')
                if lead.converted_to_patient_id:
                    print(f'✅ Converted to Patient ID: {lead.converted_to_patient_id}')
                print(f'Created: {lead.created_at}')
                print()
        else:
            print('❌ No leads found with "liz", "loiz", "lois", or "lina" in their name\n')
        
        # Show total leads
        total_leads = Lead.query.count()
        print(f'📊 Total leads in database: {total_leads}')
        
        # Show all leads if there aren't many
        if total_leads > 0 and total_leads <= 20:
            print(f'\n📋 All leads:')
            all_leads = Lead.query.order_by(Lead.created_at.desc()).all()
            for l in all_leads:
                print(f'  - ID {l.id}: {l.first_name} {l.last_name} ({l.email}) - Status: {l.status}')
        
    except Exception as e:
        print(f'\n❌ Error: {e}')
        print('\nThe leads table may not exist in this database.')
        import traceback
        traceback.print_exc()

