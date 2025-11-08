from sqlalchemy import create_engine, text
import os

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

def init_db():
    with engine.begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS users(
          user_id TEXT PRIMARY KEY,
          email TEXT UNIQUE NOT NULL,
          full_name TEXT,
          plex_username TEXT,
          status TEXT,
          join_date TIMESTAMP,
          last_paid_date TIMESTAMP,
          next_due_date TIMESTAMP,
          plan TEXT,
          monthly_price NUMERIC,
          credits_balance NUMERIC DEFAULT 0,
          plex_invite_status TEXT,
          plex_account_id TEXT,
          notes TEXT
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS payments(
          payment_id TEXT PRIMARY KEY,
          user_id TEXT,
          email TEXT,
          amount NUMERIC,
          currency TEXT,
          provider TEXT,
          provider_event_id TEXT UNIQUE,
          paid_at TIMESTAMP,
          period_start DATE,
          period_end DATE,
          status TEXT,
          idempotency_key TEXT UNIQUE,
          raw_payload JSONB
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS invites(
          invite_id TEXT PRIMARY KEY,
          user_id TEXT,
          email TEXT,
          plex_server TEXT,
          sent_at TIMESTAMP,
          accepted_at TIMESTAMP,
          status TEXT,
          error_message TEXT,
          attempts INT DEFAULT 0
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS referrals(
          id SERIAL PRIMARY KEY,
          referrer_email TEXT,
          referrer_user_id TEXT,
          code TEXT,
          referred_email TEXT,
          credited_amount NUMERIC,
          credit_status TEXT,
          credited_at TIMESTAMP,
          note TEXT
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS audit_log(
          id SERIAL PRIMARY KEY,
          ts TIMESTAMP DEFAULT NOW(),
          event TEXT,
          user_id TEXT,
          email TEXT,
          details TEXT
        );
        """))
