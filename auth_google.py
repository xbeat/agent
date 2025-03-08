from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os
import json

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.send'
]

def authenticate_google():
    creds = None
    if os.path.exists('credentials/credentials.json'):
        with open('credentials/credentials.json', 'r') as token:
            creds = json.load(token)
    
    if not creds or not creds.get('token'):
        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials/client_secrets.json',
            scopes=SCOPES
        )
        creds = flow.run_local_server(port=0)
        with open('credentials/credentials.json', 'w') as token:
            json.dump(creds.to_json(), token)
    
    return creds

if __name__ == '__main__':
    authenticate_google()