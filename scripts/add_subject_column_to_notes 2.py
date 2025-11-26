"""
Migration script to add 'subject' column to patient_notes table
Run this to fix the database schema mismatch
"""

import sqlite3
import os
import sys

def find_database():
    """Find the SQLite database file"""
    # Common locations
    possible_paths = [
        'capturecare/instance/capturecare.db',
        'instance/capturecare.db',
        'capturecare.db',
        'capturecare/instance/database.db',
        'instance/database.db',
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    # Search in current directory and subdirectories
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.db'):
                return os.path.join(root, file)
    
    return None

def column_exists(conn, table_name, column_name):
    """Check if a column exists in a table"""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns

def migrate_patient_notes():
    """Add subject column to patient_notes table"""
    db_path = find_database()
    
    if not db_path:
        print("❌ Could not find database file!")
        print("   Please specify the database path manually or ensure it exists.")
        return False
    
    print(f"📁 Found database: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("=" * 60)
        print("Migrating patient_notes table...")
        print("=" * 60)
        
        # Check if column already exists
        if column_exists(conn, 'patient_notes', 'subject'):
            print("✓ Column 'subject' already exists in patient_notes table")
            conn.close()
            return True
        
        # Add the subject column
        print("Adding 'subject' column to patient_notes table...")
        cursor.execute("""
            ALTER TABLE patient_notes 
            ADD COLUMN subject VARCHAR(200)
        """)
        conn.commit()
        
        # Verify it was added
        if column_exists(conn, 'patient_notes', 'subject'):
            print("✅ Successfully added 'subject' column to patient_notes table")
            conn.close()
            return True
        else:
            print("❌ Column was not added successfully")
            conn.close()
            return False
            
    except sqlite3.OperationalError as e:
        if 'duplicate column name' in str(e).lower():
            print("✓ Column 'subject' already exists (detected via error)")
            return True
        else:
            print(f"❌ SQLite error: {e}")
            return False
    except Exception as e:
        print(f"❌ Error migrating patient_notes table: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("Patient Notes Migration Script")
    print("=" * 60 + "\n")
    
    # Change to script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    os.chdir(project_root)
    print(f"📂 Working directory: {project_root}\n")
    
    success = migrate_patient_notes()
    
    if success:
        print("\n" + "=" * 60)
        print("✅ Migration completed successfully!")
        print("=" * 60)
        print("\nYou can now save notes with subjects. Your old notes are safe!")
        print("=" * 60 + "\n")
    else:
        print("\n" + "=" * 60)
        print("❌ Migration failed. Please check the error above.")
        print("=" * 60 + "\n")
        sys.exit(1)
