#!/usr/bin/env python3
"""
Add sample patient notes for all patients
Creates realistic clinical notes, follow-ups, and observations
"""

import sqlite3
import os
from datetime import datetime, timedelta
import random

# Get database path
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db_path = os.path.join(base_dir, 'capturecare', 'instance', 'capturecare.db')

if not os.path.exists(db_path):
    print(f"❌ Database not found at: {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Sample note templates
NOTE_TEMPLATES = [
    {
        'subject': 'Initial Consultation',
        'note_text': 'Patient presented for initial consultation. Discussed health goals and current lifestyle. Reviewed medical history and medications. Plan: Follow-up in 2 weeks to review progress.',
        'note_type': 'manual',
        'author': 'Dr. Smith'
    },
    {
        'subject': 'Follow-up Appointment',
        'note_text': 'Follow-up consultation completed. Patient reports feeling well. Reviewed recent health data trends. Blood pressure and heart rate within normal ranges. Continue current treatment plan.',
        'note_type': 'manual',
        'author': 'Dr. Chen'
    },
    {
        'subject': 'Health Check Results',
        'note_text': 'Completed comprehensive health assessment. All vital signs stable. Patient advised to maintain regular exercise routine and healthy diet. Next review scheduled in 1 month.',
        'note_type': 'observation',
        'author': 'Nurse Jones'
    },
    {
        'subject': 'Medication Review',
        'note_text': 'Reviewed current medications with patient. No adverse effects reported. Dosage remains appropriate. Patient understands importance of medication compliance.',
        'note_type': 'manual',
        'author': 'Dr. Smith'
    },
    {
        'subject': 'Lifestyle Discussion',
        'note_text': 'Discussed lifestyle modifications including diet and exercise. Patient motivated to make positive changes. Provided educational materials and resources. Encouraged to track daily activity.',
        'note_type': 'manual',
        'author': 'Dr. Chen'
    },
    {
        'subject': 'Progress Review',
        'note_text': 'Patient showing good progress with health goals. Weight trending downward, activity levels increasing. Continue current plan. Patient encouraged to maintain momentum.',
        'note_type': 'observation',
        'author': 'Nurse Jones'
    },
    {
        'subject': 'Blood Pressure Monitoring',
        'note_text': 'Blood pressure readings consistently within target range. Patient monitoring at home as instructed. No concerns at this time. Continue regular monitoring.',
        'note_type': 'observation',
        'author': 'Dr. Smith'
    },
    {
        'subject': 'Exercise Program Discussion',
        'note_text': 'Discussed personalized exercise program based on patient fitness level. Patient started walking program and reports feeling more energetic. Plan to gradually increase intensity.',
        'note_type': 'manual',
        'author': 'Dr. Chen'
    },
    {
        'subject': 'Sleep Quality Assessment',
        'note_text': 'Reviewed sleep patterns from health data. Patient averaging 7-8 hours per night. Sleep quality appears good. No sleep-related concerns identified.',
        'note_type': 'observation',
        'author': 'Nurse Jones'
    },
    {
        'subject': 'Nutrition Consultation',
        'note_text': 'Nutrition consultation completed. Reviewed dietary habits and provided recommendations. Patient committed to making healthier food choices. Follow-up in 2 weeks.',
        'note_type': 'manual',
        'author': 'Dr. Smith'
    },
    {
        'subject': 'Heart Rate Variability Review',
        'note_text': 'Reviewed heart rate data from wearable device. Patterns appear normal and consistent. Patient engaging in regular physical activity. Continue monitoring.',
        'note_type': 'observation',
        'author': 'Dr. Chen'
    },
    {
        'subject': 'Weight Management Progress',
        'note_text': 'Weight management progress review. Patient has lost 2kg over past month. Positive trend continuing. Patient motivated and adhering to plan. Excellent progress.',
        'note_type': 'observation',
        'author': 'Nurse Jones'
    },
    {
        'subject': 'Stress Management Discussion',
        'note_text': 'Discussed stress management techniques with patient. Patient reports work-related stress. Provided coping strategies and relaxation techniques. Follow-up scheduled.',
        'note_type': 'manual',
        'author': 'Dr. Smith'
    },
    {
        'subject': 'Activity Level Review',
        'note_text': 'Reviewed activity data from health tracking devices. Patient consistently meeting daily step goals. Activity levels have increased significantly. Keep up the great work!',
        'note_type': 'observation',
        'author': 'Dr. Chen'
    },
    {
        'subject': 'General Health Check',
        'note_text': 'Routine health check completed. All systems functioning well. Patient reports feeling healthy and energetic. No concerns identified. Continue current care plan.',
        'note_type': 'observation',
        'author': 'Nurse Jones'
    }
]

def add_sample_notes():
    # Get all patients
    cursor.execute("SELECT id, first_name, last_name FROM patients")
    patients = cursor.fetchall()
    if not patients:
        print("❌ No patients found!")
        conn.close()
        return
    
    # Get all active practitioners (for author names)
    cursor.execute("SELECT id, first_name, last_name, role FROM users WHERE is_active = 1 AND role IN ('practitioner', 'doctor', 'nurse')")
    practitioners = cursor.fetchall()
    
    if not practitioners:
        print("⚠️  No practitioners found, using default author names")
        practitioner_names = ['Dr. Smith', 'Dr. Chen', 'Nurse Jones']
    else:
        practitioner_names = [f"{'Dr.' if p[3] in ['practitioner', 'doctor'] else 'Nurse'} {p[1]} {p[2]}" for p in practitioners]
    
    print(f"📋 Found {len(patients)} patients\n")
    
    notes_created = 0
    notes_skipped = 0
    
    for patient_id, first_name, last_name in patients:
        patient_name = f"{first_name} {last_name}"
        print(f"\n📝 Adding notes for {patient_name}...")
        
        # Add 3-6 random notes per patient, spread over the past 60 days
        num_notes = random.randint(3, 6)
        
        for i in range(num_notes):
            # Random date in the past 60 days
            days_ago = random.randint(0, 60)
            note_date = datetime.now() - timedelta(days=days_ago)
            
            # Random note template
            template = random.choice(NOTE_TEMPLATES)
            
            # Check if similar note already exists for this patient
            cursor.execute("""
                SELECT id FROM patient_notes 
                WHERE patient_id = ? AND subject = ? 
                AND DATE(created_at) = DATE(?)
            """, (patient_id, template['subject'], note_date))
            
            if cursor.fetchone():
                notes_skipped += 1
                continue
            
            # Create note
            now = datetime.now()
            
            cursor.execute("""
                INSERT INTO patient_notes 
                (patient_id, subject, note_text, note_type, author, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                patient_id,
                template['subject'],
                template['note_text'],
                template['note_type'],
                random.choice(practitioner_names),
                note_date,
                note_date
            ))
            
            notes_created += 1
            print(f"  ✅ {template['subject']} - {note_date.strftime('%Y-%m-%d')}")
    
    conn.commit()
    
    print(f"\n📊 Summary:")
    print(f"   Created: {notes_created} notes")
    print(f"   Skipped: {notes_skipped} (already exist)")
    print(f"\n✅ Done! Sample notes added successfully!")
    
    conn.close()

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("Sample Patient Notes Generator")
    print("=" * 60 + "\n")
    add_sample_notes()

