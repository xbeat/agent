from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import os
import json
import logging

logging.basicConfig(level=logging.INFO)

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.send'
]

def get_credentials_path():
    """Restituisce il percorso corretto per le credenziali."""
    if os.getenv('ENV') == 'prod':
        # Modalità produzione: usa il percorso di Render
        return '/etc/secrets/credentials.json'
    else:
        # Modalità sviluppo: usa il percorso locale
        return 'credentials/credentials.json'

def authenticate_google():
    """Autentica l'utente con Google OAuth."""
    creds = None
    creds_path = get_credentials_path()
    
    # Se esiste già un file di token, caricalo
    if os.path.exists(creds_path):
        with open(creds_path, 'r') as token:
            creds = Credentials.from_authorized_user_info(json.load(token), SCOPES)
    
    # Se non ci sono credenziali valide, esegui il flusso OAuth
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials/client_secrets.json',  # File scaricato da Google Cloud
                scopes=SCOPES
            )
            creds = flow.run_local_server(port=0)
        
        # Salva le credenziali per il prossimo avvio
        with open(creds_path, 'w') as token:
            token.write(creds.to_json())
    
    return creds

if __name__ == "__main__":
    authenticate_google()