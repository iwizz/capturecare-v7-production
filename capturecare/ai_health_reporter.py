from openai import OpenAI
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class AIHealthReporter:
    def __init__(self, api_key, use_xai=False, xai_api_key=None):
        self.api_key = api_key
        self.use_xai = use_xai
        self.xai_api_key = xai_api_key
        
        if use_xai and xai_api_key:
            # Use xAI (Grok) API
            self.client = OpenAI(
                api_key=xai_api_key,
                base_url="https://api.x.ai/v1"
            ) if xai_api_key else None
            self.model = "grok-3"  # Latest Grok model (grok-beta was deprecated on 2025-09-15)
        else:
            # Use OpenAI
            self.client = OpenAI(api_key=api_key) if api_key else None
            self.model = "gpt-4"
    
    def generate_health_report(self, patient, health_data_summary):
        """Generate patient-friendly health report (default/backward compatible)"""
        return self.generate_patient_report(patient, health_data_summary)
    
    def generate_patient_report(self, patient, health_data_summary):
        """Generate patient-friendly health report for email"""
        if not self.client:
            api_name = "xAI (Grok)" if self.use_xai else "OpenAI"
            return f"{api_name} API key not configured. Cannot generate AI health report."
        
        try:
            prompt = self._build_patient_report_prompt(patient, health_data_summary)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a friendly health coach providing personalized health insights. Use warm, encouraging language that motivates patients while being clear and actionable. Avoid medical jargon and explain everything in simple terms."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1500
            )
            
            report = response.choices[0].message.content
            return report
            
        except Exception as e:
            logger.error(f"Error generating patient health report: {e}")
            return f"Error generating health report: {str(e)}"
    
    def generate_clinical_note(self, patient, health_data_summary):
        """Generate technical clinical note for Cliniko"""
        if not self.client:
            api_name = "xAI (Grok)" if self.use_xai else "OpenAI"
            return f"{api_name} API key not configured. Cannot generate clinical note."
        
        try:
            prompt = self._build_clinical_note_prompt(patient, health_data_summary)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a clinical health data analyst writing professional treatment notes for healthcare providers. Use medical terminology, be precise with measurements, include relevant clinical observations, and follow standard SOAP note format where applicable."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=1200
            )
            
            note = response.choices[0].message.content
            return note
            
        except Exception as e:
            logger.error(f"Error generating clinical note: {e}")
            return f"Error generating clinical note: {str(e)}"
    
    def generate_video_script(self, patient, health_data_summary):
        """Generate short conversational script for video avatar (60-90 seconds)"""
        if not self.client:
            api_name = "xAI (Grok)" if self.use_xai else "OpenAI"
            return f"{api_name} API key not configured. Cannot generate video script."
        
        try:
            prompt = self._build_video_script_prompt(patient, health_data_summary)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are writing a friendly, conversational script for a video avatar health coach. The script should be 60-90 seconds when read aloud (150-220 words). Use natural speech patterns, contractions, and a warm conversational tone. Address the patient directly using 'you'. Keep it concise, positive, and actionable."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=400
            )
            
            script = response.choices[0].message.content
            return script
            
        except Exception as e:
            logger.error(f"Error generating video script: {e}")
            return f"Error generating video script: {str(e)}"
    
    def _build_health_analysis_prompt(self, patient, health_data_summary):
        """Legacy prompt - redirects to patient report prompt"""
        return self._build_patient_report_prompt(patient, health_data_summary)
    
    def _build_patient_report_prompt(self, patient, health_data_summary):
        """Build prompt for patient-friendly health report"""
        age = self._calculate_age(patient.date_of_birth) if patient.date_of_birth else 'Unknown'
        
        prompt = f"""
Generate a friendly, encouraging health report for this patient:

Patient Information:
- Name: {patient.first_name} {patient.last_name}
- Age: {age}

Recent Health Data:
{self._format_health_data(health_data_summary)}

Create a warm, motivating health report that:
1. **Celebrates Wins**: Start with positive observations and improvements
2. **Key Insights**: Explain what the data means in simple, everyday language
3. **Health Goals**: Compare to healthy ranges for their age (no medical jargon)
4. **Action Steps**: Provide 3-5 specific, easy-to-follow recommendations
5. **Encouragement**: End with motivating words about their health journey

Use a friendly, conversational tone. Avoid medical terminology. Make it feel personal and supportive.
"""
        return prompt
    
    def _build_clinical_note_prompt(self, patient, health_data_summary):
        """Build prompt for clinical treatment note"""
        age = self._calculate_age(patient.date_of_birth) if patient.date_of_birth else 'Unknown'
        
        prompt = f"""
Generate a professional clinical note for healthcare provider review:

Patient: {patient.first_name} {patient.last_name}
Age: {age}
Date: {datetime.now().strftime('%Y-%m-%d')}

Objective Health Data:
{self._format_health_data(health_data_summary)}

Create a clinical treatment note following SOAP format:

**SUBJECTIVE:**
- Patient health data monitoring via connected devices

**OBJECTIVE:**
- Vital signs and biometric measurements
- Trends analysis over monitoring period
- Notable changes or deviations from baseline

**ASSESSMENT:**
- Clinical interpretation of metrics
- Comparison to age-appropriate reference ranges
- Risk factors identified
- Positive health indicators

**PLAN:**
- Clinical recommendations
- Suggested interventions or lifestyle modifications
- Follow-up monitoring parameters

Use medical terminology. Be precise with measurements. Include clinical significance.
"""
        return prompt
    
    def _build_video_script_prompt(self, patient, health_data_summary):
        """Build prompt for video avatar script (60-90 seconds)"""
        age = self._calculate_age(patient.date_of_birth) if patient.date_of_birth else 'Unknown'
        first_name = patient.first_name
        
        prompt = f"""
Write a 60-90 second conversational video script for a health coach avatar talking to {first_name} (age {age}).

Their Recent Health Data:
{self._format_health_data(health_data_summary)}

Create a friendly video script (150-220 words) that:
- Opens with a warm greeting using their first name
- Highlights 1-2 key health wins or insights
- Gives 2-3 quick, actionable tips
- Ends with encouragement

Script Guidelines:
✓ Use "you" and "your" - speak directly to {first_name}
✓ Use contractions (you're, we'll, let's)
✓ Sound natural and conversational
✓ Keep sentences short and punchy
✓ Stay positive and upbeat
✓ Make it feel like a real conversation
✗ Don't use medical jargon
✗ Don't write stage directions or [pauses]
✗ Don't exceed 220 words

Write ONLY the script text - what the avatar will say.
"""
        return prompt
    
    def _format_health_data(self, health_data_summary):
        formatted = []
        
        for metric_type, data_points in health_data_summary.items():
            if data_points:
                latest = data_points[-1]
                formatted.append(f"- {metric_type.replace('_', ' ').title()}: {latest['value']} {latest.get('unit', '')} (on {latest['timestamp'].strftime('%Y-%m-%d')})")
                
                if len(data_points) > 1:
                    oldest = data_points[0]
                    change = latest['value'] - oldest['value']
                    if change != 0:
                        formatted.append(f"  Change: {'+' if change > 0 else ''}{change:.1f} over {len(data_points)} measurements")
        
        return '\n'.join(formatted) if formatted else "No recent health data available"
    
    def _calculate_age(self, date_of_birth):
        if not date_of_birth:
            return None
        today = datetime.today().date()
        dob = date_of_birth if isinstance(date_of_birth, type(today)) else date_of_birth.date()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        return age
    
    def generate_summary_insights(self, patient, health_data_summary):
        if not self.client:
            return {}
        
        try:
            insights = {
                'overall_health_score': self._calculate_health_score(health_data_summary),
                'key_metrics': self._extract_key_metrics(health_data_summary),
                'recommendations_count': 0,
                'areas_of_concern': []
            }
            
            if 'weight' in health_data_summary and health_data_summary['weight']:
                weight_trend = self._analyze_trend(health_data_summary['weight'])
                insights['weight_trend'] = weight_trend
            
            if 'systolic_bp' in health_data_summary and health_data_summary['systolic_bp']:
                bp_status = self._analyze_blood_pressure(health_data_summary)
                insights['blood_pressure_status'] = bp_status
            
            if 'sleep_score' in health_data_summary and health_data_summary['sleep_score']:
                sleep_quality = self._analyze_sleep(health_data_summary['sleep_score'])
                insights['sleep_quality'] = sleep_quality
            
            return insights
            
        except Exception as e:
            logger.error(f"Error generating summary insights: {e}")
            return {}
    
    def _calculate_health_score(self, health_data_summary):
        score = 75
        
        if 'steps' in health_data_summary and health_data_summary['steps']:
            avg_steps = sum(d['value'] for d in health_data_summary['steps']) / len(health_data_summary['steps'])
            if avg_steps >= 10000:
                score += 5
            elif avg_steps < 5000:
                score -= 5
        
        if 'sleep_score' in health_data_summary and health_data_summary['sleep_score']:
            avg_sleep = sum(d['value'] for d in health_data_summary['sleep_score']) / len(health_data_summary['sleep_score'])
            if avg_sleep >= 80:
                score += 5
            elif avg_sleep < 60:
                score -= 5
        
        return max(0, min(100, score))
    
    def _extract_key_metrics(self, health_data_summary):
        key_metrics = {}
        priority_metrics = ['weight', 'systolic_bp', 'diastolic_bp', 'heart_rate', 'steps', 'sleep_score']
        
        for metric in priority_metrics:
            if metric in health_data_summary and health_data_summary[metric]:
                latest = health_data_summary[metric][-1]
                key_metrics[metric] = {
                    'value': latest['value'],
                    'unit': latest.get('unit', ''),
                    'date': latest['timestamp'].strftime('%Y-%m-%d')
                }
        
        return key_metrics
    
    def _analyze_trend(self, data_points):
        if len(data_points) < 2:
            return 'stable'
        
        values = [d['value'] for d in data_points]
        first_half_avg = sum(values[:len(values)//2]) / (len(values)//2)
        second_half_avg = sum(values[len(values)//2:]) / (len(values) - len(values)//2)
        
        change_percent = ((second_half_avg - first_half_avg) / first_half_avg) * 100
        
        if change_percent > 2:
            return 'increasing'
        elif change_percent < -2:
            return 'decreasing'
        else:
            return 'stable'
    
    def _analyze_blood_pressure(self, health_data_summary):
        if 'systolic_bp' not in health_data_summary or not health_data_summary['systolic_bp']:
            return 'unknown'
        
        latest_systolic = health_data_summary['systolic_bp'][-1]['value']
        latest_diastolic = health_data_summary.get('diastolic_bp', [{}])[-1].get('value', 0)
        
        if latest_systolic < 120 and latest_diastolic < 80:
            return 'normal'
        elif latest_systolic < 130 and latest_diastolic < 80:
            return 'elevated'
        elif latest_systolic < 140 or latest_diastolic < 90:
            return 'stage_1_hypertension'
        else:
            return 'stage_2_hypertension'
    
    def _analyze_sleep(self, sleep_data):
        if not sleep_data:
            return 'unknown'
        
        avg_score = sum(d['value'] for d in sleep_data) / len(sleep_data)
        
        if avg_score >= 80:
            return 'excellent'
        elif avg_score >= 70:
            return 'good'
        elif avg_score >= 60:
            return 'fair'
        else:
            return 'poor'
