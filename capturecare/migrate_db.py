"""
Database migration script to add new columns for calendar functionality
Run this to add practitioner fields to users and appointments tables
"""

from web_dashboard import app, db
from sqlalchemy import text

def column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    result = db.session.execute(text(f"PRAGMA table_info({table_name})"))
    columns = [row[1] for row in result]
    return column_name in columns

def migrate_database():
    """Add new columns to existing tables"""
    with app.app_context():
        try:
            # Add columns to users table
            print("Migrating users table...")
            
            user_migrations = {
                'first_name': "ALTER TABLE users ADD COLUMN first_name VARCHAR(100)",
                'last_name': "ALTER TABLE users ADD COLUMN last_name VARCHAR(100)",
                'role': "ALTER TABLE users ADD COLUMN role VARCHAR(50) DEFAULT 'practitioner'",
                'calendar_color': "ALTER TABLE users ADD COLUMN calendar_color VARCHAR(7) DEFAULT '#00698f'",
                'google_calendar_id': "ALTER TABLE users ADD COLUMN google_calendar_id VARCHAR(200)",
                'is_active': "ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT TRUE"
            }
            
            for column, migration in user_migrations.items():
                if not column_exists('users', column):
                    db.session.execute(text(migration))
                    print(f"✓ Added column: users.{column}")
                else:
                    print(f"⊙ Column already exists: users.{column}")
            
            # Add column to appointments table
            if not column_exists('appointments', 'practitioner_id'):
                db.session.execute(text("ALTER TABLE appointments ADD COLUMN practitioner_id INTEGER"))
                print(f"✓ Added column: appointments.practitioner_id")
            else:
                print(f"⊙ Column already exists: appointments.practitioner_id")
            
            # Add new columns to patients table
            print("\nMigrating patients table...")
            
            patient_migrations = {
                'emergency_contact_email': "ALTER TABLE patients ADD COLUMN emergency_contact_email VARCHAR(120)",
                'emergency_contact_consent': "ALTER TABLE patients ADD COLUMN emergency_contact_consent BOOLEAN DEFAULT FALSE",
                'gp_name': "ALTER TABLE patients ADD COLUMN gp_name VARCHAR(200)",
                'gp_address': "ALTER TABLE patients ADD COLUMN gp_address VARCHAR(200)",
                'gp_phone': "ALTER TABLE patients ADD COLUMN gp_phone VARCHAR(20)",
                'has_gp': "ALTER TABLE patients ADD COLUMN has_gp BOOLEAN DEFAULT FALSE",
                'current_medications': "ALTER TABLE patients ADD COLUMN current_medications TEXT",
                'owns_smart_device': "ALTER TABLE patients ADD COLUMN owns_smart_device BOOLEAN DEFAULT FALSE",
                'health_focus_areas': "ALTER TABLE patients ADD COLUMN health_focus_areas TEXT",
                'terms_consent': "ALTER TABLE patients ADD COLUMN terms_consent BOOLEAN DEFAULT FALSE"
            }
            
            for column, migration in patient_migrations.items():
                if not column_exists('patients', column):
                    db.session.execute(text(migration))
                    print(f"✓ Added column: patients.{column}")
                else:
                    print(f"⊙ Column already exists: patients.{column}")
            
            # Add device_source column to health_data table
            print("\nMigrating health_data table...")
            if not column_exists('health_data', 'device_source'):
                db.session.execute(text("ALTER TABLE health_data ADD COLUMN device_source VARCHAR(20)"))
                print(f"✓ Added column: health_data.device_source")
            else:
                print(f"⊙ Column already exists: health_data.device_source")
            
            db.session.commit()
            print("\n✅ Database migration completed successfully!")
            
            # Create sample practitioners if none exist
            from models import User
            from werkzeug.security import generate_password_hash
            
            if User.query.count() == 0:
                print("\nCreating sample practitioners...")
                
                practitioners = [
                    {
                        'username': 'dr.smith',
                        'email': 'dr.smith@capturecare.com',
                        'password_hash': generate_password_hash('password123'),
                        'first_name': 'Sarah',
                        'last_name': 'Smith',
                        'role': 'practitioner',
                        'calendar_color': '#00698f',
                        'is_admin': True,
                        'is_active': True
                    },
                    {
                        'username': 'nurse.jones',
                        'email': 'nurse.jones@capturecare.com',
                        'password_hash': generate_password_hash('password123'),
                        'first_name': 'Michael',
                        'last_name': 'Jones',
                        'role': 'nurse',
                        'calendar_color': '#96b7c8',
                        'is_admin': False,
                        'is_active': True
                    },
                    {
                        'username': 'dr.chen',
                        'email': 'dr.chen@capturecare.com',
                        'password_hash': generate_password_hash('password123'),
                        'first_name': 'Lisa',
                        'last_name': 'Chen',
                        'role': 'practitioner',
                        'calendar_color': '#265063',
                        'is_admin': False,
                        'is_active': True
                    }
                ]
                
                for p in practitioners:
                    user = User(**p)
                    db.session.add(user)
                
                db.session.commit()
                print(f"✅ Created {len(practitioners)} sample practitioners")
                print("   - dr.smith / password123 (Admin)")
                print("   - nurse.jones / password123")
                print("   - dr.chen / password123")
            else:
                print(f"\n✓ Found {User.query.count()} existing users")
            
        except Exception as e:
            print(f"\n❌ Migration error: {e}")
            db.session.rollback()
            raise

if __name__ == '__main__':
    migrate_database()
