import os
import json
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from dotenv import load_dotenv
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain_google_genai import GoogleGenerativeAI
from database import Database
from gcalendar import GoogleCalendar
from gmail import GmailService

# Configurazione iniziale
load_dotenv()
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG,
    handlers=[logging.StreamHandler()]  # Log solo su console, nessun file
)

class CalendarAgent:
    def __init__(self):
        self.llm = GoogleGenerativeAI(
            model="gemini-1.5-pro-latest",
            google_api_key=os.getenv("GOOGLE_API_KEY")
        )
        self.db = Database()
        self.calendar = GoogleCalendar()
        self.gmail = GmailService()
        self.chain = self._create_chain()
    
    def _create_chain(self):
        prompt_template = """
        **Devi restituire SOLO JSON VALIDO senza altri testo.**
        Analizza il comando e genera:

        {{
            "action": "add|delete|list",
            "summary": "testo evento (in minuscolo)",
            "start": "YYYY-MM-DDTHH:MM:SS",  # solo per 'add'
            "end": "YYYY-MM-DDTHH:MM:SS",    # solo per 'add'
            "date": "YYYY-MM-DD"             # solo per 'delete'
        }}

        **Esempi obbligatori:**
        Input: "Aggiungi dentista domani alle 14:30 per 1 ora"
        Output: {{
            "action": "add",
            "summary": "dentista",
            "start": "2024-05-30T14:30:00",
            "end": "2024-05-30T15:30:00"
        }}

        Input: "Elimina evento riunione del 30 maggio"
        Output: {{
            "action": "delete",
            "summary": "riunione",
            "date": "2024-05-30"
            }}

        Input: {user_input}
        """
        
        return LLMChain(
            llm=self.llm,
            prompt=PromptTemplate(
                input_variables=["user_input"],
                template=prompt_template
            )
        )
    
    def parse_command(self, user_input: str) -> dict:
        try:
            response = self.chain.run(user_input=user_input)
            
            # Pulizia aggressiva della risposta
            cleaned = response.strip()
            cleaned = cleaned.replace('```json', '').replace('```', '')
            cleaned = cleaned.replace("'", '"')  # Converti singoli apici in doppi
            
            # Debug: mostra la risposta grezza
            logging.info(f"Risposta LLM: {cleaned}")
            
            return json.loads(cleaned)
            
        except json.JSONDecodeError as e:
            logging.error(f"JSON non valido: {cleaned}")
            raise ValueError("Formato risposta non riconosciuto")
        except Exception as e:
            logging.error(f"Errore parsing: {str(e)}")
            raise
    
    # Nel metodo handle_action, modifica tutte le azioni per inviare email automatiche
    def handle_action(self, action_data: dict) -> str:
        action = action_data.get("action")
        response = ""
        
        try:
            if action == "add":
                # Creazione evento
                event = self.calendar.create_event(
                    action_data["summary"],
                    action_data["start"],
                    action_data["end"]
                )
                # Salva nel DB
                self.db.upsert_event({
                    "event_id": event["id"],
                    "summary": action_data["summary"],
                    "start_time": action_data["start"],
                    "end_time": action_data["end"]
                })
                response = f"✅ Evento creato: {event.get('htmlLink')}"
                
                # Invia email automatica
                self.gmail.send_email(
                    "g.canale@escom.it",  # Sostituisci con la tua email
                    "Nuovo Evento Creato",
                    f"Evento: {action_data['summary']}\nInizio: {action_data['start']}"
                )
            
            elif action == "delete":
                # Cerca evento per data e summary
                events = self.db.get_events_by_date(action_data["date"])
                target_events = [e for e in events if e['summary'] == action_data["summary"]]
                
                if not target_events:
                    return "❌ Nessun evento trovato"
                    
                for event in target_events:
                    self.calendar.delete_event(event['event_id'])
                    self.db.delete_event(event['event_id'])
                
                response = f"🗑️ Eliminati {len(target_events)} eventi"
                
                # Invia email automatica
                self.gmail.send_email(
                    "g.canale@escom.it",
                    "Evento Eliminato",
                    f"Evento: {action_data['summary']}\nData: {action_data['date']}"
                )
            
            elif action == "list":
                events = self.db.get_events()
                response = "\n".join([f"{e['summary']} ({e['start_time']})" for e in events])
        
            return response
        
        except Exception as e:
            logging.error(f"Action Error: {str(e)}")
            return "❌ Errore durante l'operazione"

async def telegram_start(update: Update, context):
    await update.message.reply_text("📅 Ciao! Sono il tuo assistente per il calendario.")

async def telegram_message(update: Update, context):
    agent = CalendarAgent()
    try:
        action_data = agent.parse_command(update.message.text)
        response = agent.handle_action(action_data)
        await update.message.reply_text(response)
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {str(e)}")

def main():
    app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    app.add_handler(CommandHandler("start", telegram_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_message))
    app.run_polling()

if __name__ == "__main__":
    main()