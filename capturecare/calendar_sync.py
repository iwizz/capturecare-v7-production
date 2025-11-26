import os
import logging
import requests
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

class GoogleCalendarSync:
    """Manages Google Calendar integration via Replit connector"""
    
    def __init__(self):
        self.connector_hostname = os.getenv('REPLIT_CONNECTORS_HOSTNAME')
        self.repl_identity = os.getenv('REPL_IDENTITY')
        self.web_repl_renewal = os.getenv('WEB_REPL_RENEWAL')
        self.access_token = None
        self.token_expiry = None
        
    def _get_auth_token(self):
        """Get the X-Replit-Token for connector authentication"""
        if self.repl_identity:
            return f'repl {self.repl_identity}'
        elif self.web_repl_renewal:
            return f'depl {self.web_repl_renewal}'
        else:
            raise Exception('X_REPLIT_TOKEN not found for repl/depl')
    
    def _refresh_access_token(self):
        """Fetch fresh access token from Replit connector"""
        if not self.connector_hostname:
            raise Exception('Google Calendar not configured - REPLIT_CONNECTORS_HOSTNAME not found')
        
        try:
            x_replit_token = self._get_auth_token()
            
            url = f'https://{self.connector_hostname}/api/v2/connection?include_secrets=true&connector_names=google-calendar'
            headers = {
                'Accept': 'application/json',
                'X_REPLIT_TOKEN': x_replit_token
            }
            
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            items = data.get('items', [])
            
            if not items or len(items) == 0:
                raise Exception('Google Calendar not connected')
            
            connection_settings = items[0]
            settings = connection_settings.get('settings', {})
            
            self.access_token = settings.get('access_token')
            expires_at_str = settings.get('expires_at')
            
            if expires_at_str:
                self.token_expiry = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
            
            if not self.access_token:
                raise Exception('No access token found in Google Calendar connection')
            
            logger.info("Successfully retrieved Google Calendar access token")
            return self.access_token
            
        except Exception as e:
            logger.error(f"Error refreshing Google Calendar token: {e}")
            raise
    
    def _get_valid_token(self):
        """Get a valid access token, refreshing if necessary"""
        if not self.access_token or (self.token_expiry and datetime.now(timezone.utc) >= self.token_expiry):
            return self._refresh_access_token()
        return self.access_token
    
    def create_event(self, summary, start_time, end_time, description=None, location=None, attendees=None):
        """
        Create a calendar event
        
        Args:
            summary: Event title
            start_time: datetime object for event start
            end_time: datetime object for event end
            description: Optional event description
            location: Optional event location
            attendees: Optional list of email addresses
            
        Returns:
            event_id if successful, None otherwise
        """
        try:
            token = self._get_valid_token()
            
            event_body = {
                'summary': summary,
                'start': {
                    'dateTime': start_time.isoformat(),
                    'timeZone': 'Australia/Sydney'
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': 'Australia/Sydney'
                }
            }
            
            if description:
                event_body['description'] = description
            
            if location:
                event_body['location'] = location
            
            if attendees:
                event_body['attendees'] = [{'email': email} for email in attendees]
            
            url = 'https://www.googleapis.com/calendar/v3/calendars/primary/events'
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.post(url, json=event_body, headers=headers)
            response.raise_for_status()
            
            event_data = response.json()
            event_id = event_data.get('id')
            
            logger.info(f"Successfully created Google Calendar event: {event_id}")
            return event_id
            
        except Exception as e:
            logger.error(f"Error creating Google Calendar event: {e}")
            return None
    
    def update_event(self, event_id, summary=None, start_time=None, end_time=None, description=None, location=None):
        """
        Update an existing calendar event
        
        Args:
            event_id: Google Calendar event ID
            summary: New event title (optional)
            start_time: New start datetime (optional)
            end_time: New end datetime (optional)
            description: New description (optional)
            location: New location (optional)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            token = self._get_valid_token()
            
            url = f'https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}'
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            
            event_body = {}
            
            if summary:
                event_body['summary'] = summary
            
            if start_time:
                event_body['start'] = {
                    'dateTime': start_time.isoformat(),
                    'timeZone': 'Australia/Sydney'
                }
            
            if end_time:
                event_body['end'] = {
                    'dateTime': end_time.isoformat(),
                    'timeZone': 'Australia/Sydney'
                }
            
            if description is not None:
                event_body['description'] = description
            
            if location is not None:
                event_body['location'] = location
            
            response = requests.patch(url, json=event_body, headers=headers)
            response.raise_for_status()
            
            logger.info(f"Successfully updated Google Calendar event: {event_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating Google Calendar event: {e}")
            return False
    
    def delete_event(self, event_id):
        """
        Delete a calendar event
        
        Args:
            event_id: Google Calendar event ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            token = self._get_valid_token()
            
            url = f'https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}'
            headers = {
                'Authorization': f'Bearer {token}'
            }
            
            response = requests.delete(url, headers=headers)
            response.raise_for_status()
            
            logger.info(f"Successfully deleted Google Calendar event: {event_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting Google Calendar event: {e}")
            return False
    
    def get_calendar_info(self):
        """
        Get information about the connected calendar
        
        Returns:
            dict with calendar info (email, name) or None if error
        """
        try:
            token = self._get_valid_token()
            
            # Get calendar info
            url = 'https://www.googleapis.com/calendar/v3/calendars/primary'
            headers = {
                'Authorization': f'Bearer {token}'
            }
            
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            
            return {
                'email': data.get('id'),
                'summary': data.get('summary', 'Primary Calendar'),
                'timezone': data.get('timeZone', 'Australia/Sydney')
            }
            
        except Exception as e:
            logger.error(f"Error getting calendar info: {e}")
            return None
    
    def list_upcoming_events(self, max_results=10, days_ahead=30):
        """
        List upcoming calendar events
        
        Args:
            max_results: Maximum number of events to return
            days_ahead: Number of days ahead to search
            
        Returns:
            List of event dictionaries
        """
        try:
            token = self._get_valid_token()
            
            time_min = datetime.utcnow().isoformat() + 'Z'
            time_max = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + 'Z'
            
            url = f'https://www.googleapis.com/calendar/v3/calendars/primary/events'
            params = {
                'timeMin': time_min,
                'timeMax': time_max,
                'maxResults': max_results,
                'singleEvents': True,
                'orderBy': 'startTime'
            }
            headers = {
                'Authorization': f'Bearer {token}'
            }
            
            response = requests.get(url, params=params, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            events = data.get('items', [])
            
            logger.info(f"Successfully retrieved {len(events)} upcoming events")
            return events
            
        except Exception as e:
            logger.error(f"Error listing Google Calendar events: {e}")
            return []
