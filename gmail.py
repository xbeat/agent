from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from email.mime.text import MIMEText
import base64
import json
import os
import logging

logging.basicConfig(level=logging.INFO)

def get_credentials_path():
    """Restituisce il percorso corretto per le credenziali."""
    if os.getenv('ENV') == 'prod':
        # Modalità produzione: usa il percorso di Render
        return '/etc/secrets/credentials.json'
    else:
        # Modalità sviluppo: usa il percorso locale
        return 'credentials/credentials.json'

class GmailService:
    def __init__(self):
        self.service = self._authenticate()
    
    def _authenticate(self):
        """Autentica l'utente con Google OAuth."""
        creds_path = get_credentials_path()
        try:
            with open(creds_path, 'r') as token:
                creds_info = json.load(token)
            creds = Credentials.from_authorized_user_info(creds_info, scopes=['https://www.googleapis.com/auth/gmail.send'])
            
            if not creds.valid:
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    raise Exception("Credenziali non valide")
            
            return build('gmail', 'v1', credentials=creds)
        except Exception as e:
            logging.error(f"Errore autenticazione Gmail: {str(e)}")
            raise
    
    async def send_email(self, to: str, subject: str, body: str) -> None:
        """Invia un'email tramite Gmail API."""
        try:
            message = MIMEText(body)
            message['to'] = to
            message['from'] = 'kaolay@gmail.com'
            message['subject'] = subject
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            logging.info(f"Invio email a {to}")
            self.service.users().messages().send(
                userId='me',
                body={'raw': raw}
            ).execute()
            logging.info("✅ Email inviata con successo")
        except Exception as e:
            logging.error(f"❌ Errore invio email: {str(e)}")
            # Change this line:
            # raise
            # To this:
            raise Exception(f"Errore invio email: {str(e)}")