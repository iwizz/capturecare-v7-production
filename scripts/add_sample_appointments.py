#!/usr/bin/env python3
"""
Add sample appointments for existing patients
Simple version using direct database access
"""

import sqlite3
import os
from datetime import datetime, timedelta, time

# Get database path
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db_path = os.path.join(base_dir, 'capturecare', 'instance', 'capturecare.db')

if not os.path.exists(db_path):
    print(f"❌ Database not found at: {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

def add_sample_appointments():
    # Get all patients
    cursor.execute("SELECT id, first_name, last_name FROM patients")
    patients = cursor.fetchall()
    if not patients:
        print("❌ No patients found!")
        conn.close()
        return
    
    # Get all active practitioners
    cursor.execute("SELECT id, first_name, last_name FROM users WHERE is_active = 1")
    practitioners = cursor.fetchall()
    if not practitioners:
        print("❌ No active practitioners found!")
        conn.close()
        return
    
    print(f"📋 Found {len(patients)} patients and {len(practitioners)} practitioners\n")
    
    # Sample appointments - spread across next 3 weeks (including today and past week for visibility)
    # Format: (days_from_today, hour, minute, duration_minutes, patient_index, practitioner_index, title)
    today = datetime.now().date()
    
    # Filter out admin users - only use practitioners, doctors, and nurses
    cursor.execute("SELECT id, first_name, last_name FROM users WHERE is_active = 1 AND role IN ('practitioner', 'doctor', 'nurse')")
    active_practitioners = cursor.fetchall()
    
    if not active_practitioners:
        print("❌ No active practitioners (excluding admin) found!")
        conn.close()
        return
    
    practitioners = active_practitioners
    print(f"📋 Using {len(practitioners)} active practitioners (excluding admin)\n")
    
    sample_appointments = [
            # Past week (for visibility)
            (-3, 9, 0, 30, 0, 0, "Initial Consultation"),
            (-3, 14, 30, 60, 1, 1, "Follow-up Appointment"),
            (-2, 10, 0, 30, 2, 2, "Health Check"),
            (-2, 15, 0, 60, 3, 0, "Review Session"),
            (-1, 9, 30, 30, 4, 1, "Consultation"),
            (-1, 11, 0, 60, 5, 2, "Follow-up"),
            # Today
            (0, 9, 0, 30, 0, 0, "Morning Consultation"),
            (0, 10, 30, 60, 1, 1, "Health Assessment"),
            (0, 14, 0, 30, 2, 2, "Follow-up"),
            (0, 15, 30, 60, 3, 0, "Review"),
            # This week
            (1, 9, 0, 30, 0, 0, "Initial Consultation"),
            (1, 10, 30, 60, 1, 1, "Follow-up Appointment"),
            (1, 14, 0, 30, 2, 2, "Health Check"),
            (1, 15, 0, 30, 3, 0, "Review Session"),
            (2, 9, 30, 60, 4, 1, "Consultation"),
            (2, 11, 0, 30, 5, 2, "Follow-up"),
            (2, 13, 30, 60, 0, 0, "Health Assessment"),
            (2, 15, 0, 30, 1, 1, "Check-in"),
            (3, 9, 0, 30, 2, 2, "Appointment"),
            (3, 10, 30, 60, 3, 0, "Consultation"),
            (3, 14, 0, 30, 4, 1, "Follow-up"),
            (3, 15, 30, 60, 5, 2, "Health Check"),
            (4, 9, 30, 30, 0, 0, "Review"),
            (4, 11, 0, 60, 1, 1, "Consultation"),
            (4, 14, 30, 30, 2, 2, "Follow-up"),
            # Next week
            (7, 9, 0, 30, 3, 0, "Initial Consultation"),
            (7, 10, 30, 60, 4, 1, "Follow-up Appointment"),
            (7, 14, 0, 30, 5, 2, "Health Check"),
            (8, 9, 30, 60, 0, 0, "Consultation"),
            (8, 11, 0, 30, 1, 1, "Follow-up"),
            (8, 13, 30, 60, 2, 2, "Health Assessment"),
            (8, 15, 0, 30, 3, 0, "Check-in"),
            (9, 9, 0, 30, 4, 1, "Appointment"),
            (9, 10, 30, 60, 5, 2, "Consultation"),
            (9, 14, 0, 30, 0, 0, "Review"),
            (10, 9, 30, 60, 1, 1, "Health Check"),
            (10, 11, 0, 30, 2, 2, "Follow-up"),
            (10, 14, 30, 60, 3, 0, "Consultation"),
            (11, 9, 0, 30, 4, 1, "Assessment"),
            (11, 10, 30, 60, 5, 2, "Review"),
            (11, 14, 0, 30, 0, 0, "Check-in"),
            # Week after next
            (14, 9, 0, 30, 1, 1, "Follow-up"),
            (14, 10, 30, 60, 2, 2, "Consultation"),
            (14, 14, 0, 30, 3, 0, "Health Check"),
            (15, 9, 30, 60, 4, 1, "Review"),
            (15, 11, 0, 30, 5, 2, "Follow-up"),
            (15, 14, 30, 60, 0, 0, "Consultation"),
    ]
    
    appointments_created = 0
    appointments_skipped = 0
        
    for days_offset, hour, minute, duration, patient_idx, pract_idx, title in sample_appointments:
        # Calculate appointment date
        appointment_date = today + timedelta(days=days_offset)
        
        # Get patient and practitioner (wrap around if needed)
        patient = patients[patient_idx % len(patients)]
        practitioner = practitioners[pract_idx % len(practitioners)]
        
        patient_id, patient_first, patient_last = patient
        pract_id, pract_first, pract_last = practitioner
        patient_name = f"{patient_first} {patient_last}"
        pract_name = f"{pract_first} {pract_last}"
        
        # Check if appointment already exists
        # Combine date and time into start_time
        start_time = datetime.combine(appointment_date, time(hour, minute))
        
        cursor.execute("""
            SELECT id FROM appointments 
            WHERE patient_id = ? AND practitioner_id = ? 
            AND start_time = ?
        """, (patient_id, pract_id, start_time))
        
        if cursor.fetchone():
            appointments_skipped += 1
            continue
        
        # Create appointment
        end_time = start_time + timedelta(minutes=duration)
        now = datetime.now()
        
        cursor.execute("""
            INSERT INTO appointments 
            (patient_id, practitioner_id, start_time, end_time, 
             duration_minutes, title, status, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'scheduled', ?, ?, ?)
        """, (
            patient_id, pract_id, start_time, end_time,
            duration, title, f"Sample appointment for {patient_name} with {pract_name}",
            now, now
        ))
        
        appointments_created += 1
        print(f"✅ Created: {appointment_date.strftime('%Y-%m-%d')} {hour:02d}:{minute:02d} - {patient_name} with {pract_name} ({duration}min)")
    
    conn.commit()
    
    print(f"\n📊 Summary:")
    print(f"   Created: {appointments_created} appointments")
    print(f"   Skipped: {appointments_skipped} (already exist)")
    print(f"\n✅ Done! Sample appointments added successfully!")
    
    conn.close()

if __name__ == '__main__':
    add_sample_appointments()

