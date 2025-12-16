#!/usr/bin/env python3
"""
Withings Data Fetcher - Direct API Implementation
Uses direct HTTP requests to Withings API instead of withings-api library
"""

import os
import requests
import json
import time
from datetime import datetime, timedelta, timezone
from .models import db, HealthData, Device, Patient
import logging
from sqlalchemy.exc import OperationalError
from .tz_utils import to_local

logger = logging.getLogger(__name__)

def safe_db_commit(max_retries=5, retry_delay=0.1):
    """Safely commit database changes with retry logic for SQLite locks"""
    for attempt in range(max_retries):
        try:
            db.session.commit()
            return True
        except OperationalError as e:
            if 'database is locked' in str(e).lower() or 'locked' in str(e).lower():
                if attempt < max_retries - 1:
                    logger.warning(f"Database locked, retrying commit (attempt {attempt + 1}/{max_retries})...")
                    db.session.rollback()
                    time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                    continue
                else:
                    logger.error(f"Database lock persisted after {max_retries} attempts")
                    db.session.rollback()
                    return False
            else:
                logger.error(f"Database error during commit: {e}")
                db.session.rollback()
                return False
        except Exception as e:
            logger.error(f"Unexpected error during commit: {e}")
            db.session.rollback()
            return False
    return False

TOKENS_DIR = 'tokens'

# Official Withings measurement type mapping from API documentation
MEASURE_TYPE_MAP = {
    1: "weight", 4: "height", 5: "fat_free_mass", 6: "fat_ratio",
    8: "fat_mass", 9: "diastolic_bp", 10: "systolic_bp", 11: "heart_rate",
    12: "temperature", 54: "spo2", 76: "muscle_mass", 77: "hydration",
    88: "bone_mass", 91: "pwv", 123: "vo2_max", 155: "vascular_age",
    226: "basal_metabolic_rate",
}

MEASURE_UNITS = {
    1: "kg", 4: "m", 5: "kg", 6: "%", 8: "kg", 9: "mmHg", 10: "mmHg",
    11: "bpm", 12: "°C", 54: "%", 76: "kg", 77: "%", 88: "kg",
    91: "m/s", 123: "ml/min/kg", 155: "years", 226: "kcal",
}


