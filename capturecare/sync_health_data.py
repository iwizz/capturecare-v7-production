from datetime import datetime, timedelta
from .models import db, Patient, HealthData
from .withings_auth import WithingsAuthManager
from .fetch_withings_data import WithingsDataFetcher
from .google_sheet_writer import GoogleSheetWriter
from .ai_health_reporter import AIHealthReporter
from .email_sender import EmailSender
import logging

logger = logging.getLogger(__name__)

class HealthDataSynchronizer:
    def __init__(self, config):
        self.withings_auth = WithingsAuthManager(
            config.get('WITHINGS_CLIENT_ID', ''),
            config.get('WITHINGS_CLIENT_SECRET', ''),
            config.get('WITHINGS_REDIRECT_URI', '')
        )
        
        self.google_sheets = GoogleSheetWriter(
            config.get('GOOGLE_SHEETS_CREDENTIALS', ''),
            config.get('GOOGLE_SHEET_ID', '')
        ) if config.get('GOOGLE_SHEETS_CREDENTIALS') else None
        
        self.ai_reporter = AIHealthReporter(
            config.get('OPENAI_API_KEY', '')
        ) if config.get('OPENAI_API_KEY') else None
        
        self.email_sender = EmailSender(
            config.get('SMTP_SERVER', ''),
            config.get('SMTP_PORT', 587),
            config.get('SMTP_USERNAME', ''),
            config.get('SMTP_PASSWORD', ''),
            config.get('SMTP_FROM_EMAIL', '')
        ) if config.get('SMTP_USERNAME') else None
    
    def sync_patient_data(self, patient_id, days_back=7, startdate=None, send_email=False, full_sync=False):
        try:
            patient = Patient.query.get(patient_id)
            if not patient:
                logger.error(f"Patient {patient_id} not found")
                return {'success': False, 'error': 'Patient not found'}
            
            # Get access token directly (no library needed!)
            access_token = self.withings_auth.get_access_token(patient_id)
            if not access_token:
                logger.error(f"No Withings access token for patient {patient_id}")
                return {'success': False, 'error': 'Withings not connected or token expired'}
            
            fetcher = WithingsDataFetcher(access_token)
            
            # FULL SYNC: Fetch month by month to avoid timeouts
            if full_sync:
                logger.info(f"🔄 FULL SYNC MODE: Fetching 12 months of data in monthly batches")
                
                total_measurements = 0
                total_activities = 0
                total_sleep = 0
                total_devices = 0
                
                # Start from 12 months ago
                current_start = datetime.now() - timedelta(days=365)
                end_date = datetime.now()
                
                # Fetch month by month
                month_num = 1
                while current_start < end_date:
                    # Calculate end of current month (or today if it's the last month)
                    current_end = min(current_start + timedelta(days=30), end_date)
                    
                    logger.info(f"📅 Month {month_num}/12: Fetching from {current_start.strftime('%Y-%m-%d')} to {current_end.strftime('%Y-%m-%d')}")
                    
                    try:
                        # Fetch data for this month (skip intraday to avoid memory issues)
                        month_data = fetcher.fetch_all_data(patient_id, startdate=current_start, days_back=30, skip_intraday=True)
                        
                        total_measurements += len(month_data.get('measurements', []))
                        total_activities += len(month_data.get('activities', []))
                        total_sleep += len(month_data.get('sleep', []))
                        if month_num == 1:
                            total_devices += len(month_data.get('devices', []))
                        
                        logger.info(f"✅ Month {month_num}: +{len(month_data.get('measurements', []))} measurements, "
                                  f"+{len(month_data.get('activities', []))} activities, "
                                  f"+{len(month_data.get('sleep', []))} sleep records")
                    except Exception as e:
                        logger.error(f"❌ Error fetching month {month_num}: {e}")
                    
                    # Move to next month
                    current_start = current_end
                    month_num += 1
                
                logger.info(f"🎉 FULL SYNC COMPLETE: {total_measurements} measurements, {total_activities} activities, {total_sleep} sleep records")
                
                data = {
                    'measurements': list(range(total_measurements)),  # Just for count
                    'activities': list(range(total_activities)),
                    'sleep': list(range(total_sleep)),
                    'devices': list(range(total_devices))
                }
            
            # INCREMENTAL SYNC: Normal logic
            else:
                # Use provided startdate, or calculate from last record or days_back
                if startdate is None:
                    # Check for last record to determine start date
                    last_record = HealthData.query.filter_by(
                        patient_id=patient_id
                    ).order_by(HealthData.timestamp.desc()).first()
                    
                    if last_record:
                        # Start from last record timestamp minus 1 day buffer to catch any missed data
                        startdate = last_record.timestamp - timedelta(days=1)
                        logger.info(f"📊 Last record found: {last_record.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                        logger.info(f"📅 Syncing from {startdate.strftime('%Y-%m-%d')} onwards (1 day buffer to catch missed data)")
                    else:
                        # No records exist, use days_back from today
                        startdate = datetime.now() - timedelta(days=days_back)
                        logger.info(f"📊 No existing records found. Syncing last {days_back} days from {startdate.strftime('%Y-%m-%d')}")
                else:
                    logger.info(f"📅 Using provided startdate: {startdate.strftime('%Y-%m-%d %H:%M:%S')}")
                
                data = fetcher.fetch_all_data(patient_id, startdate=startdate, days_back=days_back)
            
            if self.google_sheets:
                health_data = HealthData.query.filter(
                    HealthData.patient_id == patient_id,
                    HealthData.timestamp >= datetime.now() - timedelta(days=days_back)
                ).all()
                
                if health_data:
                    self.google_sheets.write_health_data(patient, health_data)
            
            if send_email and self.ai_reporter and self.email_sender:
                health_summary = self._get_health_summary(patient_id, days_back)
                report = self.ai_reporter.generate_health_report(patient, health_summary)
                
                self.email_sender.send_health_report(
                    patient.email,
                    f"{patient.first_name} {patient.last_name}",
                    report
                )
            
            return {
                'success': True,
                'measurements': len(data.get('measurements', [])),
                'activities': len(data.get('activities', [])),
                'sleep': len(data.get('sleep', [])),
                'devices': len(data.get('devices', []))
            }
            
        except Exception as e:
            logger.error(f"Error syncing patient data: {e}")
            return {'success': False, 'error': str(e)}
    
    def sync_all_patients(self, days_back=1):
        patients = Patient.query.filter(Patient.withings_user_id.isnot(None)).all()
        results = []
        
        for patient in patients:
            result = self.sync_patient_data(patient.id, days_back=days_back)
            results.append({
                'patient_id': patient.id,
                'patient_name': f"{patient.first_name} {patient.last_name}",
                'result': result
            })
        
        return results
    
    def _get_health_summary(self, patient_id, days_back=7):
        health_data = HealthData.query.filter(
            HealthData.patient_id == patient_id,
            HealthData.timestamp >= datetime.now() - timedelta(days=days_back)
        ).order_by(HealthData.timestamp).all()
        
        summary = {}
        for data in health_data:
            if data.measurement_type not in summary:
                summary[data.measurement_type] = []
            summary[data.measurement_type].append({
                'value': data.value,
                'unit': data.unit,
                'timestamp': data.timestamp
            })
        
        return summary
    
    def generate_health_report(self, patient_id):
        try:
            patient = Patient.query.get(patient_id)
            if not patient:
                return {'success': False, 'error': 'Patient not found'}
            
            health_summary = self._get_health_summary(patient_id, days_back=30)
            
            if not self.ai_reporter:
                return {'success': False, 'error': 'AI reporter not configured'}
            
            report = self.ai_reporter.generate_health_report(patient, health_summary)
            insights = self.ai_reporter.generate_summary_insights(patient, health_summary)
            
            return {
                'success': True,
                'report': report,
                'insights': insights
            }
            
        except Exception as e:
            logger.error(f"Error generating health report: {e}")
            return {'success': False, 'error': str(e)}
