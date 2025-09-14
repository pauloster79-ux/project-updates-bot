# db_init.py
import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data.db")
engine = create_engine(DATABASE_URL, future=True)

def main():
    with engine.begin() as conn:
        # users table
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS users (
            id              SERIAL PRIMARY KEY,
            slack_user_id   TEXT UNIQUE NOT NULL,
            display_name    TEXT NOT NULL,
            email           TEXT,
            timezone        TEXT DEFAULT 'Europe/London',
            cadence_days    INTEGER DEFAULT 7,
            preferred_hour  INTEGER,
            preferred_dow   INTEGER,
            last_prompt_at  TIMESTAMP,
            next_due_at     TIMESTAMP,
            is_active       BOOLEAN DEFAULT TRUE,
            project         TEXT,
            escalate_to     TEXT
        );
        """))

        # Postgres-safe column adds (no-op if they exist)
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'Europe/London';"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS cadence_days INTEGER DEFAULT 7;"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_hour INTEGER;"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_dow INTEGER;"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_prompt_at TIMESTAMP;"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS next_due_at TIMESTAMP;"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS project TEXT;"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS escalate_to TEXT;"))

        # updates table
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS updates (
            id             SERIAL PRIMARY KEY,
            user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            prompted_at    TIMESTAMP,
            responded_at   TIMESTAMP,
            progress_pct   INTEGER,
            summary        TEXT,
            blockers       TEXT,
            eta_date       DATE,
            rag            TEXT,
            raw_payload    JSONB,
            raw_text       TEXT,
            source         TEXT
        );
        """))

    print("✅ Tables ensured")

if __name__ == "__main__":
    main()
