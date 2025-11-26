#!/usr/bin/env python3
"""
Rename patients to have different names from practitioners
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

# New patient names (different from practitioners)
new_patient_names = [
    (1, 'John', 'Smith'),
    (2, 'Mary', 'Johnson'),
    (3, 'Robert', 'Chen'),
    (4, 'Jennifer', 'Williams'),
    (5, 'David', 'Thompson'),
    (6, 'Patricia', 'Martinez'),
]

def rename_patients():
    print("🔄 Renaming patients to avoid conflicts with practitioner names...\n")
    
    for patient_id, new_first, new_last in new_patient_names:
        # Get current name
        cursor.execute("SELECT first_name, last_name FROM patients WHERE id = ?", (patient_id,))
        result = cursor.fetchone()
        
        if result:
            old_first, old_last = result
            old_name = f"{old_first} {old_last}"
            new_name = f"{new_first} {new_last}"
            
            # Update patient name
            cursor.execute("""
                UPDATE patients 
                SET first_name = ?, last_name = ?
                WHERE id = ?
            """, (new_first, new_last, patient_id))
            
            print(f"✅ Patient {patient_id}: {old_name} → {new_name}")
        else:
            print(f"⚠️  Patient {patient_id} not found, skipping...")
    
    conn.commit()
    print(f"\n✅ Successfully renamed patients!")
    print(f"\n📋 Updated patient names:")
    cursor.execute("SELECT id, first_name, last_name FROM patients ORDER BY id")
    for row in cursor.fetchall():
        print(f"   {row[0]}: {row[1]} {row[2]}")
    
    conn.close()

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("Patient Name Update Script")
    print("=" * 60 + "\n")
    rename_patients()

