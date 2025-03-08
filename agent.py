import os
import json
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes,
)
from database import Database
from gcalendar import GoogleCalendar
from gmail import GmailService
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

# Configurazione logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)

class MaskingFormatter(logging.Formatter):
    """Maschera il token Telegram nei log."""
    def __init__(self, fmt=None, datefmt=None, style='%'):
        super().__init__(fmt, datefmt, style)
        self.token = os.getenv('TELEGRAM_TOKEN')
        
    def format(self, record):
        formatted = super().format(record)
        if self.token and self.token in formatted:
            return formatted.replace(self.token, "[TOKEN NASCOSTO]")
        return formatted

handler = logging.StreamHandler()
handler.setFormatter(MaskingFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logging.root.handlers = [handler]

logger = logging.getLogger(__name__)

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')

class HealthServer:
    def __init__(self, port=10000):
        self.port = port
        self.server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        self.thread = Thread(target=self.server.serve_forever)

    def start(self):
        self.thread.start()
        logger.info(f"Health check server avviato su porta {self.port}")

    def stop(self):
        self.server.shutdown()
        self.thread.join()
        logger.info("Health check server fermato")

class CalendarAgent:
    def __init__(self):
        self.db = Database()
        self.calendar = GoogleCalendar()
        self.gmail = GmailService()
        self.health_server = HealthServer() if os.getenv('ENV') == 'prod' else None
        self.llm_chain = self._init_llm_chain()
    
    def _init_llm_chain(self):
        try:
            llm = ChatGoogleGenerativeAI(
                model="gemini-1.5-pro-002",
                google_api_key=os.getenv("GOOGLE_API_KEY"),
                temperature=0.7
            )
            
            template = self._create_prompt()
            prompt = PromptTemplate(
                template=template,
                input_variables=["user_input", "current_year"],
                template_format="f-string"
            )
            
            # Create a pipeline using the new style
            return prompt | llm
        except Exception as e:
            logging.error(f"Error initializing LLM chain: {str(e)}")
            raise RuntimeError(f"Failed to initialize LLM: {str(e)}. Check your API key and model access.")

    def _create_prompt(self):
        """Crea il prompt per l'LLM."""
        return """
        Analizza il comando utente e genera un JSON strutturato.
        Considera questi sinonimi:
        - Creazione: aggiungi, crea, nuovo, inserisci, programma
        - Eliminazione: cancella, elimina, rimuovi, annulla
        - Modifica: modifica, cambia, aggiorna, sposta, riprogramma, rinvia
        - Lista: mostra, elenca, lista, visualizza, vedi, dammi, quali
        
        Linee guida critiche:
        1. Il campo 'summary' DEVE contenere SOLO il titolo base dell'evento
        2. Rimuovi ASSOLUTAMENTE riferimenti temporali dal 'summary' (es. "delle 15", "del 12 marzo")
        3. Per 'modify'/'delete' senza event_id:
           - 'date' e 'time' devono sempre riflettere la data/ora ORIGINALE
           - Usa il formato ISO8601 per tutti i campi temporali
        4. Per le azioni di modifica, includi SEMPRE sia i nuovi orari (start/end) che quelli originali (date/time)

        Struttura JSON:
        {{
            "action": "add|delete|modify|list",
            "summary": "stringa",             // SOLO titolo, senza date/orari
            "start": "YYYY-MM-DDTHH:MM:SS",   // Obbligatorio per add/modify (NUOVO orario)
            "end": "YYYY-MM-DDTHH:MM:SS",     // Obbligatorio per add/modify (NUOVO orario)
            "event_id": "stringa",            // Obbligatorio solo se specificato
            "date": "YYYY-MM-DD",             // Obbligatorio per delete/modify senza event_id (DATA ORIGINALE)
            "time": "HH:MM"                   // Obbligatorio per delete/modify senza event_id (ORA ORIGINALE)
        }}
        
        Istruzioni:
        1. Per le date relative (es. "domani", "lunedì prossimo") usa la data assoluta
        2. Per gli orari: "alle 15" -> 15:00:00, "16:30" -> 16:30:00
        3. Se mancano informazioni critiche, deducile dal contesto
        4. IMPORTANTE: Se non vieve specificato l'anno usa sempre l'anno corrente ({current_year}) per tutte le date
        5. Per l'azione "list", il campo "summary" è opzionale e può essere usato come filtro

        "ATTENZIONE: Il 'summary' DEVE corrispondere ESATTAMENTE al titolo esistente nell'agenda"

        Istruzioni chiave:
        1. Per comandi tipo "sposta X da Y a Z":
           - 'summary' = X (senza riferimenti a Y/Z)
           - 'date'/'time' = Y (orario originale)
           - 'start'/'end' = Z (nuovo orario)
        2. Per date relative ("domani", "lunedì prossimo"):
           - Converti in data assoluta usando l'anno corrente
        3. Per orari:
           - "alle 15" → 15:00, "16 e 30" → 16:30
        4. Se mancano dettagli critici, deducili dal contesto
        
        Esempi corretti:
        - Input: "Inserisci una riunione con il team domani pomeriggio alle 14 per 2 ore"
          Output: {{
            "action": "add",
            "summary": "riunione con il team",
            "start": "{current_year}-05-30T14:00:00",
            "end": "{current_year}-05-30T16:00:00"
          }}
        - Input: "Elimina l'appuntamento del 5 giugno alle 9:30"
          Output: {{
            "action": "delete", 
            "summary": "appuntamento", # <-- Solo il titolo, nessun riferimento temporale
            "date": "{current_year}-06-05",
            "time": "09:30"
          }}
        - Input: "Sposta la call di marketing da oggi alle 11 a domani alle 15"
          Output: {{
            "action": "modify",
            "event_id": "", 
            "summary": "call di marketing", # <-- Solo il titolo, nessun riferimento temporale
            "start": "{current_year}-05-30T15:00:00",
            "end": "{current_year}-05-30T16:00:00"
          }}
        - Input: "Rinvia la riunione di oggi alle 14 a dopodomani alle 16"
          Output: {{
            "action": "modify",
            "summary": "riunione",
            "date": "{current_year}-03-08",    // Data originale (oggi)
            "time": "14:00",                   // Ora originale
            "start": "{current_year}-03-10T16:00:00", // Nuovo orario
            "end": "{current_year}-03-10T17:00:00"
        }}  
        - Input: "Mostrami tutti gli eventi"
          Output: {{
            "action": "list"
          }}
        - Input: "Quali appuntamenti ho giovedì?"
          Output: {{
            "action": "list",
            "date": "{current_year}-05-30"
          }}
        - Input: "Elenca le riunioni di questa settimana"
          Output: {{
            "action": "list",
            "summary": "riunioni"
          }}          
        
        Input corrente: {user_input}
        """

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_input = update.message.text
        try:
            action_data = self.parse_command(user_input)
            response = await self._execute_action(update, action_data)
            if response is not None:  # Invia risposta solo se ce n'è una
                await update.message.reply_text(response)
        
        except Exception as e:
            logger.error(f"Errore: {str(e)}", exc_info=True)
            await update.message.reply_text("❌ Errore durante l'operazione.")

    def parse_command(self, user_input: str) -> dict:
        try:
            # Get current year
            current_year = datetime.now().year
            
            # Using the new pipeline style with current_year
            response = self.llm_chain.invoke({
                "user_input": user_input,
                "current_year": current_year
            })
            
            # In the new style, response might be formatted differently
            if hasattr(response, 'content'):
                # If using ChatGoogleGenerativeAI
                response_text = response.content
            else:
                # Fallback for other response formats
                response_text = str(response)
                
            cleaned = response_text.strip().replace('```json', '').replace('```', '').replace("'", '"')
            
            logger.info(f"Raw LLM response: {response}")
            logger.info(f"Cleaned response: {cleaned}")
            
            data = json.loads(cleaned)
            
            # Validazione campi obbligatori
            if 'action' not in data:
                raise ValueError("Campo 'action' mancante")
                
            return data
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON non valido: {cleaned}, errore: {str(e)}")
            raise ValueError("Formato risposta non riconosciuto")
        except Exception as e:
            logger.error(f"Errore parsing: {str(e)}")
            raise

    async def _execute_action(self, update: Update, action_data: dict) -> str:
        action = action_data.get("action")
        
        try:
            if action == "add":
                return await self._add_event(update, action_data)
            elif action == "delete":
                result = await self._confirm_delete(update, action_data)
                return result if result is not None else None  # Gestisce il caso in cui _confirm_delete non restituisce nulla
            elif action == "modify":
                return await self._modify_event(update, action_data)
            elif action == "list":
                return await self._list_events()
            else:
                return "❌ Azione non supportata."
        except Exception as e:
            await self.gmail.send_email(
                to="g.canale@escom.it",  # Indirizzo fisso per la demo
                subject="Errore operazione",
                body=f"Errore durante {action}: {str(e)}"
            )
            raise

    async def _add_event(self, update: Update, action_data: dict) -> str:
        # Add debug log here
        logging.info(f"Attempting to create calendar event: {action_data}")
        
        event = self.calendar.create_event(
            action_data["summary"],
            action_data["start"],
            action_data["end"]
        )
        
        # Add debug log here
        logging.info(f"Calendar event creation result: {event}")
        
        self.db.upsert_event({
            "event_id": event["id"],
            "summary": action_data["summary"],
            "start_time": action_data["start"],
            "end_time": action_data["end"]
        })
        
        await self.gmail.send_email(
            to="g.canale@escom.it",  # Indirizzo fisso per la demo,
            subject="Nuovo evento creato",
            body=f"Evento creato: {action_data['summary']}\nOra: {action_data['start']}"
        )
        
        return f"✅ Evento creato: {event.get('htmlLink')}"

    async def _modify_event(self, update: Update, action_data: dict) -> str:
        event_id = action_data.get("event_id")
        
        # Log the received event_id for debugging
        logging.info(f"Received event_id for modification: {event_id}")
        
        # Check if we need to search for the event
        if not event_id or event_id == "ID_DA_CERCARE_IN_DB":
            # Search for events by summary
            logging.info(f"Searching for events with summary: {action_data['summary']}")
            events = self.db.get_events_by_summary(action_data["summary"])
            
            if not events:
                return "❌ Nessun evento trovato con questo titolo."
            
            if len(events) > 1:
                # Multiple events found, return list of events
                event_list = "\n".join([f"{e['summary']} ({e['start_time']})" for e in events])
                return f"🔍 Trovati più eventi. Specifica quale vuoi modificare:\n{event_list}"
            
            # Use the first (and only) event found
            event_id = events[0]["event_id"]
            logging.info(f"Found event with ID: {event_id}")
        
        try:
            # Update the event with the real ID
            event = self.calendar.update_event(
                event_id,
                action_data["summary"],
                action_data["start"],
                action_data["end"]
            )
            
            # Update the database
            self.db.upsert_event({
                "event_id": event["id"],
                "summary": action_data["summary"],
                "start_time": action_data["start"],
                "end_time": action_data["end"]
            })
            
            await self.gmail.send_email(
                to="g.canale@escom.it",  # Indirizzo fisso per la demo,
                subject="Evento modificato",
                body=f"Evento modificato: {action_data['summary']}\nNuovo orario: {action_data['start']}"
            )
            
            return f"🔄 Evento modificato: {event.get('htmlLink')}"
    
        except Exception as e:
            logging.error(f"Error modifying event: {str(e)}")
            return f"❌ Errore durante la modifica dell'evento: {str(e)}"

    async def _list_events(self) -> str:
        """Lista tutti gli eventi."""
        events = self.db.get_events()
        if not events:
            return "🗓️ Nessun evento trovato."
        return "\n".join([f"{e['summary']} ({e['start_time']})" for e in events])

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gestisce i click sui bottoni inline."""
        query = update.callback_query
        await query.answer()

        # Verifica prima se inizia con delete_confirm
        if query.data.startswith("delete_confirm:"):
            # Divide solo alla prima e seconda occorrenza di ":"
            parts = query.data.split(":", 2)
            if len(parts) >= 3:
                action = parts[0]
                date = parts[1]
                time = parts[2]
                await self._delete_event(query, date, time)
            else:
                # Gestisci il caso in cui non ci sono abbastanza parti
                await query.edit_message_text("❌ Dati di callback non validi.")
        elif query.data == "delete_cancel":
            await query.edit_message_text("❌ Cancellazione annullata.")
        else:
            await query.edit_message_text("❌ Azione non riconosciuta.")

    async def _confirm_delete(self, update: Update, action_data: dict) -> str:
        """Mostra una conferma prima di eliminare un evento."""
        date = action_data.get("date")
        time = action_data.get("time", "")
        summary = action_data.get("summary", "")
        
        # Log for debugging
        logging.info(f"Confirming deletion for date: {date}, time: {time}, summary: {summary}")
        
        if not date:
            return "❌ Data non specificata per la cancellazione."
        
        # Cerca eventi in quella data
        events = self.db.get_events_by_date(date)
        
        if not events:
            return f"❌ Nessun evento trovato per il {date}."
        
        # Filtra per ora se specificata
        if time:
            filtered_events = []
            for e in events:
                # Handle both string and datetime objects
                if isinstance(e['start_time'], str):
                    event_time = e['start_time'].split('T')[1]
                else:
                    # Format datetime object to string
                    event_time = e['start_time'].strftime('%H:%M:%S')
                
                if event_time.startswith(time):
                    filtered_events.append(e)
                    
            if filtered_events:
                events = filtered_events
        
        # Filtra per titolo se specificato
        if summary:
            filtered_events = [e for e in events if summary.lower() in e['summary'].lower()]
            if filtered_events:
                events = filtered_events
        
        if len(events) == 1:
            event = events[0]
            
            # Get event time in proper format
            if isinstance(event['start_time'], str):
                event_time = event['start_time'].split('T')[1][:5]
            else:
                event_time = event['start_time'].strftime('%H:%M')
                
            keyboard = [
                [
                    InlineKeyboardButton("✅ Conferma", callback_data=f"delete_confirm:{date}:{time}"),
                    InlineKeyboardButton("❌ Annulla", callback_data="delete_cancel")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Invia direttamente il messaggio con i bottoni
            await update.message.reply_text(
                f"🗑️ Vuoi eliminare '{event['summary']}' del {date} alle {event_time}?", 
                reply_markup=reply_markup
            )
            return None  # Non restituiamo nulla perché abbiamo già inviato il messaggio
        else:
            # Multiple events found
            events_text = []
            for e in events[:5]:
                if isinstance(e['start_time'], str):
                    event_time = e['start_time'].split('T')[1][:5]
                else:
                    event_time = e['start_time'].strftime('%H:%M')
                
                events_text.append(f"- {e['summary']} ({event_time})")
                
            events_str = "\n".join(events_text)
            keyboard = [
                [
                    InlineKeyboardButton("✅ Elimina tutti", callback_data=f"delete_confirm:{date}:{time}"),
                    InlineKeyboardButton("❌ Annulla", callback_data="delete_cancel")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
        
            # Invia direttamente il messaggio con i bottoni
            await update.message.reply_text(
                f"🔍 Trovati {len(events)} eventi per il {date}:\n{events_str}", 
                reply_markup=reply_markup
            )
            return None  # Non restituiamo nulla perché abbiamo già inviato il messaggio

    async def _delete_event(self, query, date: str, time: str) -> str:
        """Elimina un evento."""
        events = self.db.get_events_by_date(date)
        
        target_events = []
        for e in events:
            # Gestisci sia oggetti datetime che stringhe
            if isinstance(e['start_time'], str):
                event_time = e['start_time'].split('T')[1]
            else:
                # Converti datetime in stringa nel formato appropriato
                event_time = e['start_time'].strftime('%H:%M:%S')
                
            if event_time.startswith(time):
                target_events.append(e)
        
        if not target_events:
            await query.edit_message_text("❌ Nessun evento trovato.")
            return
        
        deleted_events = []
        for event in target_events:
            self.calendar.delete_event(event['event_id'])
            self.db.delete_event(event['event_id'])
            deleted_events.append(event)
        
        # Aggiungi qui l'invio email per la cancellazione
        try:
            # Per ogni evento cancellato, invia una notifica via email
            for event in deleted_events:
                # Converti start_time in stringa se è un datetime
                start_time_str = event['start_time']
                if not isinstance(start_time_str, str):
                    start_time_str = event['start_time'].strftime('%Y-%m-%dT%H:%M:%S')
                    
                await self.gmail.send_email(
                    to="g.canale@escom.it",  # Indirizzo fisso per la demo
                    subject="Evento cancellato",
                    body=f"È stato cancellato l'evento: {event['summary']}\nData/ora: {start_time_str}"
                )
            logger.info(f"Inviate {len(deleted_events)} email di notifica per cancellazione eventi")
        except Exception as e:
            logger.error(f"❌ Errore invio email per cancellazione: {str(e)}")
    
        await query.edit_message_text(f"🗑️ Eliminati {len(target_events)} eventi.")

    def run(self):
        """Avvia il bot."""
        if self.health_server:
            self.health_server.start()
        
        app = Application.builder().token(os.getenv('TELEGRAM_TOKEN')).build()
        app.add_handler(CommandHandler("start", self.handle_message))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        app.add_handler(CallbackQueryHandler(self.button_callback))
        app.run_polling()

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    bot = CalendarAgent()
    try:
        bot.run()
    finally:
        if bot.health_server:
            bot.health_server.stop()