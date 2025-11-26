#!/usr/bin/env python3
"""
Update patient emails to match their new names
"""

import sqlite3
import os

# Get database path
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db_path = os.path.join(base_dir, 'capturecare', 'instance', 'capturecare.db')

if not os.path.exists(db_path):
    print(f"❌ Database not found at: {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# New email addresses matching the new names
patient_email_updates = [
    (1, 'john.smith@email.com'),
    (2, 'mary.johnson@email.com'),
    (3, 'robert.chen@email.com'),
    (4, 'jennifer.williams@email.com'),
    (5, 'david.thompson@email.com'),
    (6, 'patricia.martinez@email.com'),
]

def update_patient_emails():
    print("🔄 Updating patient emails to match new names...\n")
    
    for patient_id, new_email in patient_email_updates:
        # Get current name and email
        cursor.execute("SELECT first_name, last_name, email FROM patients WHERE id = ?", (patient_id,))
        result = cursor.fetchone()
        
        if result:
            first_name, last_name, old_email = result
            patient_name = f"{first_name} {last_name}"
            
            # Update email
            cursor.execute("""
                UPDATE patients 
                SET email = ?
                WHERE id = ?
            """, (new_email, patient_id))
            
            print(f"✅ Patient {patient_id} ({patient_name}): {old_email} → {new_email}")
        else:
            print(f"⚠️  Patient {patient_id} not found, skipping...")
    
    conn.commit()
    print(f"\n✅ Successfully updated patient emails!")
    print(f"\n📋 Updated patient information:")
    cursor.execute("SELECT id, first_name, last_name, email FROM patients ORDER BY id")
    for row in cursor.fetchall():
        print(f"   {row[0]}: {row[1]} {row[2]} - {row[3]}")
    
    conn.close()

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("Patient Email Update Script")
    print("=" * 60 + "\n")
    update_patient_emails()

