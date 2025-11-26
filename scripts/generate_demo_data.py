#!/usr/bin/env python3
"""
Script to generate realistic demo health data for all patients
This creates sample data for demonstration purposes

Usage:
    python scripts/generate_demo_data.py [--replace] [--days N]
    
Options:
    --replace    Automatically replace existing data without prompting
    --days N      Number of days of data to generate (default: 60)
"""
import sys
import os
from datetime import datetime, timedelta
import random
import math
import argparse

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'capturecare'))

from flask import Flask
from models import db, Patient, HealthData
from config import Config

app = Flask(__name__)
config = Config()
app.config.from_object(config)
db.init_app(app)

def generate_realistic_value(base_value, variation_percent=0.05, trend=0):
    """Generate a realistic value with small variations and optional trend"""
    variation = base_value * variation_percent * (random.random() * 2 - 1)
    trend_change = trend * random.random()
    return base_value + variation + trend_change

def generate_demo_data_for_patient(patient, days_back=60):
    """Generate realistic demo health data for a patient"""
    print(f"\nGenerating demo data for {patient.first_name} {patient.last_name}...")
    
    # Calculate age if date_of_birth is available
    age = None
    if patient.date_of_birth:
        today = datetime.now().date()
        age = int((today - patient.date_of_birth).days / 365.25)
    
    # Determine base values based on age and sex
    sex = patient.sex.lower() if patient.sex else 'male'
    
    # Base values for different metrics (will be adjusted by age/sex)
    base_values = {
        'weight': 70 if sex == 'male' else 65,  # kg
        'heart_rate': 72,  # bpm
        'systolic_bp': 120,  # mmHg
        'diastolic_bp': 80,  # mmHg
        'steps': 8000,  # daily steps
        'sleep_duration': 7.5,  # hours
        'spo2': 98,  # %
        'body_temperature': 36.6,  # °C
        'fat_mass': 15,  # kg
        'muscle_mass': 50,  # kg
        'fat_ratio': 20,  # %
        'fat_free_mass': 55,  # kg
        'bone_mass': 3,  # kg
        'basal_metabolic_rate': 1800,  # kcal
        'total_calories': 2200,  # kcal
        'calories': 400,  # active kcal
        'distance': 6000,  # meters
        'hydration': 60,  # %
        'vo2_max': 45,  # ml/kg/min
        'pwv': 7,  # m/s
        'vascular_age': age if age else 45,  # years
        'height': 170,  # cm
    }
    
    # Adjust base values based on age and sex
    if age:
        if age > 60:
            base_values['heart_rate'] = 68
            base_values['systolic_bp'] = 130
            base_values['diastolic_bp'] = 85
            base_values['steps'] = 6000
            base_values['sleep_duration'] = 7.0
        elif age < 30:
            base_values['heart_rate'] = 75
            base_values['systolic_bp'] = 115
            base_values['diastolic_bp'] = 75
            base_values['steps'] = 10000
            base_values['sleep_duration'] = 8.0
        
        if sex == 'female':
            base_values['weight'] -= 5
            base_values['muscle_mass'] -= 8
            base_values['fat_mass'] += 3
            base_values['basal_metabolic_rate'] -= 200
            base_values['total_calories'] -= 300
            base_values['vo2_max'] -= 5
    
    # Generate data for the last N days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    data_points = []
    current_date = start_date
    
    # Track trends (slight improvements over time for demo)
    trends = {
        'weight': -0.01,  # Slight weight loss trend
        'steps': 5,  # Slight increase in steps
        'heart_rate': -0.02,  # Slight improvement
        'sleep_duration': 0.01,  # Slight improvement
    }
    
    while current_date <= end_date:
        day_offset = (current_date - start_date).days
        
        # Weight - measured daily in morning
        if random.random() > 0.1:  # 90% chance of measurement
            weight = generate_realistic_value(
                base_values['weight'] + trends['weight'] * day_offset,
                variation_percent=0.02
            )
            data_points.append(HealthData(
                patient_id=patient.id,
                measurement_type='weight',
                value=round(weight, 1),
                unit='kg',
                timestamp=current_date.replace(hour=8, minute=0) + timedelta(minutes=random.randint(0, 30)),
                source='withings',
                device_source='scale'
            ))
        
        # Heart Rate - multiple readings per day (watch)
        if random.random() > 0.2:  # 80% chance
            for hour in [9, 12, 15, 18, 21]:
                if random.random() > 0.3:  # 70% chance per time
                    hr = generate_realistic_value(
                        base_values['heart_rate'] + trends['heart_rate'] * day_offset,
                        variation_percent=0.15
                    )
                    # Add some variation based on activity
                    if hour in [12, 15]:  # Afternoon - slightly higher
                        hr += random.randint(5, 15)
                    elif hour == 21:  # Evening - lower
                        hr -= random.randint(3, 8)
                    
                    data_points.append(HealthData(
                        patient_id=patient.id,
                        measurement_type='heart_rate',
                        value=round(hr),
                        unit='bpm',
                        timestamp=current_date.replace(hour=hour, minute=random.randint(0, 59)),
                        source='withings',
                        device_source='watch'
                    ))
        
        # Blood Pressure - measured a few times per week
        if random.random() > 0.6:  # 40% chance (fewer measurements)
            systolic = generate_realistic_value(
                base_values['systolic_bp'],
                variation_percent=0.08
            )
            diastolic = generate_realistic_value(
                base_values['diastolic_bp'],
                variation_percent=0.10
            )
            bp_time = current_date.replace(hour=random.randint(8, 10), minute=random.randint(0, 59))
            
            data_points.append(HealthData(
                patient_id=patient.id,
                measurement_type='systolic_bp',
                value=round(systolic),
                unit='mmHg',
                timestamp=bp_time,
                source='withings',
                device_source='scale'
            ))
            data_points.append(HealthData(
                patient_id=patient.id,
                measurement_type='diastolic_bp',
                value=round(diastolic),
                unit='mmHg',
                timestamp=bp_time,
                source='withings',
                device_source='scale'
            ))
        
        # Steps - daily total
        steps = generate_realistic_value(
            base_values['steps'] + trends['steps'] * day_offset,
            variation_percent=0.25
        )
        # Add some day-of-week variation (weekends might be different)
        if current_date.weekday() >= 5:  # Weekend
            steps *= random.uniform(0.7, 1.3)
        data_points.append(HealthData(
            patient_id=patient.id,
            measurement_type='steps',
            value=round(steps),
            unit='steps',
            timestamp=current_date.replace(hour=23, minute=59),
            source='withings',
            device_source='watch'
        ))
        
        # Sleep Duration - daily
        sleep = generate_realistic_value(
            base_values['sleep_duration'] + trends['sleep_duration'] * day_offset,
            variation_percent=0.15
        )
        # Weekend sleep might be longer
        if current_date.weekday() >= 5:
            sleep += random.uniform(0.5, 1.5)
        data_points.append(HealthData(
            patient_id=patient.id,
            measurement_type='sleep_duration',
            value=round(sleep, 1),
            unit='hours',
            timestamp=current_date.replace(hour=7, minute=0),
            source='withings',
            device_source='watch'
        ))
        
        # SpO2 - measured occasionally
        if random.random() > 0.7:  # 30% chance
            spo2 = generate_realistic_value(base_values['spo2'], variation_percent=0.01)
            data_points.append(HealthData(
                patient_id=patient.id,
                measurement_type='spo2',
                value=round(spo2, 1),
                unit='%',
                timestamp=current_date.replace(hour=random.randint(10, 16), minute=random.randint(0, 59)),
                source='withings',
                device_source='watch'
            ))
        
        # Body Temperature - measured occasionally
        if random.random() > 0.8:  # 20% chance
            temp = generate_realistic_value(base_values['body_temperature'], variation_percent=0.02)
            data_points.append(HealthData(
                patient_id=patient.id,
                measurement_type='body_temperature',
                value=round(temp, 1),
                unit='°C',
                timestamp=current_date.replace(hour=random.randint(8, 12), minute=random.randint(0, 59)),
                source='withings',
                device_source='watch'
            ))
        
        # Body Composition - measured weekly
        if current_date.weekday() == 0 and random.random() > 0.3:  # Monday, 70% chance
            fat_mass = generate_realistic_value(base_values['fat_mass'], variation_percent=0.05)
            muscle_mass = generate_realistic_value(base_values['muscle_mass'], variation_percent=0.03)
            fat_ratio = generate_realistic_value(base_values['fat_ratio'], variation_percent=0.05)
            fat_free_mass = generate_realistic_value(base_values['fat_free_mass'], variation_percent=0.03)
            bone_mass = generate_realistic_value(base_values['bone_mass'], variation_percent=0.05)
            
            comp_time = current_date.replace(hour=8, minute=random.randint(0, 30))
            
            data_points.append(HealthData(
                patient_id=patient.id,
                measurement_type='fat_mass',
                value=round(fat_mass, 1),
                unit='kg',
                timestamp=comp_time,
                source='withings',
                device_source='scale'
            ))
            data_points.append(HealthData(
                patient_id=patient.id,
                measurement_type='muscle_mass',
                value=round(muscle_mass, 1),
                unit='kg',
                timestamp=comp_time,
                source='withings',
                device_source='scale'
            ))
            data_points.append(HealthData(
                patient_id=patient.id,
                measurement_type='fat_ratio',
                value=round(fat_ratio, 1),
                unit='%',
                timestamp=comp_time,
                source='withings',
                device_source='scale'
            ))
            data_points.append(HealthData(
                patient_id=patient.id,
                measurement_type='fat_free_mass',
                value=round(fat_free_mass, 1),
                unit='kg',
                timestamp=comp_time,
                source='withings',
                device_source='scale'
            ))
            data_points.append(HealthData(
                patient_id=patient.id,
                measurement_type='bone_mass',
                value=round(bone_mass, 2),
                unit='kg',
                timestamp=comp_time,
                source='withings',
                device_source='scale'
            ))
        
        # Calories - daily
        total_cal = generate_realistic_value(base_values['total_calories'], variation_percent=0.20)
        active_cal = generate_realistic_value(base_values['calories'], variation_percent=0.30)
        
        data_points.append(HealthData(
            patient_id=patient.id,
            measurement_type='total_calories',
            value=round(total_cal),
            unit='kcal',
            timestamp=current_date.replace(hour=23, minute=59),
            source='withings',
            device_source='watch'
        ))
        data_points.append(HealthData(
            patient_id=patient.id,
            measurement_type='calories',
            value=round(active_cal),
            unit='kcal',
            timestamp=current_date.replace(hour=23, minute=59),
            source='withings',
            device_source='watch'
        ))
        
        # Distance - daily
        distance = generate_realistic_value(base_values['distance'], variation_percent=0.25)
        data_points.append(HealthData(
            patient_id=patient.id,
            measurement_type='distance',
            value=round(distance),
            unit='m',
            timestamp=current_date.replace(hour=23, minute=59),
            source='withings',
            device_source='watch'
        ))
        
        # BMR - measured occasionally
        if random.random() > 0.9:  # 10% chance
            bmr = generate_realistic_value(base_values['basal_metabolic_rate'], variation_percent=0.05)
            data_points.append(HealthData(
                patient_id=patient.id,
                measurement_type='basal_metabolic_rate',
                value=round(bmr),
                unit='kcal',
                timestamp=current_date.replace(hour=8, minute=0),
                source='withings',
                device_source='scale'
            ))
        
        # Move to next day
        current_date += timedelta(days=1)
    
    # Add all data points to database
    print(f"  Generated {len(data_points)} data points")
    for data_point in data_points:
        db.session.add(data_point)
    
    return len(data_points)

