from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv
load_dotenv()

engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///data.db"), future=True)

schema = '''
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slack_user_id TEXT NOT NULL,
  display_name TEXT NOT NULL,
  email TEXT,
  timezone TEXT DEFAULT 'Europe/London',
  cadence_days INTEGER DEFAULT 7,
  last_prompt_at TIMESTAMP,
  next_due_at TIMESTAMP,
  is_active BOOLEAN DEFAULT 1
);

CREATE TABLE IF NOT EXISTS updates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  prompted_at TIMESTAMP NOT NULL,
  responded_at TIMESTAMP,
  progress_pct INTEGER,
  summary TEXT,
  blockers TEXT,
  eta_date DATE,
  rag TEXT,
  raw_text TEXT,
  source TEXT DEFAULT 'slack_dm'
);
'''

def main():
    with engine.begin() as conn:
        for stmt in schema.strip().split(";"):
            if stmt.strip():
                conn.execute(text(stmt.strip()))
    print("✅ Tables created")

if __name__ == "__main__":
    main()
