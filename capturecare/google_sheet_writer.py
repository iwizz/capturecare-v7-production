import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class GoogleSheetWriter:
    def __init__(self, credentials_json, sheet_id):
        self.sheet_id = sheet_id
        
        if credentials_json:
            try:
                creds_dict = json.loads(credentials_json) if isinstance(credentials_json, str) else credentials_json
                scopes = [
                    'https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/drive'
                ]
                self.credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
                self.client = gspread.authorize(self.credentials)
                self.sheet = None
            except Exception as e:
                logger.error(f"Error initializing Google Sheets: {e}")
                self.client = None
                self.sheet = None
        else:
            self.client = None
            self.sheet = None
    
    def open_sheet(self, worksheet_name='Health Data'):
        if not self.client:
            return False
        
        try:
            spreadsheet = self.client.open_by_key(self.sheet_id)
            
            try:
                self.sheet = spreadsheet.worksheet(worksheet_name)
            except gspread.WorksheetNotFound:
                self.sheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=20)
                headers = [
                    'Patient ID', 'Patient Name', 'Email', 'Date', 'Time',
                    'Measurement Type', 'Value', 'Unit', 'Source', 'Timestamp'
                ]
                self.sheet.append_row(headers)
            
            return True
        except Exception as e:
            logger.error(f"Error opening Google Sheet: {e}")
            return False
    
    def write_health_data(self, patient, health_data_list):
        if not self.sheet:
            if not self.open_sheet():
                return False
        
        try:
            rows = []
            for data in health_data_list:
                row = [
                    patient.id,
                    f'{patient.first_name} {patient.last_name}',
                    patient.email,
                    data.timestamp.strftime('%Y-%m-%d'),
                    data.timestamp.strftime('%H:%M:%S'),
                    data.measurement_type,
                    data.value,
                    data.unit or '',
                    data.source,
                    data.timestamp.isoformat()
                ]
                rows.append(row)
            
            if rows:
                self.sheet.append_rows(rows)
                logger.info(f"Wrote {len(rows)} rows to Google Sheet for patient {patient.id}")
                return True
            
        except Exception as e:
            logger.error(f"Error writing to Google Sheet: {e}")
            return False
        
        return False
    
    def write_consolidated_data(self, patient, consolidated_metrics):
        worksheet_name = f'Patient_{patient.id}_Consolidated'
        
        if not self.client:
            return False
        
        try:
            spreadsheet = self.client.open_by_key(self.sheet_id)
            
            try:
                sheet = spreadsheet.worksheet(worksheet_name)
            except gspread.WorksheetNotFound:
                sheet = spreadsheet.add_worksheet(title=worksheet_name, rows=500, cols=30)
                headers = ['Date'] + list(consolidated_metrics.keys())
                sheet.append_row(headers)
            
            dates = sorted(set(
                data['timestamp'].strftime('%Y-%m-%d') 
                for metrics in consolidated_metrics.values() 
                for data in metrics
            ))
            
            for date_str in dates:
                row = [date_str]
                for metric_type in consolidated_metrics.keys():
                    metric_data = consolidated_metrics[metric_type]
                    value = ''
                    for data in metric_data:
                        if data['timestamp'].strftime('%Y-%m-%d') == date_str:
                            value = data['value']
                            break
                    row.append(value)
                
                sheet.append_row(row)
            
            logger.info(f"Wrote consolidated data to Google Sheet for patient {patient.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error writing consolidated data: {e}")
            return False
