#!/usr/bin/env python3
"""
Script to create or reset the admin user in the production database
Run this as a Cloud Run job or directly in the production environment
"""
import os
import sys

# Set up environment for production
os.environ['USE_SECRET_MANAGER'] = 'True'
os.environ['GCP_PROJECT_ID'] = 'capturecare-461801'

# Add capturecare directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'capturecare'))

from flask import Flask
from models import db, User
from config import Config
from werkzeug.security import generate_password_hash

def create_admin_user():
    """Create or reset the admin user"""
    app = Flask(__name__)
    config = Config()
    app.config.from_object(config)
    
    print(f"Connecting to database: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")
    
    db.init_app(app)
    
    with app.app_context():
        try:
            # Create tables if they don't exist
            db.create_all()
            
            # Check if user exists
            admin = User.query.filter_by(username='iwizz').first()
            
            if admin:
                print(f"User 'iwizz' already exists. Resetting password...")
                admin.password_hash = generate_password_hash('wizard007')
                admin.is_admin = True
                admin.email = 'admin@capturecare.com'
                db.session.commit()
                print("✅ Password reset successfully for user 'iwizz'")
            else:
                print("Creating new admin user 'iwizz'...")
                admin = User(
                    username='iwizz',
                    email='admin@capturecare.com',
                    password_hash=generate_password_hash('wizard007'),
                    is_admin=True
                )
                db.session.add(admin)
                db.session.commit()
                print("✅ Admin user 'iwizz' created successfully")
            
            print("\n" + "="*50)
            print("Login credentials:")
            print("Username: iwizz")
            print("Password: wizard007")
            print("="*50)
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

if __name__ == '__main__':
    create_admin_user()