def main():
    """Main function to generate demo data for all patients"""
    parser = argparse.ArgumentParser(description='Generate realistic demo health data for all patients')
    parser.add_argument('--replace', action='store_true', help='Automatically replace existing data without prompting')
    parser.add_argument('--days', type=int, default=60, help='Number of days of data to generate (default: 60)')
    args = parser.parse_args()
    
    with app.app_context():
        # Create tables if they don't exist
        try:
            db.create_all()
            print("Database tables verified/created")
        except Exception as e:
            print(f"Note: {e}")
        
        patients = Patient.query.all()
        
        if not patients:
            print("No patients found in database. Please add patients first.")
            return
        
        print(f"Found {len(patients)} patient(s)")
        print("=" * 60)
        
        total_data_points = 0
        for patient in patients:
            try:
                # Check if patient already has data
                existing_count = HealthData.query.filter_by(patient_id=patient.id).count()
                if existing_count > 0:
                    if args.replace:
                        # Delete existing data
                        HealthData.query.filter_by(patient_id=patient.id).delete()
                        print(f"  Deleted existing data for {patient.first_name} {patient.last_name}")
                    else:
                        response = input(f"\n{patient.first_name} {patient.last_name} already has {existing_count} data points. Replace? (y/n): ")
                        if response.lower() != 'y':
                            print(f"  Skipping {patient.first_name} {patient.last_name}")
                            continue
                        else:
                            # Delete existing data
                            HealthData.query.filter_by(patient_id=patient.id).delete()
                            print(f"  Deleted existing data for {patient.first_name} {patient.last_name}")
                
                count = generate_demo_data_for_patient(patient, days_back=args.days)
                total_data_points += count
                
            except Exception as e:
                print(f"  Error generating data for {patient.first_name} {patient.last_name}: {e}")
                db.session.rollback()
                continue
        
        try:
            db.session.commit()
            print("\n" + "=" * 60)
            print(f"✅ Successfully generated {total_data_points} demo data points!")
            print("=" * 60)
        except Exception as e:
            print(f"\n❌ Error committing data: {e}")
            db.session.rollback()
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    main()

