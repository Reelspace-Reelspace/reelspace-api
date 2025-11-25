import os, hmac, hashlib, json, uuid
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy import text

from .db import engine, init_db
from .plex_service import invite_user, debug_connection
from . import sheets




SHARED_WEBHOOK_SECRET = os.getenv("SHARED_WEBHOOK_SECRET", "")
DEFAULT_PLAN_PRICE = float(os.getenv("DEFAULT_PLAN_PRICE", "9.00"))
DEFAULT_PLAN_NAME = os.getenv("DEFAULT_PLAN_NAME", "Standard")

# Public Wave checkout link – safe to expose
WAVE_CHECKOUT_URL = os.getenv(
    "WAVE_CHECKOUT_URL",
    "https://link.waveapps.com/kbsw8p-n6f972"
)


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="ReelSpace Automation API", version="0.1.0")

# CORS – allow your join site(s) to call the API
origins = [
    "https://reelspace.watch",
    "https://www.reelspace.watch",
    "https://reelspace.pages.dev",
    "https://reelspace-api-1.onrender.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)






# Public endpoint your join page can call to fetch checkout info
@app.get("/wave/checkout")
def get_wave_checkout():
    return {
        "checkout_url": WAVE_CHECKOUT_URL,
        "plan_name": DEFAULT_PLAN_NAME,
        "price": DEFAULT_PLAN_PRICE,
        "currency": "USD",
    }

# ----------------------------------------------------
# DEBUG ROUTES – TO TEST GOOGLE SHEETS CONNECTIVITY
# ----------------------------------------------------

# ----------------------------------------------------
# DEBUG ROUTES – TO TEST GOOGLE SHEETS CONNECTIVITY
# ----------------------------------------------------

@app.get("/debug/sheets")
def debug_sheets():
    """List worksheet tabs to confirm Google Sheets connection."""
    sh = sheets.get_sheet()
    worksheets = [ws.title for ws in sh.worksheets()]
    return {"worksheets": worksheets}

@app.get("/debug/plex")
def debug_plex():
    """
    Debug Plex connectivity: shows account info and available servers.
    Does NOT expose your token.
    """
    return debug_connection()
    
@app.post("/debug/add-demo-user")
def add_demo_user():
    """Append a demo row to Google Sheets to verify writing works."""
    sh = sheets.get_sheet()
    ws = sh.worksheet("Users")

    row = [
        "u_demo_api",                   # user_id
        "demo_api@example.com",         # email
        "Demo User From API",           # full_name
        "",                             # plex_username
        "",                             # referral_code_used
        "active",                       # status
        "2025-11-15",                   # join_date
        "2025-11-15",                   # last_paid_date
        "",                             # next_due_date
        "Standard",                     # plan
        9,                              # monthly_price
        0,                              # credits_balance
        "sent",                         # plex_invite_status
        "",                             # plex_account_id
        "Created via API test",         # notes
    ]

    print("Writing DEBUG user to sheet:", ws.title)
    ws.append_row(row, value_input_option="USER_ENTERED")
    return {"status": "row added"}


@app.on_event("startup")
def _startup():
    init_db()

def verify_signature(raw_body: bytes, signature: str):
    if not SHARED_WEBHOOK_SECRET:
        return True
    mac = hmac.new(SHARED_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, signature or "")

def upsert_user(conn, email: str, full_name: str | None):
    uid = f"u_{uuid.uuid4().hex[:10]}"
    conn.execute(text("""
        INSERT INTO users(user_id, email, full_name, status, join_date, plan, monthly_price)
        VALUES(:uid, :email, :full_name, 'active', NOW(), :plan, :price)
        ON CONFLICT (email) DO NOTHING
    """), dict(uid=uid, email=email, full_name=full_name or "", plan=DEFAULT_PLAN_NAME, price=DEFAULT_PLAN_PRICE))
    row = conn.execute(text("SELECT user_id, credits_balance, plex_invite_status FROM users WHERE email=:e"), dict(e=email)).mappings().first()
    return row

# ---------- Signup payload & endpoint (from Wave / checkout) ----------

class SignupFromWave(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str | None = None


@app.post("/signup/from-wave")
async def signup_from_wave(payload: SignupFromWave):
    """
    Create/update a user after successful checkout and add them to Google Sheets.
    """
    # Build full name
    full_name = payload.first_name
    if payload.last_name:
        full_name = f"{payload.first_name} {payload.last_name}"

    # 1) Upsert into database
    with engine.begin() as conn:
        user_row = upsert_user(conn, payload.email, full_name)
        user_id = user_row["user_id"]

    # 2) Send Plex invite using new invite_user helper
    plex_status = "pending"
    try:
        plex_status = invite_user(payload.email, full_name)  # 'sent' | 'already_shared' | 'already_invited'
    except Exception as e:
        plex_status = f"error: {e.__class__.__name__}"

    # 3) Append into Google Sheet (Users tab)
    sh = sheets.get_sheet()
    ws = sh.worksheet("Users")

    today = datetime.utcnow().date().isoformat()

    # Must match Users sheet headers:
    # user_id | email | full_name | plex_username | referral_code_used |
    # status | join_date | last_paid_date | next_due_date | plan |
    # monthly_price | credits_balance | plex_invite_status | plex_account_id | notes
    row = [
        user_id,                     # user_id
        payload.email,               # email
        full_name,                   # full_name
        "",                          # plex_username
        "",                          # referral_code_used
        "active",                    # status
        today,                       # join_date
        today,                       # last_paid_date
        "",                          # next_due_date
        DEFAULT_PLAN_NAME,           # plan
        str(DEFAULT_PLAN_PRICE),     # monthly_price
        "0",                         # credits_balance
        plex_status,                 # plex_invite_status
        "",                          # plex_account_id
        "Created via Wave checkout", # notes
    ]

    print("Writing signup to sheet:", ws.title)
    ws.append_row(row, value_input_option="USER_ENTERED")

    return {
        "status": "ok",
        "user_id": user_id,
        "plex_invite_status": plex_status,
    }
    
@app.post("/webhooks/wave")
async def wave_webhook(request: Request):
    raw = await request.body()
    sig = request.headers.get("X-Signature","")
    if not verify_signature(raw, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")
    payload = await request.json()
    # Expecting a normalized structure from Pipedream/Make:
    # {
    #   "event_type": "payment_succeeded",
    #   "provider_event_id": "...",
    #   "email": "user@example.com",
    #   "full_name": "Full Name",
    #   "amount": 9.00,
    #   "currency": "USD",
    #   "period_start": "2025-11-01",
    #   "period_end": "2025-12-01",
    #   "referral_code": "REF-ABC123" (optional)
    # }
    event_type = payload.get("event_type")
    if event_type != "payment_succeeded":
        return JSONResponse({"ok": True, "ignored": True})
    provider_event_id = payload["provider_event_id"]
    email = payload["email"].lower()
    full_name = payload.get("full_name","")
    amount = float(payload.get("amount", 0))
    currency = payload.get("currency","USD")
    period_start = payload.get("period_start")
    period_end = payload.get("period_end")
    referral_code = payload.get("referral_code")
    idempotency_key = f"{email}-{period_start}"
    with engine.begin() as conn:
        # Upsert user
        u = upsert_user(conn, email, full_name)
        user_id = u["user_id"]
        # Insert payment if not exists (idempotent)
        conn.execute(text("""
            INSERT INTO payments(payment_id, user_id, email, amount, currency, provider, provider_event_id,
                                 paid_at, period_start, period_end, status, idempotency_key, raw_payload)
            VALUES(:pid, :uid, :email, :amount, :currency, 'Wave', :peid, NOW(),
                   :ps, :pe, 'succeeded', :ikey, CAST(:raw AS JSONB))
            ON CONFLICT (provider_event_id) DO NOTHING
        """), dict(pid=f"p_{uuid.uuid4().hex[:10]}", uid=user_id, email=email, amount=amount, currency=currency,
                     peid=provider_event_id, ps=period_start, pe=period_end, ikey=idempotency_key, raw=json.dumps(payload)))
        # Update user paid dates
        conn.execute(text("""
            UPDATE users SET last_paid_date = NOW(), next_due_date = (NOW() + INTERVAL '30 days')
            WHERE email=:e
        """), dict(e=email))
        # Handle referral credit (simple: $2 credit once at signup)
        if referral_code:
            # credit only if not already credited for this referred email
            exists = conn.execute(text("""
                SELECT 1 FROM referrals WHERE code=:c AND referred_email=:e LIMIT 1
            """), dict(c=referral_code, e=email)).first()
            if not exists:
                conn.execute(text("""
                    INSERT INTO referrals(referrer_email, referrer_user_id, code, referred_email,
                                          credited_amount, credit_status, credited_at, note)
                    VALUES('', '', :c, :e, 2.00, 'credited', NOW(), 'Signup credit')
                """), dict(c=referral_code, e=email))
                conn.execute(text("""
                    UPDATE users SET credits_balance = COALESCE(credits_balance,0) + 2.00 WHERE email=:e
                """), dict(e=email))
        # Decide if we should (re)send Plex invite — using the new plex_service.py logic
invite_needed = True
if u["plex_invite_status"] in ("sent", "accepted"):
    invite_needed = False

if invite_needed:
    try:
        status = invite_user(email, full_name)
        conn.execute(text("""
            INSERT INTO invites(invite_id, user_id, email, plex_server, sent_at, status, attempts)
            VALUES(:iid, :uid, :email, :server, NOW(), :status, 1)
        """), dict(
            iid=f"i_{uuid.uuid4().hex[:10]}",
            uid=user_id,
            email=email,
            server=os.getenv("PLEX_SERVER_NAME", ""),
            status=status
        ))

        conn.execute(text("""
            UPDATE users SET plex_invite_status=:status WHERE email=:email
        """), dict(email=email, status=status))

    except Exception as ex:
        conn.execute(text("""
            INSERT INTO invites(invite_id, user_id, email, plex_server, sent_at, status, error_message, attempts)
            VALUES(:iid, :uid, :email, :server, NOW(), 'error', :msg, 1)
        """), dict(
            iid=f"i_{uuid.uuid4().hex[:10]}",
            uid=user_id,
            email=email,
            server=os.getenv("PLEX_SERVER_NAME", ""),
            msg=str(ex)
        ))

        conn.execute(text("""
            UPDATE users SET plex_invite_status='error' WHERE email=:email
        """), dict(email=email))
            except Exception as ex:
                conn.execute(text("""
                    INSERT INTO invites(invite_id, user_id, email, plex_server, sent_at, status, error_message, attempts)
                    VALUES(:iid, :uid, :email, :server, NOW(), 'error', :msg, 1)
                """), dict(iid=f"i_{uuid.uuid4().hex[:10]}", uid=user_id, email=email,
                             server=os.getenv("PLEX_SERVER_NAME",""), msg=str(ex)))
                # Append to Google Sheets (best-effort)
        try:
            sheets.append_row(
                "Payments",
                [
                    datetime.utcnow().isoformat(),
                    email,
                    amount,
                    currency,
                    provider_event_id,
                    period_start,
                    period_end,
                    idempotency_key,
                    "ok",
                ],
            )
        except Exception as _:
            pass

        conn.execute(text("""
            INSERT INTO audit_log(event, user_id, email, details)
            VALUES('payment_processed', :uid, :email, :details)
        """), dict(uid=user_id, email=email, details=f"amount={amount}, invite={'yes' if invite_needed else 'no'}"))
    return {"ok": True, "user": email, "invite_sent": invite_needed}

@app.get("/healthz")
def healthz():
    return {"ok": True}



