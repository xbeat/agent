CREATE TABLE IF NOT EXISTS agent_events (  
    id SERIAL PRIMARY KEY,  
    event_id VARCHAR(255) UNIQUE,  
    summary TEXT NOT NULL,  
    start_time TIMESTAMP,  
    end_time TIMESTAMP,  
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  
);  