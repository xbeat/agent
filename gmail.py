from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from email.mime.text import MIMEText
import base64
import json
import os
import logging

logging.basicConfig(level=logging.INFO)

class GmailService:
    def __init__(self):
        self.service = self._authenticate()
    
    def _authenticate(self):
        try:
            with open('credentials/credentials.json', 'r') as token:
                creds_info = json.load(token)
            creds = Credentials.from_authorized_user_info(creds_info)
            
            if not creds.valid:
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    raise Exception("Invalid credentials")
            
            return build('gmail', 'v1', credentials=creds)
        except Exception as e:
            logging.error(f"Gmail Auth Error: {str(e)}")
            return None
    
    # Modifica il metodo send_email
    def send_email(self, to: str, subject: str, body: str) -> None:
        try:
            message = MIMEText(body)
            message['to'] = to
            message['from'] = 'kaolay@gmail.com'  # Aggiungi questo
            message['subject'] = subject
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            logging.info(f"Invio email a {to}")
            self.service.users().messages().send(
                userId='me',
                body={'raw': raw}
            ).execute()
            logging.info("Email inviata con successo")
            
        except Exception as e:
            logging.error(f"Errore invio email: {str(e)}")
            return None