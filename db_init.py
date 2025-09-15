import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data.db")
engine = create_engine(DATABASE_URL, future=True)

def main():
    with engine.begin() as conn:
        # --- USERS table ---
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS users (
            id              SERIAL PRIMARY KEY,
            slack_user_id   TEXT NOT NULL,
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

        # Ensure columns exist (safe no-ops on Postgres)
        if engine.url.get_backend_name().startswith("postgres"):
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'Europe/London';"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS cadence_days INTEGER DEFAULT 7;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_hour INTEGER;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_dow INTEGER;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_prompt_at TIMESTAMP;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS next_due_at TIMESTAMP;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS project TEXT;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS escalate_to TEXT;"))

            # >>> CRITICAL: make slack_user_id unique so UPSERT works
            # Use a unique INDEX (works with ON CONFLICT too)
            conn.execute(text("""
                DO $$
                BEGIN
                  IF NOT EXISTS (
                    SELECT 1 FROM pg_indexes
                     WHERE schemaname = 'public'
                       AND indexname  = 'users_slack_user_id_uniq_idx'
                  ) THEN
                    CREATE UNIQUE INDEX users_slack_user_id_uniq_idx
                      ON users (slack_user_id);
                  END IF;
                END
                $$;
            """))
        else:
            # SQLite fallback: add UNIQUE constraint if table newly created (no IF NOT EXISTS for ALTER here)
            pass

        # --- UPDATES table ---
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
            raw_payload    JSON,
            raw_text       TEXT,
            source         TEXT
        );
        """))

    print("✅ Tables & indexes ensured")

if __name__ == "__main__":
    main()