class WithingsDataFetcher:
    def __init__(self, access_token):
        """Initialize with access token from custom OAuth"""
        self.access_token = access_token
    
    def fetch_all_data(self, patient_id, startdate=None, days_back=7):
        """Main method to fetch all types of data
        
        Args:
            patient_id: Patient ID
            startdate: Start date for fetching (datetime). If None, uses days_back from today
            days_back: Number of days back from today if startdate is not provided
        """
        try:
            patient = Patient.query.get(patient_id)
            if not patient:
                raise ValueError(f"Patient {patient_id} not found")
            
            enddate = datetime.now()
            
            # Use provided startdate, or calculate from days_back
            if startdate is None:
                startdate = enddate - timedelta(days=days_back)
            
            logger.info(f"📅 Fetching data for {patient.email} from {startdate.strftime('%Y-%m-%d %H:%M:%S')} to {enddate.strftime('%Y-%m-%d %H:%M:%S')}")
            
            data_collected = {
                'measurements': [],
                'activities': [],
                'sleep': [],
                'devices': []
            }
            
            # 1. Fetch body measurements
            try:
                measurements = self.fetch_measurements(patient_id, startdate, enddate)
                data_collected['measurements'] = measurements
                logger.info(f"✅ Fetched {len(measurements)} body measurements")
            except Exception as e:
                logger.error(f"❌ Error fetching measurements: {e}")
            
            # 2. Fetch activity data
            try:
                activities = self.fetch_activities(patient_id, startdate, enddate)
                data_collected['activities'] = activities
                logger.info(f"✅ Fetched {len(activities)} activity records")
            except Exception as e:
                logger.error(f"❌ Error fetching activities: {e}")
            
            # 3. Fetch sleep data
            try:
                sleep_data = self.fetch_sleep_data(patient_id, startdate, enddate)
                data_collected['sleep'] = sleep_data
                logger.info(f"✅ Fetched {len(sleep_data)} sleep records")
            except Exception as e:
                logger.error(f"❌ Error fetching sleep data: {e}")
            
            # 4. Fetch devices
            try:
                devices = self.fetch_devices(patient_id)
                data_collected['devices'] = devices
                logger.info(f"✅ Fetched {len(devices)} devices")
            except Exception as e:
                logger.error(f"❌ Error fetching devices: {e}")
            
            # 5. Fetch intraday heart rate from smartwatch
            try:
                intraday_hr = self.fetch_intraday_heart_rate(patient_id, startdate, enddate)
                data_collected['intraday_hr'] = intraday_hr
                logger.info(f"✅ Fetched {len(intraday_hr)} intraday heart rate measurements")
            except Exception as e:
                logger.error(f"❌ Error fetching intraday heart rate: {e}")
            
            return data_collected
            
        except Exception as e:
            logger.error(f"Error in fetch_all_data: {e}")
            import traceback
            traceback.print_exc()
            return {'measurements': [], 'activities': [], 'sleep': [], 'devices': []}
    
    def fetch_measurements(self, patient_id, startdate, enddate):
        """Fetch body composition measurements using direct API calls"""
        measurements = []
        
        try:
            url = "https://wbsapi.withings.net/measure"
            params = {
                "action": "getmeas",
                "category": 1,
                "startdate": int(startdate.timestamp()),
                "enddate": int(enddate.timestamp())
            }
            
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            # Handle pagination
            all_measuregrps = []
            offset = 0
            more = 1
            page = 1
            
            while more and page <= 50:
                if offset > 0:
                    params["offset"] = offset
                
                logger.info(f"📄 Fetching measurements page {page}...")
                resp = requests.post(url, data=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                
                if data.get("status") == 0 and data.get("body", {}).get("measuregrps"):
                    measuregrps = data["body"]["measuregrps"]
                    all_measuregrps.extend(measuregrps)
                    more = data["body"].get("more", 0)
                    offset = data["body"].get("offset", 0)
                    logger.info(f"   Found {len(measuregrps)} measurement groups")
                    page += 1
                else:
                    logger.info(f"   No more data (status: {data.get('status')})")
                    break
            
            # Process and save measurements
            for grp in all_measuregrps:
                # Convert UTC timestamp to AEST/AEDT
                utc_timestamp = datetime.fromtimestamp(grp['date'], tz=timezone.utc)
                timestamp = to_local(utc_timestamp).replace(tzinfo=None)  # Store as naive datetime in local time
                
                for measure in grp.get('measures', []):
                    value = measure['value'] * (10 ** measure['unit'])
                    mtype = measure.get('type', '')
                    measurement_name = MEASURE_TYPE_MAP.get(mtype, f'unknown_{mtype}')
                    unit = MEASURE_UNITS.get(mtype, '')
                    
                    # Save to database (avoid duplicates)
                    existing = HealthData.query.filter_by(
                        patient_id=patient_id,
                        measurement_type=measurement_name,
                        timestamp=timestamp
                    ).first()
                    
                    if not existing:
                        # Mark heart rate from scales with device_source='scale'
                        device_src = 'scale' if mtype == 11 else None
                        health_data = HealthData(
                            patient_id=patient_id,
                            measurement_type=measurement_name,
                            value=value,
                            unit=unit,
                            timestamp=timestamp,
                            source='withings',
                            device_source=device_src
                        )
                        db.session.add(health_data)
                        measurements.append({
                            'type': measurement_name,
                            'value': value,
                            'unit': unit,
                            'timestamp': timestamp
                        })
            
            if safe_db_commit():
                logger.info(f"💾 Saved {len(measurements)} new measurements to database")
            else:
                logger.error("Failed to commit measurements to database")
            
        except Exception as e:
            logger.error(f"Error in fetch_measurements: {e}")
            db.session.rollback()
        
        return measurements
    
    def fetch_activities(self, patient_id, startdate, enddate):
        """Fetch activity data using direct API calls"""
        activities = []
        
        try:
            url = "https://wbsapi.withings.net/v2/measure"
            params = {
                "action": "getactivity",
                "startdateymd": startdate.strftime("%Y-%m-%d"),
                "enddateymd": enddate.strftime("%Y-%m-%d")
            }
            
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            resp = requests.post(url, data=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("status") == 0 and data.get("body", {}).get("activities"):
                activity_list = data["body"]["activities"]
                
                activity_mapping = {
                    'steps': ('steps', 'count'),
                    'distance': ('distance', 'm'),
                    'calories': ('calories', 'kcal'),
                    'totalcalories': ('total_calories', 'kcal'),
                    'hr_average': ('heart_rate', 'bpm'),
                }
                
                for activity in activity_list:
                    date_str = activity.get('date', '')
                    if date_str:
                        timestamp = datetime.strptime(date_str, '%Y-%m-%d').replace(hour=12)
                        
                        for field, (metric_type, unit) in activity_mapping.items():
                            if field in activity and activity[field] is not None:
                                value = activity[field]
                                if value > 0:
                                    # Avoid duplicates
                                    existing = HealthData.query.filter_by(
                                        patient_id=patient_id,
                                        measurement_type=metric_type,
                                        timestamp=timestamp
                                    ).first()
                                    
                                    if not existing:
                                        health_data = HealthData(
                                            patient_id=patient_id,
                                            measurement_type=metric_type,
                                            value=float(value),
                                            unit=unit,
                                            timestamp=timestamp,
                                            source='withings'
                                        )
                                        db.session.add(health_data)
                                        activities.append({
                                            'type': metric_type,
                                            'value': value,
                                            'unit': unit,
                                            'timestamp': timestamp
                                        })
                
                if safe_db_commit():
                    logger.info(f"💾 Saved {len(activities)} new activity records to database")
                else:
                    logger.error("Failed to commit activities to database")
                
        except Exception as e:
            logger.error(f"Error in fetch_activities: {e}")
            db.session.rollback()
        
        return activities
    
    def fetch_sleep_data(self, patient_id, startdate, enddate):
        """Fetch sleep data using direct API calls - sleep durations in HOURS"""
        sleep_data = []
        
        try:
            url = "https://wbsapi.withings.net/v2/sleep"
            params = {
                "action": "getsummary",
                "startdateymd": startdate.strftime("%Y-%m-%d"),
                "enddateymd": enddate.strftime("%Y-%m-%d")
            }
            
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            resp = requests.post(url, data=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("status") == 0 and data.get("body", {}).get("series"):
                sleep_list = data["body"]["series"]
                
                sleep_mapping = {
                    'deepsleepduration': ('deep_sleep', 'hours', 1/3600),
                    'lightsleepduration': ('light_sleep', 'hours', 1/3600),
                    'remsleepduration': ('rem_sleep', 'hours', 1/3600),
                    'sleep_score': ('sleep_score', 'score', 1),
                    'hr_average': ('sleep_hr_avg', 'bpm', 1),
                    'wakeupcount': ('wakeup_count', 'count', 1),
                }
                
                for sleep_session in sleep_list:
                    # Convert UTC timestamp to AEST/AEDT
                    utc_timestamp = datetime.fromtimestamp(sleep_session.get('startdate', 0), tz=timezone.utc)
                    timestamp = to_local(utc_timestamp).replace(tzinfo=None)  # Store as naive datetime in local time
                    data_obj = sleep_session.get('data', {})
                    
                    # Calculate total sleep duration
                    total_seconds = 0
                    for field in ['deepsleepduration', 'lightsleepduration', 'remsleepduration']:
                        if field in data_obj:
                            total_seconds += data_obj[field]
                    
                    if total_seconds > 0:
                        total_hours = round(total_seconds / 3600, 2)
                        
                        existing = HealthData.query.filter_by(
                            patient_id=patient_id,
                            measurement_type='sleep_duration',
                            timestamp=timestamp
                        ).first()
                        
                        if not existing:
                            health_data = HealthData(
                                patient_id=patient_id,
                                measurement_type='sleep_duration',
                                value=total_hours,
                                unit='hours',
                                timestamp=timestamp,
                                source='withings'
                            )
                            db.session.add(health_data)
                            sleep_data.append({
                                'type': 'sleep_duration',
                                'value': total_hours,
                                'unit': 'hours',
                                'timestamp': timestamp
                            })
                    
                    # Extract other sleep metrics
                    for field, (metric_type, unit, conversion) in sleep_mapping.items():
                        if field in data_obj and data_obj[field] is not None:
                            raw_value = data_obj[field]
                            if raw_value > 0:
                                converted_value = round(raw_value * conversion, 2) if unit == 'hours' else raw_value
                                
                                existing = HealthData.query.filter_by(
                                    patient_id=patient_id,
                                    measurement_type=metric_type,
                                    timestamp=timestamp
                                ).first()
                                
                                if not existing:
                                    health_data = HealthData(
                                        patient_id=patient_id,
                                        measurement_type=metric_type,
                                        value=float(converted_value),
                                        unit=unit,
                                        timestamp=timestamp,
                                        source='withings'
                                    )
                                    db.session.add(health_data)
                                    sleep_data.append({
                                        'type': metric_type,
                                        'value': converted_value,
                                        'unit': unit,
                                        'timestamp': timestamp
                                    })
                
                if safe_db_commit():
                    logger.info(f"💾 Saved {len(sleep_data)} new sleep records to database")
                else:
                    logger.error("Failed to commit sleep data to database")
                
        except Exception as e:
            logger.error(f"Error in fetch_sleep_data: {e}")
            db.session.rollback()
        
        return sleep_data
    
    def fetch_devices(self, patient_id):
        """Fetch device list using direct API calls"""
        devices = []
        
        try:
            url = "https://wbsapi.withings.net/v2/user"
            params = {"action": "getdevice"}
            
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            resp = requests.post(url, data=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("status") == 0 and data.get("body", {}).get("devices"):
                device_list = data["body"]["devices"]
                
                for device in device_list:
                    existing_device = Device.query.filter_by(
                        patient_id=patient_id,
                        device_id=device.get('deviceid', '')
                    ).first()
                    
                    if not existing_device:
                        new_device = Device(
                            patient_id=patient_id,
                            device_type=device.get('type', 'unknown'),
                            device_id=device.get('deviceid', ''),
                            device_model=device.get('model', ''),
                            last_sync=datetime.utcnow(),
                            status='active'
                        )
                        db.session.add(new_device)
                        devices.append({
                            'type': device.get('type'),
                            'model': device.get('model'),
                            'id': device.get('deviceid')
                        })
                    else:
                        existing_device.last_sync = datetime.utcnow()
                        existing_device.status = 'active'
                
                if safe_db_commit():
                    logger.info(f"💾 Updated {len(devices)} devices in database")
                else:
                    logger.error("Failed to commit devices to database")
                
        except Exception as e:
            logger.error(f"Error in fetch_devices: {e}")
            db.session.rollback()
        
        return devices
    
    def fetch_intraday_heart_rate(self, patient_id, startdate, enddate):
        """Fetch detailed intraday heart rate data from smartwatch using getintradayactivity"""
        intraday_hr_data = []
        
        try:
            url = "https://wbsapi.withings.net/v2/measure"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            # Process day by day (API limit is 24 hours per request)
            current_date = startdate
            while current_date <= enddate:
                day_start = int(current_date.timestamp())
                day_end = int((current_date + timedelta(days=1)).timestamp()) - 1
                
                params = {
                    "action": "getintradayactivity",
                    "startdate": day_start,
                    "enddate": day_end,
                    "data_fields": "heart_rate"
                }
                
                try:
                    resp = requests.post(url, data=params, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    
                    if data.get("status") == 0 and data.get("body", {}).get("series"):
                        series = data["body"]["series"]
                        logger.info(f"📊 Found {len(series)} intraday measurements for {current_date.strftime('%Y-%m-%d')}")
                        
                        for timestamp_str, metrics in series.items():
                            hr_value = metrics.get('heart_rate')
                            
                            if hr_value and hr_value > 0:
                                # Convert UTC timestamp to AEST/AEDT
                                utc_timestamp = datetime.fromtimestamp(int(timestamp_str), tz=timezone.utc)
                                timestamp = to_local(utc_timestamp).replace(tzinfo=None)  # Store as naive datetime in local time
                                
                                # Avoid duplicates - check for watch source data
                                existing = HealthData.query.filter_by(
                                    patient_id=patient_id,
                                    measurement_type='heart_rate',
                                    timestamp=timestamp,
                                    device_source='watch'
                                ).first()
                                
                                if not existing:
                                    health_data = HealthData(
                                        patient_id=patient_id,
                                        measurement_type='heart_rate',
                                        value=float(hr_value),
                                        unit='bpm',
                                        timestamp=timestamp,
                                        source='withings',
                                        device_source='watch'
                                    )
                                    db.session.add(health_data)
                                    intraday_hr_data.append({
                                        'value': hr_value,
                                        'timestamp': timestamp
                                    })
                    
                    elif data.get("status") != 0:
                        logger.warning(f"⚠️ API returned status {data.get('status')} for {current_date.strftime('%Y-%m-%d')}")
                
                except Exception as e:
                    logger.error(f"❌ Error fetching intraday data for {current_date.strftime('%Y-%m-%d')}: {e}")
                
                current_date += timedelta(days=1)
            
            if intraday_hr_data:
                if safe_db_commit():
                    logger.info(f"💾 Saved {len(intraday_hr_data)} intraday heart rate measurements")
                else:
                    logger.error("Failed to commit intraday heart rate data to database")
            
        except Exception as e:
            logger.error(f"Error in fetch_intraday_heart_rate: {e}")
            db.session.rollback()
        
        return intraday_hr_data
