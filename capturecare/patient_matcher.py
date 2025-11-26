import requests
from datetime import datetime
import logging
import base64

logger = logging.getLogger(__name__)

class ClinikoIntegration:
    def __init__(self, api_key, shard='au1'):
        self.api_key = api_key
        self.shard = shard
        self.base_url = f'https://api.{shard}.cliniko.com/v1'
        
        auth_string = f'{api_key}:'
        encoded_auth = base64.b64encode(auth_string.encode()).decode()
        
        self.headers = {
            'Authorization': f'Basic {encoded_auth}',
            'User-Agent': 'CaptureCare Health System',
            'Accept': 'application/json'
        }
    
    def search_patient(self, email=None, first_name=None, last_name=None):
        try:
            params = {}
            if email:
                params['q'] = email
            elif first_name and last_name:
                params['q'] = f'{first_name} {last_name}'
            
            response = requests.get(
                f'{self.base_url}/patients',
                headers=self.headers,
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                patients = data.get('patients', [])
                return patients
            else:
                logger.error(f"Cliniko search error: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Error searching Cliniko patient: {e}")
            return []
    
    def get_patient(self, patient_id):
        try:
            response = requests.get(
                f'{self.base_url}/patients/{patient_id}',
                headers=self.headers
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Cliniko get patient error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting Cliniko patient: {e}")
            return None
    
    def create_treatment_note(self, patient_id, content, practitioner_id=None):
        try:
            data = {
                'patient_id': patient_id,
                'content': content,
                'draft': False
            }
            
            if practitioner_id:
                data['practitioner_id'] = practitioner_id
            
            response = requests.post(
                f'{self.base_url}/treatment_notes',
                headers=self.headers,
                json=data
            )
            
            if response.status_code in [200, 201]:
                return response.json()
            else:
                logger.error(f"Cliniko create note error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating Cliniko treatment note: {e}")
            return None
    
    def get_treatment_notes(self, patient_id):
        try:
            response = requests.get(
                f'{self.base_url}/patients/{patient_id}/treatment_notes',
                headers=self.headers
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('treatment_notes', [])
            else:
                logger.error(f"Cliniko get notes error: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Error getting Cliniko treatment notes: {e}")
            return []
    
    def get_all_patients(self, per_page=100):
        all_patients = []
        page = 1
        
        try:
            while True:
                response = requests.get(
                    f'{self.base_url}/patients',
                    headers=self.headers,
                    params={'per_page': per_page, 'page': page}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    patients = data.get('patients', [])
                    
                    if not patients:
                        break
                    
                    all_patients.extend(patients)
                    
                    total_entries = data.get('total_entries', 0)
                    if len(all_patients) >= total_entries:
                        break
                    
                    page += 1
                else:
                    logger.error(f"Cliniko get all patients error: {response.status_code} - {response.text}")
                    break
                    
        except Exception as e:
            logger.error(f"Error getting all Cliniko patients: {e}")
        
        return all_patients
    
    def match_patient(self, capturecare_patient):
        cliniko_patients = self.search_patient(
            email=capturecare_patient.email,
            first_name=capturecare_patient.first_name,
            last_name=capturecare_patient.last_name
        )
        
        if cliniko_patients:
            best_match = None
            for cp in cliniko_patients:
                if cp.get('email', '').lower() == capturecare_patient.email.lower():
                    best_match = cp
                    break
                elif (cp.get('first_name', '').lower() == capturecare_patient.first_name.lower() and
                      cp.get('last_name', '').lower() == capturecare_patient.last_name.lower()):
                    best_match = cp
            
            if best_match:
                return best_match.get('id')
        
        return None
