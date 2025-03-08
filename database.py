import os
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO)

class Database:
    def __init__(self):
        self.conn = self._connect()
        self._init_db()
    
    def _connect(self):
        try:
            if os.getenv('ENV') == 'prod':
                return psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')
            else:
                return psycopg2.connect(
                    host=os.getenv('DB_HOST'),
                    dbname=os.getenv('DB_NAME'),
                    user=os.getenv('DB_USER'),
                    password=os.getenv('DB_PASSWORD'),
                    cursor_factory=RealDictCursor
                )
        except Exception as e:
            logging.error(f"DB Connection Error: {str(e)}")
            raise
    
    def get_events_by_summary(self, summary: str) -> list:
        try:
            query = "SELECT * FROM agent_events WHERE summary ILIKE %s"
            with self.conn.cursor() as cur:
                cur.execute(query, (f"%{summary}%",))
                return cur.fetchall()
        except Exception as e:
            logging.error(f"DB Error: {str(e)}")
            return []
    
    def get_events_by_date(self, date: str) -> list:
        try:
            query = """
                SELECT * FROM agent_events 
                WHERE DATE(start_time AT TIME ZONE 'Europe/Rome') = %s
            """
            with self.conn.cursor() as cur:
                cur.execute(query, (date,))
                return cur.fetchall()
        except Exception as e:
            logging.error(f"DB Error: {str(e)}")
            return []
        
    def _init_db(self):
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS agent_events (
                    id SERIAL PRIMARY KEY,
                    event_id VARCHAR(255) UNIQUE,
                    summary TEXT NOT NULL,
                    start_time TIMESTAMPTZ,
                    end_time TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            self.conn.commit()
    
    def upsert_event(self, event_data: dict) -> bool:
        try:
            logging.info(f"Tentativo di salvataggio evento: {event_data}")
            query = sql.SQL("""
                INSERT INTO agent_events (event_id, summary, start_time, end_time)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (event_id) DO UPDATE SET
                    summary = EXCLUDED.summary,
                    start_time = EXCLUDED.start_time,
                    end_time = EXCLUDED.end_time
            """)
            with self.conn.cursor() as cur:
                cur.execute(query, (
                    event_data['event_id'],
                    event_data['summary'],
                    event_data['start_time'],
                    event_data['end_time']
                ))
                self.conn.commit()
                logging.info("✅ Evento salvato nel database")
                return True
        except Exception as e:
            logging.error(f"❌ Errore DB: {str(e)}")
            self.conn.rollback()
            return False
    
    def delete_event(self, event_id: str) -> bool:
        try:
            query = "DELETE FROM agent_events WHERE event_id = %s"
            with self.conn.cursor() as cur:
                cur.execute(query, (event_id,))
                self.conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logging.error(f"DB Error: {str(e)}")
            return False
    
    def get_events(self) -> list:
        try:
            query = "SELECT * FROM agent_events ORDER BY start_time"
            with self.conn.cursor() as cur:
                cur.execute(query)
                return cur.fetchall()
        except Exception as e:
            logging.error(f"DB Error: {str(e)}")
            return []

    def get_events_by_date(self, date: str) -> list:
        try:
            query = """
                SELECT * FROM agent_events 
                WHERE DATE(start_time) = %s
            """
            with self.conn.cursor() as cur:
                cur.execute(query, (date,))
                return cur.fetchall()
        except Exception as e:
            logging.error(f"DB Error: {str(e)}")
        return []            