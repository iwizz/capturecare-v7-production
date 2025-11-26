#!/usr/bin/env python3
"""
Script to create or reset the admin user in the database
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'capturecare'))

from flask import Flask
from models import db, User
from config import Config
from werkzeug.security import generate_password_hash

app = Flask(__name__)
config = Config()
app.config.from_object(config)
db.init_app(app)

def create_admin_user():
    """Create or reset the admin user"""
    with app.app_context():
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
        
        print("\nLogin credentials:")
        print("Username: iwizz")
        print("Password: wizard007")

if __name__ == '__main__':
    create_admin_user()

