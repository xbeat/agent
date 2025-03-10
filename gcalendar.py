from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import os
import logging
import json

logging.basicConfig(level=logging.INFO)

def get_credentials_path():
    if os.getenv('ENV') == 'prod':
        return '/etc/secrets/credentials.json'
    else:
        return 'credentials/credentials.json'

class GoogleCalendar:
    def __init__(self):
        self.service = self._authenticate()
    
    def _authenticate(self):
        try:
            with open(get_credentials_path(), 'r') as token:
                creds_info = json.load(token)
            creds = Credentials.from_authorized_user_info(creds_info)
            
            if not creds.valid:
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    raise Exception("Credenziali non valide")
            
            return build('calendar', 'v3', credentials=creds)
        except Exception as e:
            logging.error(f"Errore autenticazione Calendar: {str(e)}")
            raise
    
    def create_event(self, summary: str, start: str, end: str) -> dict:
        event = {
            'summary': summary,
            'start': {'dateTime': start, 'timeZone': 'Europe/Rome'},
            'end': {'dateTime': end, 'timeZone': 'Europe/Rome'}
        }
        return self.service.events().insert(
            calendarId='primary',
            body=event
        ).execute()
    
    def update_event(self, event_id: str, summary: str, start: str, end: str) -> dict:
        event = {
            'summary': summary,
            'start': {'dateTime': start, 'timeZone': 'Europe/Rome'},
            'end': {'dateTime': end, 'timeZone': 'Europe/Rome'}
        }
        return self.service.events().update(
            calendarId='primary',
            eventId=event_id,
            body=event
        ).execute()
    
    def delete_event(self, event_id: str) -> None:
        self.service.events().delete(
            calendarId='primary',
            eventId=event_id
        ).execute()
    
    def list_events(self, max_results=10) -> list:
        return self.service.events().list(
            calendarId='primary',
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute().get('items', [])