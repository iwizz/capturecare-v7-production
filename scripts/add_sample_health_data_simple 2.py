#!/usr/bin/env python3
"""
Add sample health data for all patients (up to today's date)
Simple version using direct database access
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

def generate_health_data_for_patient(patient_id, days_back=90):
    """Generate realistic health data for a patient"""
    data_points = []
    today = datetime.now()
    start_date = today - timedelta(days=days_back)
    
    # Base values (will vary by patient)
    base_weight = random.uniform(60, 90)  # kg
    base_heart_rate = random.randint(65, 80)  # bpm
    base_systolic = random.randint(110, 130)  # mmHg
    base_diastolic = random.randint(70, 85)  # mmHg
    base_steps = random.randint(5000, 12000)  # steps
    base_sleep = random.uniform(6.5, 8.5)  # hours
    
    current_date = start_date
    
    while current_date <= today:
        # Weight - measured daily (90% chance)
        if random.random() > 0.1:
            weight = base_weight + random.uniform(-2, 2)
            data_points.append((
                patient_id, 'weight', round(weight, 1), 'kg',
                current_date.replace(hour=8, minute=random.randint(0, 30)),
                'withings', 'scale'
            ))
        
        # Heart Rate - multiple readings per day (70% chance)
        if random.random() > 0.3:
            for hour in [9, 12, 15, 18, 21]:
                if random.random() > 0.3:
                    hr = base_heart_rate + random.randint(-10, 15)
                    if hour in [12, 15]:
                        hr += random.randint(5, 15)
                    elif hour == 21:
                        hr -= random.randint(3, 8)
                    hr = max(50, min(100, hr))  # Keep in reasonable range
                    
                    data_points.append((
                        patient_id, 'heart_rate', hr, 'bpm',
                        current_date.replace(hour=hour, minute=random.randint(0, 59)),
                        'withings', 'watch'
                    ))
        
        # Blood Pressure - measured a few times per week (40% chance)
        if random.random() > 0.6:
            systolic = base_systolic + random.randint(-10, 10)
            diastolic = base_diastolic + random.randint(-8, 8)
            bp_time = current_date.replace(hour=random.randint(8, 10), minute=random.randint(0, 59))
            
            data_points.append((
                patient_id, 'systolic_bp', systolic, 'mmHg', bp_time, 'withings', 'scale'
            ))
            data_points.append((
                patient_id, 'diastolic_bp', diastolic, 'mmHg', bp_time, 'withings', 'scale'
            ))
        
        # Steps - daily total
        steps = base_steps + random.randint(-2000, 3000)
        if current_date.weekday() >= 5:  # Weekend
            steps = int(steps * random.uniform(0.7, 1.3))
        steps = max(0, steps)
        
        data_points.append((
            patient_id, 'steps', steps, 'steps',
            current_date.replace(hour=23, minute=59),
            'withings', 'watch'
        ))
        
        # Sleep Duration - daily
        sleep = base_sleep + random.uniform(-1, 1.5)
        if current_date.weekday() >= 5:  # Weekend
            sleep += random.uniform(0.5, 1.5)
        sleep = max(4, min(10, sleep))  # Keep in reasonable range
        
        data_points.append((
            patient_id, 'sleep_duration', round(sleep, 1), 'hours',
            current_date.replace(hour=7, minute=0),
            'withings', 'watch'
        ))
        
        # SpO2 - measured occasionally (30% chance)
        if random.random() > 0.7:
            spo2 = random.uniform(96, 100)
            data_points.append((
                patient_id, 'spo2', round(spo2, 1), '%',
                current_date.replace(hour=random.randint(10, 16), minute=random.randint(0, 59)),
                'withings', 'watch'
            ))
        
        # Body Temperature - measured occasionally (20% chance)
        if random.random() > 0.8:
            temp = random.uniform(36.0, 37.2)
            data_points.append((
                patient_id, 'body_temperature', round(temp, 1), '°C',
                current_date.replace(hour=random.randint(8, 12), minute=random.randint(0, 59)),
                'withings', 'watch'
            ))
        
        # Body Composition - measured weekly (Monday, 70% chance)
        if current_date.weekday() == 0 and random.random() > 0.3:
            fat_mass = random.uniform(10, 25)
            muscle_mass = random.uniform(40, 60)
            fat_ratio = random.uniform(15, 30)
            fat_free_mass = random.uniform(50, 70)
            bone_mass = random.uniform(2.5, 4.0)
            comp_time = current_date.replace(hour=8, minute=random.randint(0, 30))
            
            data_points.append((patient_id, 'fat_mass', round(fat_mass, 1), 'kg', comp_time, 'withings', 'scale'))
            data_points.append((patient_id, 'muscle_mass', round(muscle_mass, 1), 'kg', comp_time, 'withings', 'scale'))
            data_points.append((patient_id, 'fat_ratio', round(fat_ratio, 1), '%', comp_time, 'withings', 'scale'))
            data_points.append((patient_id, 'fat_free_mass', round(fat_free_mass, 1), 'kg', comp_time, 'withings', 'scale'))
            data_points.append((patient_id, 'bone_mass', round(bone_mass, 2), 'kg', comp_time, 'withings', 'scale'))
        
        # Calories - daily
        total_cal = random.randint(1800, 2800)
        active_cal = random.randint(200, 600)
        
        data_points.append((
            patient_id, 'total_calories', total_cal, 'kcal',
            current_date.replace(hour=23, minute=59),
            'withings', 'watch'
        ))
        data_points.append((
            patient_id, 'calories', active_cal, 'kcal',
            current_date.replace(hour=23, minute=59),
            'withings', 'watch'
        ))
        
        # Distance - daily
        distance = random.randint(3000, 10000)
        data_points.append((
            patient_id, 'distance', distance, 'm',
            current_date.replace(hour=23, minute=59),
            'withings', 'watch'
        ))
        
        # Move to next day
        current_date += timedelta(days=1)
    
    return data_points

def add_sample_health_data():
    # Get all patients
    cursor.execute("SELECT id, first_name, last_name FROM patients")
    patients = cursor.fetchall()
    if not patients:
        print("❌ No patients found!")
        conn.close()
        return
    
    today = datetime.now()
    
    print(f"📋 Found {len(patients)} patients\n")
    print("Generating health data up to today's date...\n")
    
    total_data_points = 0
    
    for patient_id, first_name, last_name in patients:
        patient_name = f"{first_name} {last_name}"
        print(f"📊 Generating data for {patient_name}...")
        
        # Check existing data count and latest date
        cursor.execute("SELECT COUNT(*), MAX(timestamp) FROM health_data WHERE patient_id = ?", (patient_id,))
        result = cursor.fetchone()
        existing_count = result[0] or 0
        latest_date_str = result[1]
        
        data_points = []
        
        if latest_date_str:
            # Parse the latest date
            try:
                latest_date = datetime.fromisoformat(latest_date_str.replace('Z', '+00:00').split('.')[0])
                if latest_date.date() >= today.date():
                    print(f"  ✓ Patient already has {existing_count} data points up to today. Skipping.")
                    continue
                else:
                    # Start from day after latest data
                    days_since_latest = (today.date() - latest_date.date()).days
                    if days_since_latest > 0:
                        print(f"  ⚠️  Patient has {existing_count} data points, latest: {latest_date.date()}")
                        print(f"     Adding data for the last {days_since_latest} days...")
                        # Generate only for missing days
                        data_points = generate_health_data_for_patient(patient_id, days_back=days_since_latest)
                    else:
                        continue
            except Exception as e:
                print(f"  ⚠️  Error parsing date: {e}, generating full range")
                data_points = generate_health_data_for_patient(patient_id, days_back=90)
        else:
            # No existing data, generate full range
            print(f"  No existing data found, generating 90 days of data...")
            data_points = generate_health_data_for_patient(patient_id, days_back=90)
        
        # Insert data
        cursor.executemany("""
            INSERT INTO health_data 
            (patient_id, measurement_type, value, unit, timestamp, source, device_source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, data_points)
        
        total_data_points += len(data_points)
        print(f"  ✅ Created {len(data_points)} data points")
    
    conn.commit()
    
    print(f"\n📊 Summary:")
    print(f"   Total data points created: {total_data_points}")
    print(f"\n✅ Done! Sample health data added successfully!")
    
    conn.close()

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("Sample Health Data Generator")
    print("=" * 60 + "\n")
    add_sample_health_data()

