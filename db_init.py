# Portable DB schema for Postgres (Render) and SQLite (local)
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data.db")
engine = create_engine(DATABASE_URL, future=True)


def schema_for(url: str) -> str:
    if url.startswith("postgres"):
        return """
        CREATE TABLE IF NOT EXISTS users (
          id SERIAL PRIMARY KEY,
          slack_user_id TEXT UNIQUE NOT NULL,
          display_name TEXT NOT NULL,
          email TEXT,
          timezone TEXT DEFAULT 'Europe/London',
          cadence_days INTEGER DEFAULT 7,
          last_prompt_at TIMESTAMP,
          next_due_at TIMESTAMP,
          is_active BOOLEAN DEFAULT TRUE
        );

        CREATE TABLE IF NOT EXISTS updates (
          id SERIAL PRIMARY KEY,
          user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
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
        """
    else:
        return """
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          slack_user_id TEXT UNIQUE NOT NULL,
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
        """


def main():
    ddl = schema_for(DATABASE_URL)
    with engine.begin() as conn:
        for stmt in ddl.strip().split(";"):
            if stmt.strip():
                conn.execute(text(stmt.strip()))
    print("✅ Tables ensured")


if __name__ == "__main__":
    main()
