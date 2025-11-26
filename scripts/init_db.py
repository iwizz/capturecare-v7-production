import os
from capturecare.web_dashboard import app, db
from capturecare.models import User

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Create default admin if not exists (for development)
        if os.getenv('FLASK_ENV') == 'development':
            existing_admin = User.query.filter_by(username='admin').first()
            if not existing_admin:
                admin_user = User(
                    username='admin',
                    email='admin@capturecare.com',
                    first_name='System',
                    last_name='Administrator',
                    role='admin',
                    is_admin=True,
                    is_active=True,
                    calendar_color='#00698f'
                )
                admin_user.set_password('admin123')
                db.session.add(admin_user)
                db.session.commit()
                print("Default admin user created (username: admin, password: admin123)")
        print("Database initialized successfully!")
