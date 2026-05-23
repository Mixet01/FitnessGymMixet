import csv
from copy import deepcopy
import io
import json
import mimetypes
import os
import re
import time
import uuid
from urllib.parse import urlencode
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
from html import escape
from threading import Lock

import requests
from flask import Flask, Response, g, has_request_context, jsonify, redirect, render_template, request, send_file, session, url_for

try:
    import psycopg
except Exception:
    psycopg = None


def env_int(name, default):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.environ.get("SPESE_MIXET_DATA_DIR", os.path.join(BASE_DIR, "data")).strip() or os.path.join(BASE_DIR, "data")
if not os.path.isabs(DATA_ROOT):
    DATA_ROOT = os.path.abspath(os.path.join(BASE_DIR, DATA_ROOT))

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DB_MODE = bool(DATABASE_URL)
DATA_FILE = os.path.join(DATA_ROOT, "spese_mixet.json")

APP_NAME = os.environ.get("PWA_APP_NAME", "Spese Mixet").strip() or "Spese Mixet"
SHORT_NAME = os.environ.get("PWA_SHORT_NAME", "Mixet").strip() or "Mixet"
THEME_COLOR = os.environ.get("PWA_THEME_COLOR", "#1f7a6f").strip() or "#1f7a6f"
BG_COLOR = os.environ.get("PWA_BG_COLOR", "#f7f1e8").strip() or "#f7f1e8"
PWA_ICON_FILE = os.environ.get("PWA_ICON_FILE", "").strip()
ICON_TEXT = os.environ.get("PWA_ICON_TEXT", "SM").strip() or "SM"
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
APP_PORT = int(os.environ.get("PWA_PORT", "8010"))
SESSION_DAYS = env_int("SPESE_MIXET_SESSION_DAYS", 90)
ASSET_VERSION = os.environ.get("SPESE_MIXET_ASSET_VERSION", "2026-05-23-v6").strip() or "2026-05-23-v6"
STATE_CACHE_TTL = max(0, env_int("SPESE_MIXET_STATE_CACHE_TTL", 12))
ENABLE_BANKING_BASE_URL = os.environ.get("ENABLE_BANKING_BASE_URL", "https://api.enablebanking.com").strip().rstrip("/")
ENABLE_BANKING_APP_ID = os.environ.get("ENABLE_BANKING_APP_ID", "").strip()
ENABLE_BANKING_PRIVATE_KEY = os.environ.get("ENABLE_BANKING_PRIVATE_KEY", "")
ENABLE_BANKING_PRIVATE_KEY_PATH = os.environ.get("ENABLE_BANKING_PRIVATE_KEY_PATH", "").strip()
ENABLE_BANKING_COUNTRY = os.environ.get("ENABLE_BANKING_COUNTRY", "IT").strip().upper() or "IT"
ENABLE_BANKING_ASPSP_NAME = os.environ.get("ENABLE_BANKING_ASPSP_NAME", "").strip()
ENABLE_BANKING_ASPSP_MATCH = os.environ.get("ENABLE_BANKING_ASPSP_MATCH", "postepay,poste italiane,poste").strip()
ENABLE_BANKING_CONSENT_DAYS = max(1, min(180, env_int("ENABLE_BANKING_CONSENT_DAYS", 90)))
ENABLE_BANKING_TX_DAYS = max(7, min(365, env_int("ENABLE_BANKING_TX_DAYS", 90)))
ENABLE_BANKING_PROVIDER = "enablebanking"
BANK_AUTO_SYNC_MINUTES = max(5, min(720, env_int("BANK_AUTO_SYNC_MINUTES", 30)))

DEFAULT_CATEGORY_SEEDS = [
    {"name": "Casa", "color": "#d95d39"},
    {"name": "Spesa", "color": "#f18805"},
    {"name": "Trasporti", "color": "#2a9d8f"},
    {"name": "Salute", "color": "#457b9d"},
    {"name": "Tempo libero", "color": "#8d5a97"},
    {"name": "Stipendio", "color": "#1f7a6f"},
    {"name": "Extra", "color": "#264653"},
]

MONEY_STEP = Decimal("0.01")
lock = Lock()
state_cache = {}
aspsp_cache = {}

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"), static_folder=os.path.join(BASE_DIR, "static"))
app.secret_key = os.environ.get("SPESE_MIXET_SECRET", "change-me-in-production")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=SESSION_DAYS)
app.config["SESSION_COOKIE_NAME"] = "spese_mixet_session"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SPESE_MIXET_SECURE_COOKIE", "0") == "1"
app.config["SESSION_REFRESH_EACH_REQUEST"] = True


def normalize_email(value):
    return str(value or "").strip().lower()


def clean_text(value, fallback="", max_len=120):
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return fallback
    return text[:max_len]


def pwa_color(value, fallback):
    value = str(value or "").strip()
    return value if re.fullmatch(r"#[0-9a-fA-F]{6}", value) else fallback


def pwa_label(value):
    cleaned = re.sub(r"[^A-Za-z0-9 ]", "", str(value or "").strip().upper())
    return (cleaned[:3] or "SM").strip()


def versioned_asset(path):
    clean_path = str(path or "").strip()
    if not clean_path:
        return ""
    sep = "&" if "?" in clean_path else "?"
    return f"{clean_path}{sep}v={ASSET_VERSION}"


def get_pwa_icon_descriptor():
    candidates = []
    if PWA_ICON_FILE:
        candidates.append(PWA_ICON_FILE)
    candidates.extend(
        [
            "pwa-icon.png",
            "pwa-icon-512.png",
            "pwa-icon.jpg",
            "pwa-icon.jpeg",
            "pwa-icon.svg",
            "icon.png",
            "icon.jpg",
            "icon.jpeg",
            "icon.svg",
        ]
    )

    for candidate in candidates:
        safe_name = os.path.basename(candidate)
        full_path = os.path.join(app.static_folder, safe_name)
        if os.path.exists(full_path):
            mime = mimetypes.guess_type(full_path)[0] or "image/png"
            sizes = "any" if safe_name.lower().endswith(".svg") else "512x512"
            return {
                "href": f"/static/{safe_name}",
                "src": f"/static/{safe_name}",
                "full_path": full_path,
                "type": mime,
                "sizes": sizes,
                "purpose": "any maskable",
                "is_custom": True,
                "filename": safe_name,
            }

    return {
        "href": "/pwa-icon.svg",
        "src": "/pwa-icon.svg",
        "full_path": "",
        "type": "image/svg+xml",
        "sizes": "any",
        "purpose": "any maskable",
        "is_custom": False,
        "filename": "pwa-icon.svg",
    }


def pwa_icon_cache_tag(icon):
    full_path = icon.get("full_path") or ""
    if full_path and os.path.exists(full_path):
        return str(int(os.path.getmtime(full_path)))
    return ASSET_VERSION


def sanitize_color(value, fallback="#1f7a6f"):
    value = str(value or "").strip()
    return value if re.fullmatch(r"#[0-9a-fA-F]{6}", value) else fallback


def to_decimal(value):
    raw = str(value or "").strip().replace(",", ".")
    if not raw:
        raise ValueError("Importo obbligatorio.")
    try:
        amount = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("Importo non valido.") from exc
    amount = amount.quantize(MONEY_STEP, rounding=ROUND_HALF_UP)
    if amount <= 0:
        raise ValueError("L'importo deve essere maggiore di zero.")
    return amount


def money_to_float(value):
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_iso_date(value):
    try:
        return datetime.strptime(str(value or "").strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Data non valida. Usa formato YYYY-MM-DD.") from exc


def shift_month(month_start, delta):
    year = month_start.year
    month = month_start.month + delta
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return date(year, month, 1)


def month_bounds(month_value):
    cleaned = str(month_value or "").strip()
    if not cleaned:
        today = date.today()
        cleaned = today.strftime("%Y-%m")
    try:
        start = datetime.strptime(cleaned, "%Y-%m").date().replace(day=1)
    except ValueError as exc:
        raise ValueError("Mese non valido. Usa formato YYYY-MM.") from exc
    end = shift_month(start, 1)
    return cleaned, start, end


def month_label(month_value):
    year, month = month_value.split("-")
    labels = [
        "Gennaio",
        "Febbraio",
        "Marzo",
        "Aprile",
        "Maggio",
        "Giugno",
        "Luglio",
        "Agosto",
        "Settembre",
        "Ottobre",
        "Novembre",
        "Dicembre",
    ]
    return f"{labels[int(month) - 1]} {year}"


def month_day_count(month_start):
    return (shift_month(month_start, 1) - month_start).days


def clamp_cycle_day(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 25
    return max(1, min(28, parsed))


def date_in_month(month_start, day):
    return date(month_start.year, month_start.month, min(int(day), month_day_count(month_start)))


def format_period_label(start_date, end_date):
    inclusive_end = end_date - timedelta(days=1)
    return f"{start_date.strftime('%d/%m/%Y')} - {inclusive_end.strftime('%d/%m/%Y')}"


def iso_utc(dt_value=None):
    dt_value = dt_value or datetime.utcnow()
    return dt_value.replace(microsecond=0).isoformat() + "Z"


def clone_payload(payload):
    return deepcopy(payload)


def state_cache_key(email, month_value, profile_mode, cycle_day):
    return "|".join(
        [
            normalize_email(email),
            str(month_value or "").strip(),
            str(profile_mode or "month").strip().lower(),
            str(clamp_cycle_day(cycle_day)),
        ]
    )


def get_cached_state(email, month_value, profile_mode, cycle_day):
    if STATE_CACHE_TTL <= 0:
        return None
    key = state_cache_key(email, month_value, profile_mode, cycle_day)
    item = state_cache.get(key)
    if not item:
        return None
    if (time.time() - float(item.get("timestamp", 0.0))) > STATE_CACHE_TTL:
        state_cache.pop(key, None)
        return None
    return clone_payload(item.get("payload"))


def set_cached_state(email, month_value, profile_mode, cycle_day, payload):
    if STATE_CACHE_TTL <= 0:
        return
    state_cache[state_cache_key(email, month_value, profile_mode, cycle_day)] = {
        "timestamp": time.time(),
        "payload": clone_payload(payload),
    }


def invalidate_state_cache(email=None):
    if not email:
        state_cache.clear()
        return
    prefix = f"{normalize_email(email)}|"
    for key in list(state_cache.keys()):
        if key.startswith(prefix):
            state_cache.pop(key, None)


def resolve_profile_period(month_value, profile_mode, cycle_day):
    profile_mode = str(profile_mode or "month").strip().lower()
    profile_mode = "cycle" if profile_mode == "cycle" else "month"
    cycle_day = clamp_cycle_day(cycle_day)
    _month_key, start_date, end_date = month_bounds(month_value)

    if profile_mode == "cycle":
        previous_month = shift_month(start_date, -1)
        start_date = date_in_month(previous_month, cycle_day)
        end_date = date_in_month(shift_month(previous_month, 1), cycle_day)

    return {
        "mode": profile_mode,
        "cycle_day": cycle_day,
        "start_date": start_date,
        "end_date": end_date,
        "label": format_period_label(start_date, end_date),
    }


def entry_type_label(entry_type):
    return "Entrata" if entry_type == "income" else "Spesa"


class ExpenseStore:
    def __init__(self, data_file):
        self.data_file = data_file
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        if DB_MODE:
            self.ensure_db_schema()
        else:
            self.ensure_file_state()

    def db_connect(self):
        if psycopg is None:
            raise RuntimeError("Driver PostgreSQL non disponibile. Installa 'psycopg[binary]'.")
        return psycopg.connect(DATABASE_URL, autocommit=True, prepare_threshold=None)

    def ensure_db_schema(self):
        with self.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS app_users (
                        email TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        picture TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        last_login TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS expense_categories (
                        id BIGSERIAL PRIMARY KEY,
                        user_email TEXT NOT NULL REFERENCES app_users(email) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        color TEXT NOT NULL DEFAULT '#1f7a6f',
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        archived BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS expense_entries (
                        id BIGSERIAL PRIMARY KEY,
                        user_email TEXT NOT NULL REFERENCES app_users(email) ON DELETE CASCADE,
                        category_id BIGINT REFERENCES expense_categories(id) ON DELETE SET NULL,
                        entry_type TEXT NOT NULL CHECK (entry_type IN ('expense', 'income')),
                        title TEXT NOT NULL,
                        notes TEXT NOT NULL DEFAULT '',
                        amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
                        occurred_on DATE NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_expense_categories_user
                    ON expense_categories (user_email, archived, sort_order, id)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_expense_entries_user_date
                    ON expense_entries (user_email, occurred_on DESC, id DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_expense_entries_user_category
                    ON expense_entries (user_email, category_id)
                    """
                )
                cur.execute("ALTER TABLE expense_entries ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual'")
                cur.execute("ALTER TABLE expense_entries ADD COLUMN IF NOT EXISTS external_id TEXT NOT NULL DEFAULT ''")
                cur.execute("ALTER TABLE expense_entries ADD COLUMN IF NOT EXISTS imported_at TIMESTAMPTZ NULL")
                cur.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_expense_entries_user_source_external
                    ON expense_entries (user_email, source, external_id)
                    WHERE external_id <> ''
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS bank_links (
                        user_email TEXT PRIMARY KEY REFERENCES app_users(email) ON DELETE CASCADE,
                        provider TEXT NOT NULL DEFAULT 'enablebanking',
                        aspsp_name TEXT NOT NULL DEFAULT '',
                        account_uid TEXT NOT NULL DEFAULT '',
                        account_name TEXT NOT NULL DEFAULT '',
                        account_iban TEXT NOT NULL DEFAULT '',
                        account_currency TEXT NOT NULL DEFAULT 'EUR',
                        session_id TEXT NOT NULL DEFAULT '',
                        access_valid_until TEXT NOT NULL DEFAULT '',
                        connected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS bank_snapshots (
                        user_email TEXT PRIMARY KEY REFERENCES app_users(email) ON DELETE CASCADE,
                        snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS bank_auth_flows (
                        state TEXT PRIMARY KEY,
                        user_email TEXT NOT NULL REFERENCES app_users(email) ON DELETE CASCADE,
                        aspsp_name TEXT NOT NULL DEFAULT '',
                        access_valid_until TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )

    def ensure_file_state(self):
        if not os.path.exists(self.data_file):
            self.save_file_state(self.default_file_state())

    def default_file_state(self):
        return {
            "users": {},
            "categories": {},
            "entries": {},
            "bank_links": {},
            "bank_snapshots": {},
            "bank_auth_flows": {},
            "next_category_id": 1,
            "next_entry_id": 1,
        }

    def load_file_state(self):
        if not os.path.exists(self.data_file):
            return self.default_file_state()
        with open(self.data_file, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        state = self.default_file_state()
        state.update(data or {})
        state["users"] = state.get("users", {}) or {}
        state["categories"] = state.get("categories", {}) or {}
        state["entries"] = state.get("entries", {}) or {}
        state["bank_links"] = state.get("bank_links", {}) or {}
        state["bank_snapshots"] = state.get("bank_snapshots", {}) or {}
        state["bank_auth_flows"] = state.get("bank_auth_flows", {}) or {}
        state["next_category_id"] = int(state.get("next_category_id", 1) or 1)
        state["next_entry_id"] = int(state.get("next_entry_id", 1) or 1)
        return state

    def save_file_state(self, state):
        with open(self.data_file, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)

    def serialize_user(self, user):
        if not user:
            return None
        return {
            "email": normalize_email(user.get("email")),
            "name": clean_text(user.get("name"), normalize_email(user.get("email")), 80),
            "picture": str(user.get("picture", "") or ""),
            "created_at": str(user.get("created_at", "") or ""),
            "last_login": str(user.get("last_login", "") or ""),
        }

    def serialize_category(self, category):
        if not category:
            return None
        return {
            "id": int(category["id"]),
            "name": str(category.get("name") or ""),
            "color": sanitize_color(category.get("color"), "#1f7a6f"),
            "sort_order": int(category.get("sort_order", 0) or 0),
            "archived": bool(category.get("archived", False)),
        }

    def serialize_entry(self, entry):
        if not entry:
            return None
        category = None
        if entry.get("category_id"):
            category = {
                "id": int(entry["category_id"]),
                "name": str(entry.get("category_name") or "Senza categoria"),
                "color": sanitize_color(entry.get("category_color"), "#8b6f47"),
                "archived": bool(entry.get("category_archived", False)),
            }
        return {
            "id": int(entry["id"]),
            "entry_type": str(entry.get("entry_type") or "expense"),
            "entry_type_label": entry_type_label(str(entry.get("entry_type") or "expense")),
            "title": str(entry.get("title") or ""),
            "notes": str(entry.get("notes") or ""),
            "amount": money_to_float(entry.get("amount")),
            "occurred_on": str(entry.get("occurred_on") or ""),
            "created_at": str(entry.get("created_at") or ""),
            "updated_at": str(entry.get("updated_at") or ""),
            "source": str(entry.get("source") or "manual"),
            "external_id": str(entry.get("external_id") or ""),
            "imported": str(entry.get("source") or "manual") != "manual",
            "needs_category": str(entry.get("source") or "manual") != "manual" and category is None,
            "category": category,
        }

    def ensure_default_categories(self, email, state=None):
        email = normalize_email(email)
        if DB_MODE:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM expense_categories WHERE user_email = %s", (email,))
                    count = int(cur.fetchone()[0] or 0)
                    if count > 0:
                        return
                    for index, item in enumerate(DEFAULT_CATEGORY_SEEDS, start=1):
                        cur.execute(
                            """
                            INSERT INTO expense_categories (user_email, name, color, sort_order, archived)
                            VALUES (%s, %s, %s, %s, FALSE)
                            """,
                            (email, item["name"], item["color"], index * 10),
                        )
            return

        state = state or self.load_file_state()
        current = state["categories"].setdefault(email, [])
        if current:
            return state
        for index, item in enumerate(DEFAULT_CATEGORY_SEEDS, start=1):
            current.append(
                {
                    "id": state["next_category_id"],
                    "name": item["name"],
                    "color": item["color"],
                    "sort_order": index * 10,
                    "archived": False,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
            state["next_category_id"] += 1
        return state

    def ensure_user(self, email, name, picture):
        email = normalize_email(email)
        name = clean_text(name, email, 80)
        picture = str(picture or "")
        now = datetime.now().isoformat(timespec="seconds")
        if DB_MODE:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO app_users (email, name, picture, created_at, last_login)
                        VALUES (%s, %s, %s, NOW(), NOW())
                        ON CONFLICT (email) DO UPDATE SET
                            name = EXCLUDED.name,
                            picture = EXCLUDED.picture,
                            last_login = NOW()
                        """,
                        (email, name, picture),
                    )
            self.ensure_default_categories(email)
            return self.get_user(email)

        state = self.load_file_state()
        user = state["users"].get(email) or {"email": email, "created_at": now}
        user["name"] = name
        user["picture"] = picture
        user["last_login"] = now
        state["users"][email] = user
        self.ensure_default_categories(email, state=state)
        state["categories"].setdefault(email, [])
        state["entries"].setdefault(email, [])
        self.save_file_state(state)
        return self.serialize_user(user)

    def get_user(self, email):
        email = normalize_email(email)
        if not email:
            return None
        if DB_MODE:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT email, name, picture, created_at, last_login
                        FROM app_users
                        WHERE email = %s
                        """,
                        (email,),
                    )
                    row = cur.fetchone()
            if not row:
                return None
            return {
                "email": row[0],
                "name": row[1],
                "picture": row[2] or "",
                "created_at": row[3].isoformat(timespec="seconds") if row[3] else "",
                "last_login": row[4].isoformat(timespec="seconds") if row[4] else "",
            }
        state = self.load_file_state()
        return self.serialize_user(state["users"].get(email))

    def serialize_bank_link(self, item):
        if not item:
            return None
        return {
            "provider": clean_text(item.get("provider"), ENABLE_BANKING_PROVIDER, 40),
            "aspsp_name": clean_text(item.get("aspsp_name"), "", 120),
            "account_uid": str(item.get("account_uid", "") or ""),
            "account_name": clean_text(item.get("account_name"), "", 120),
            "account_iban": str(item.get("account_iban", "") or ""),
            "account_currency": str(item.get("account_currency", "") or "EUR"),
            "session_id": str(item.get("session_id", "") or ""),
            "access_valid_until": str(item.get("access_valid_until", "") or ""),
            "connected_at": str(item.get("connected_at", "") or ""),
            "updated_at": str(item.get("updated_at", "") or ""),
        }

    def get_bank_link(self, email):
        email = normalize_email(email)
        if not email:
            return None
        if DB_MODE:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT provider,
                               aspsp_name,
                               account_uid,
                               account_name,
                               account_iban,
                               account_currency,
                               session_id,
                               access_valid_until,
                               connected_at,
                               updated_at
                        FROM bank_links
                        WHERE user_email = %s
                        """,
                        (email,),
                    )
                    row = cur.fetchone()
            if not row:
                return None
            return self.serialize_bank_link(
                {
                    "provider": row[0],
                    "aspsp_name": row[1],
                    "account_uid": row[2],
                    "account_name": row[3],
                    "account_iban": row[4],
                    "account_currency": row[5],
                    "session_id": row[6],
                    "access_valid_until": row[7],
                    "connected_at": row[8].isoformat(timespec="seconds") if row[8] else "",
                    "updated_at": row[9].isoformat(timespec="seconds") if row[9] else "",
                }
            )

        state = self.load_file_state()
        return self.serialize_bank_link(state["bank_links"].get(email))

    def save_bank_link(self, email, payload):
        email = normalize_email(email)
        item = self.serialize_bank_link(payload) or {}
        item["connected_at"] = item.get("connected_at") or datetime.now().isoformat(timespec="seconds")
        item["updated_at"] = datetime.now().isoformat(timespec="seconds")
        if DB_MODE:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO bank_links (
                            user_email,
                            provider,
                            aspsp_name,
                            account_uid,
                            account_name,
                            account_iban,
                            account_currency,
                            session_id,
                            access_valid_until,
                            connected_at,
                            updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                        ON CONFLICT (user_email) DO UPDATE SET
                            provider = EXCLUDED.provider,
                            aspsp_name = EXCLUDED.aspsp_name,
                            account_uid = EXCLUDED.account_uid,
                            account_name = EXCLUDED.account_name,
                            account_iban = EXCLUDED.account_iban,
                            account_currency = EXCLUDED.account_currency,
                            session_id = EXCLUDED.session_id,
                            access_valid_until = EXCLUDED.access_valid_until,
                            updated_at = NOW()
                        """,
                        (
                            email,
                            item["provider"],
                            item["aspsp_name"],
                            item["account_uid"],
                            item["account_name"],
                            item["account_iban"],
                            item["account_currency"],
                            item["session_id"],
                            item["access_valid_until"],
                        ),
                    )
            return self.get_bank_link(email)

        state = self.load_file_state()
        state["bank_links"][email] = item
        self.save_file_state(state)
        return self.serialize_bank_link(item)

    def delete_bank_link(self, email):
        email = normalize_email(email)
        if DB_MODE:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM bank_links WHERE user_email = %s", (email,))
            return

        state = self.load_file_state()
        state["bank_links"].pop(email, None)
        self.save_file_state(state)

    def get_bank_snapshot(self, email):
        email = normalize_email(email)
        if not email:
            return {}
        if DB_MODE:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT snapshot_json
                        FROM bank_snapshots
                        WHERE user_email = %s
                        """,
                        (email,),
                    )
                    row = cur.fetchone()
            if not row or not row[0]:
                return {}
            if isinstance(row[0], dict):
                return row[0]
            if isinstance(row[0], str):
                try:
                    return json.loads(row[0])
                except json.JSONDecodeError:
                    return {}
            return {}

        state = self.load_file_state()
        return state["bank_snapshots"].get(email) or {}

    def save_bank_snapshot(self, email, snapshot):
        email = normalize_email(email)
        data = dict(snapshot or {})
        if DB_MODE:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO bank_snapshots (user_email, snapshot_json, updated_at)
                        VALUES (%s, %s::jsonb, NOW())
                        ON CONFLICT (user_email) DO UPDATE SET
                            snapshot_json = EXCLUDED.snapshot_json,
                            updated_at = NOW()
                        """,
                        (email, json.dumps(data, ensure_ascii=False)),
                    )
            return data

        state = self.load_file_state()
        state["bank_snapshots"][email] = data
        self.save_file_state(state)
        return data

    def delete_bank_snapshot(self, email):
        email = normalize_email(email)
        if DB_MODE:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM bank_snapshots WHERE user_email = %s", (email,))
            return

        state = self.load_file_state()
        state["bank_snapshots"].pop(email, None)
        self.save_file_state(state)

    def clear_bank_data(self, email):
        self.delete_bank_snapshot(email)
        self.delete_bank_link(email)

    def save_bank_auth_flow(self, flow_state, payload):
        flow_state = str(flow_state or "").strip()
        if not flow_state:
            raise ValueError("State bancario mancante.")
        item = {
            "state": flow_state,
            "user_email": normalize_email(payload.get("user_email")),
            "aspsp_name": clean_text(payload.get("aspsp_name"), "", 120),
            "access_valid_until": str(payload.get("access_valid_until", "") or ""),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        if DB_MODE:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO bank_auth_flows (state, user_email, aspsp_name, access_valid_until, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, NOW(), NOW())
                        ON CONFLICT (state) DO UPDATE SET
                            user_email = EXCLUDED.user_email,
                            aspsp_name = EXCLUDED.aspsp_name,
                            access_valid_until = EXCLUDED.access_valid_until,
                            updated_at = NOW()
                        """,
                        (flow_state, item["user_email"], item["aspsp_name"], item["access_valid_until"]),
                    )
            return item

        state = self.load_file_state()
        state["bank_auth_flows"][flow_state] = item
        self.save_file_state(state)
        return item

    def get_bank_auth_flow(self, flow_state):
        flow_state = str(flow_state or "").strip()
        if not flow_state:
            return None
        if DB_MODE:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT state, user_email, aspsp_name, access_valid_until, created_at, updated_at
                        FROM bank_auth_flows
                        WHERE state = %s
                        """,
                        (flow_state,),
                    )
                    row = cur.fetchone()
            if not row:
                return None
            return {
                "state": row[0],
                "user_email": row[1],
                "aspsp_name": row[2],
                "access_valid_until": row[3],
                "created_at": row[4].isoformat(timespec="seconds") if row[4] else "",
                "updated_at": row[5].isoformat(timespec="seconds") if row[5] else "",
            }

        state = self.load_file_state()
        return state["bank_auth_flows"].get(flow_state)

    def delete_bank_auth_flow(self, flow_state):
        flow_state = str(flow_state or "").strip()
        if not flow_state:
            return
        if DB_MODE:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM bank_auth_flows WHERE state = %s", (flow_state,))
            return

        state = self.load_file_state()
        state["bank_auth_flows"].pop(flow_state, None)
        self.save_file_state(state)

    def list_categories(self, email, include_archived=True):
        email = normalize_email(email)
        if DB_MODE:
            sql = """
                SELECT id, name, color, sort_order, archived
                FROM expense_categories
                WHERE user_email = %s
            """
            params = [email]
            if not include_archived:
                sql += " AND archived = FALSE"
            sql += " ORDER BY archived ASC, sort_order ASC, name ASC, id ASC"
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    rows = cur.fetchall()
            return [
                {
                    "id": row[0],
                    "name": row[1],
                    "color": row[2],
                    "sort_order": row[3],
                    "archived": bool(row[4]),
                }
                for row in rows
            ]

        state = self.load_file_state()
        items = state["categories"].get(email, [])
        filtered = [item for item in items if include_archived or not item.get("archived", False)]
        filtered.sort(key=lambda item: (bool(item.get("archived", False)), int(item.get("sort_order", 0)), item.get("name", "").lower(), int(item.get("id", 0))))
        return [self.serialize_category(item) for item in filtered]

    def category_usage(self, email):
        email = normalize_email(email)
        usage = {}
        if DB_MODE:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT category_id,
                               COUNT(*) AS item_count,
                               COALESCE(SUM(CASE WHEN entry_type = 'expense' THEN amount ELSE 0 END), 0),
                               COALESCE(SUM(CASE WHEN entry_type = 'income' THEN amount ELSE 0 END), 0)
                        FROM expense_entries
                        WHERE user_email = %s AND category_id IS NOT NULL
                        GROUP BY category_id
                        """,
                        (email,),
                    )
                    rows = cur.fetchall()
            for row in rows:
                usage[int(row[0])] = {
                    "entry_count": int(row[1] or 0),
                    "expense_total": money_to_float(row[2]),
                    "income_total": money_to_float(row[3]),
                }
            return usage

        state = self.load_file_state()
        for entry in state["entries"].get(email, []):
            category_id = entry.get("category_id")
            if not category_id:
                continue
            key = int(category_id)
            bucket = usage.setdefault(key, {"entry_count": 0, "expense_total": 0.0, "income_total": 0.0})
            bucket["entry_count"] += 1
            amount = money_to_float(entry.get("amount"))
            if entry.get("entry_type") == "income":
                bucket["income_total"] += amount
            else:
                bucket["expense_total"] += amount
        return usage

    def next_category_sort(self, email):
        email = normalize_email(email)
        if DB_MODE:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COALESCE(MAX(sort_order), 0) + 10 FROM expense_categories WHERE user_email = %s",
                        (email,),
                    )
                    return int(cur.fetchone()[0] or 10)
        state = self.load_file_state()
        current = state["categories"].get(email, [])
        current_max = max([int(item.get("sort_order", 0) or 0) for item in current], default=0)
        return current_max + 10

    def save_category(self, email, payload, category_id=None):
        email = normalize_email(email)
        name = clean_text(payload.get("name"), "", 40)
        color = sanitize_color(payload.get("color"), "#1f7a6f")
        archived = bool(payload.get("archived", False))
        if not name:
            raise ValueError("Inserisci un nome categoria.")

        if DB_MODE:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id
                        FROM expense_categories
                        WHERE user_email = %s AND LOWER(name) = LOWER(%s)
                          AND (%s IS NULL OR id <> %s)
                        LIMIT 1
                        """,
                        (email, name, category_id, category_id),
                    )
                    if cur.fetchone():
                        raise ValueError("Esiste gia una categoria con questo nome.")

                    if category_id is None:
                        sort_order = self.next_category_sort(email)
                        cur.execute(
                            """
                            INSERT INTO expense_categories (user_email, name, color, sort_order, archived)
                            VALUES (%s, %s, %s, %s, %s)
                            RETURNING id
                            """,
                            (email, name, color, sort_order, archived),
                        )
                        new_id = int(cur.fetchone()[0])
                        return self.get_category(email, new_id)

                    cur.execute(
                        """
                        UPDATE expense_categories
                        SET name = %s,
                            color = %s,
                            archived = %s
                        WHERE id = %s AND user_email = %s
                        RETURNING id
                        """,
                        (name, color, archived, category_id, email),
                    )
                    row = cur.fetchone()
                    if not row:
                        raise KeyError("Categoria non trovata.")
                    return self.get_category(email, int(row[0]))

        state = self.load_file_state()
        categories = state["categories"].setdefault(email, [])
        duplicate = next(
            (item for item in categories if item["name"].strip().lower() == name.lower() and int(item["id"]) != int(category_id or 0)),
            None,
        )
        if duplicate:
            raise ValueError("Esiste gia una categoria con questo nome.")

        if category_id is None:
            category = {
                "id": state["next_category_id"],
                "name": name,
                "color": color,
                "sort_order": self.next_category_sort(email),
                "archived": archived,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
            state["next_category_id"] += 1
            categories.append(category)
        else:
            category = next((item for item in categories if int(item["id"]) == int(category_id)), None)
            if not category:
                raise KeyError("Categoria non trovata.")
            category["name"] = name
            category["color"] = color
            category["archived"] = archived
        self.save_file_state(state)
        return self.serialize_category(category)

    def get_category(self, email, category_id):
        email = normalize_email(email)
        category_id = int(category_id)
        if DB_MODE:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, name, color, sort_order, archived
                        FROM expense_categories
                        WHERE id = %s AND user_email = %s
                        """,
                        (category_id, email),
                    )
                    row = cur.fetchone()
            if not row:
                return None
            return self.serialize_category(
                {
                    "id": row[0],
                    "name": row[1],
                    "color": row[2],
                    "sort_order": row[3],
                    "archived": row[4],
                }
            )

        state = self.load_file_state()
        category = next((item for item in state["categories"].get(email, []) if int(item["id"]) == category_id), None)
        return self.serialize_category(category)

    def delete_category(self, email, category_id):
        email = normalize_email(email)
        category_id = int(category_id)
        if DB_MODE:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM expense_entries WHERE user_email = %s AND category_id = %s",
                        (email, category_id),
                    )
                    linked = int(cur.fetchone()[0] or 0)
                    if linked > 0:
                        cur.execute(
                            "UPDATE expense_categories SET archived = TRUE WHERE id = %s AND user_email = %s RETURNING id",
                            (category_id, email),
                        )
                        if not cur.fetchone():
                            raise KeyError("Categoria non trovata.")
                        return {"action": "archived", "message": "Categoria archiviata per non perdere lo storico."}

                    cur.execute(
                        "DELETE FROM expense_categories WHERE id = %s AND user_email = %s RETURNING id",
                        (category_id, email),
                    )
                    if not cur.fetchone():
                        raise KeyError("Categoria non trovata.")
                    return {"action": "deleted", "message": "Categoria eliminata."}

        state = self.load_file_state()
        categories = state["categories"].get(email, [])
        category = next((item for item in categories if int(item["id"]) == category_id), None)
        if not category:
            raise KeyError("Categoria non trovata.")
        linked = sum(1 for item in state["entries"].get(email, []) if int(item.get("category_id") or 0) == category_id)
        if linked > 0:
            category["archived"] = True
            self.save_file_state(state)
            return {"action": "archived", "message": "Categoria archiviata per non perdere lo storico."}
        state["categories"][email] = [item for item in categories if int(item["id"]) != category_id]
        self.save_file_state(state)
        return {"action": "deleted", "message": "Categoria eliminata."}

    def list_entries(self, email, start_date=None, end_date=None, limit=None):
        email = normalize_email(email)
        if DB_MODE:
            conditions = ["e.user_email = %s"]
            params = [email]
            if start_date is not None:
                conditions.append("e.occurred_on >= %s")
                params.append(start_date)
            if end_date is not None:
                conditions.append("e.occurred_on < %s")
                params.append(end_date)
            sql = f"""
                SELECT e.id,
                       e.entry_type,
                       e.title,
                       e.notes,
                       e.amount,
                       e.occurred_on,
                       e.created_at,
                       e.updated_at,
                       e.source,
                       e.external_id,
                       c.id,
                       c.name,
                       c.color,
                       c.archived
                FROM expense_entries e
                LEFT JOIN expense_categories c
                  ON c.id = e.category_id AND c.user_email = e.user_email
                WHERE {' AND '.join(conditions)}
                ORDER BY e.occurred_on DESC, e.id DESC
            """
            if limit is not None:
                sql += " LIMIT %s"
                params.append(int(limit))
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    rows = cur.fetchall()
            items = []
            for row in rows:
                items.append(
                    self.serialize_entry(
                        {
                            "id": row[0],
                            "entry_type": row[1],
                            "title": row[2],
                            "notes": row[3],
                            "amount": row[4],
                            "occurred_on": row[5].isoformat() if row[5] else "",
                            "created_at": row[6].isoformat(timespec="seconds") if row[6] else "",
                            "updated_at": row[7].isoformat(timespec="seconds") if row[7] else "",
                            "source": row[8] or "manual",
                            "external_id": row[9] or "",
                            "category_id": row[10],
                            "category_name": row[11],
                            "category_color": row[12],
                            "category_archived": row[13],
                        }
                    )
                )
            return items

        state = self.load_file_state()
        categories = {int(item["id"]): item for item in state["categories"].get(email, [])}
        items = []
        for raw in state["entries"].get(email, []):
            occurred_on = parse_iso_date(raw.get("occurred_on"))
            if start_date is not None and occurred_on < start_date:
                continue
            if end_date is not None and occurred_on >= end_date:
                continue
            category_id = raw.get("category_id")
            category = categories.get(int(category_id)) if category_id else None
            items.append(
                self.serialize_entry(
                    {
                        "id": raw["id"],
                        "entry_type": raw["entry_type"],
                        "title": raw["title"],
                        "notes": raw.get("notes", ""),
                        "amount": raw["amount"],
                        "occurred_on": raw["occurred_on"],
                        "created_at": raw.get("created_at", ""),
                        "updated_at": raw.get("updated_at", ""),
                        "source": raw.get("source", "manual"),
                        "external_id": raw.get("external_id", ""),
                        "category_id": category["id"] if category else None,
                        "category_name": category["name"] if category else "",
                        "category_color": category["color"] if category else "",
                        "category_archived": category.get("archived", False) if category else False,
                    }
                )
            )
        items.sort(key=lambda item: (item["occurred_on"], item["id"]), reverse=True)
        return items[: int(limit)] if limit is not None else items

    def get_entry(self, email, entry_id):
        matches = self.list_entries(email)
        return next((item for item in matches if int(item["id"]) == int(entry_id)), None)

    def validate_category_for_user(self, email, category_id):
        if category_id in ("", None):
            return None
        try:
            category_id = int(category_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("Categoria non valida.") from exc
        category = self.get_category(email, category_id)
        if not category:
            raise ValueError("Categoria non trovata.")
        return category_id

    def save_entry(self, email, payload, entry_id=None):
        email = normalize_email(email)
        entry_type = str(payload.get("entry_type") or "expense").strip().lower()
        if entry_type not in {"expense", "income"}:
            raise ValueError("Tipo movimento non valido.")
        title = clean_text(payload.get("title"), "", 72)
        notes = clean_text(payload.get("notes"), "", 360)
        amount = to_decimal(payload.get("amount"))
        occurred_on = parse_iso_date(payload.get("occurred_on"))
        category_id = self.validate_category_for_user(email, payload.get("category_id"))
        if not title:
            raise ValueError("Inserisci un titolo per il movimento.")

        if DB_MODE:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    if entry_id is None:
                        cur.execute(
                            """
                            INSERT INTO expense_entries (
                                user_email, category_id, entry_type, title, notes, amount, occurred_on, source, external_id, created_at, updated_at
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, 'manual', '', NOW(), NOW())
                            RETURNING id
                            """,
                            (email, category_id, entry_type, title, notes, amount, occurred_on),
                        )
                        saved_id = int(cur.fetchone()[0])
                    else:
                        cur.execute(
                            """
                            UPDATE expense_entries
                            SET category_id = %s,
                                entry_type = %s,
                                title = %s,
                                notes = %s,
                                amount = %s,
                                occurred_on = %s,
                                updated_at = NOW()
                            WHERE id = %s AND user_email = %s
                            RETURNING id
                            """,
                            (category_id, entry_type, title, notes, amount, occurred_on, int(entry_id), email),
                        )
                        row = cur.fetchone()
                        if not row:
                            raise KeyError("Movimento non trovato.")
                        saved_id = int(row[0])
            return self.get_entry(email, saved_id)

        state = self.load_file_state()
        entries = state["entries"].setdefault(email, [])
        now = datetime.now().isoformat(timespec="seconds")
        if entry_id is None:
            raw = {
                "id": state["next_entry_id"],
                "entry_type": entry_type,
                "title": title,
                "notes": notes,
                "amount": f"{amount:.2f}",
                "occurred_on": occurred_on.isoformat(),
                "category_id": category_id,
                "source": "manual",
                "external_id": "",
                "created_at": now,
                "updated_at": now,
            }
            state["next_entry_id"] += 1
            entries.append(raw)
        else:
            raw = next((item for item in entries if int(item["id"]) == int(entry_id)), None)
            if not raw:
                raise KeyError("Movimento non trovato.")
            raw.update(
                {
                    "entry_type": entry_type,
                    "title": title,
                    "notes": notes,
                    "amount": f"{amount:.2f}",
                    "occurred_on": occurred_on.isoformat(),
                    "category_id": category_id,
                    "updated_at": now,
                }
            )
        self.save_file_state(state)
        return self.get_entry(email, raw["id"])

    def delete_entry(self, email, entry_id):
        email = normalize_email(email)
        entry_id = int(entry_id)
        if DB_MODE:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM expense_entries WHERE id = %s AND user_email = %s RETURNING id",
                        (entry_id, email),
                    )
                    if not cur.fetchone():
                        raise KeyError("Movimento non trovato.")
            return

        state = self.load_file_state()
        entries = state["entries"].get(email, [])
        next_entries = [item for item in entries if int(item["id"]) != entry_id]
        if len(next_entries) == len(entries):
            raise KeyError("Movimento non trovato.")
        state["entries"][email] = next_entries
        self.save_file_state(state)

    def get_entry_by_external_id(self, email, source, external_id):
        email = normalize_email(email)
        source = str(source or "manual").strip().lower() or "manual"
        external_id = str(external_id or "").strip()
        if not external_id:
            return None
        if DB_MODE:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id
                        FROM expense_entries
                        WHERE user_email = %s AND source = %s AND external_id = %s
                        LIMIT 1
                        """,
                        (email, source, external_id),
                    )
                    row = cur.fetchone()
            if not row:
                return None
            return self.get_entry(email, int(row[0]))

        state = self.load_file_state()
        for raw in state["entries"].get(email, []):
            if str(raw.get("source") or "manual") == source and str(raw.get("external_id") or "") == external_id:
                return self.get_entry(email, raw["id"])
        return None

    def upsert_imported_entry(self, email, transaction):
        email = normalize_email(email)
        external_id = str(transaction.get("external_id") or transaction.get("id") or "").strip()
        if not external_id:
            return None
        entry_type = "income" if str(transaction.get("direction") or "expense") == "income" else "expense"
        title = clean_text(transaction.get("title"), "Movimento Postepay", 72)
        notes = clean_text(transaction.get("notes"), "", 360)
        amount = to_decimal(transaction.get("amount"))
        occurred_on = parse_iso_date(transaction.get("date"))

        existing = self.get_entry_by_external_id(email, "bank", external_id)
        if DB_MODE:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    if existing:
                        cur.execute(
                            """
                            UPDATE expense_entries
                            SET entry_type = %s,
                                title = %s,
                                notes = %s,
                                amount = %s,
                                occurred_on = %s,
                                updated_at = NOW()
                            WHERE id = %s AND user_email = %s
                            RETURNING id
                            """,
                            (entry_type, title, notes, amount, occurred_on, int(existing["id"]), email),
                        )
                        saved_id = int(cur.fetchone()[0])
                    else:
                        cur.execute(
                            """
                            INSERT INTO expense_entries (
                                user_email,
                                category_id,
                                entry_type,
                                title,
                                notes,
                                amount,
                                occurred_on,
                                source,
                                external_id,
                                imported_at,
                                created_at,
                                updated_at
                            )
                            VALUES (%s, NULL, %s, %s, %s, %s, %s, 'bank', %s, NOW(), NOW(), NOW())
                            RETURNING id
                            """,
                            (email, entry_type, title, notes, amount, occurred_on, external_id),
                        )
                        saved_id = int(cur.fetchone()[0])
            return self.get_entry(email, saved_id)

        state = self.load_file_state()
        entries = state["entries"].setdefault(email, [])
        now = datetime.now().isoformat(timespec="seconds")
        existing_raw = next(
            (item for item in entries if str(item.get("source") or "manual") == "bank" and str(item.get("external_id") or "") == external_id),
            None,
        )
        if existing_raw:
            existing_raw["entry_type"] = entry_type
            existing_raw["title"] = title
            existing_raw["notes"] = notes
            existing_raw["amount"] = f"{amount:.2f}"
            existing_raw["occurred_on"] = occurred_on.isoformat()
            existing_raw["updated_at"] = now
            saved_id = existing_raw["id"]
        else:
            raw = {
                "id": state["next_entry_id"],
                "entry_type": entry_type,
                "title": title,
                "notes": notes,
                "amount": f"{amount:.2f}",
                "occurred_on": occurred_on.isoformat(),
                "category_id": None,
                "source": "bank",
                "external_id": external_id,
                "imported_at": now,
                "created_at": now,
                "updated_at": now,
            }
            state["next_entry_id"] += 1
            entries.append(raw)
            saved_id = raw["id"]
        self.save_file_state(state)
        return self.get_entry(email, saved_id)

    def sync_bank_transactions(self, email, transactions):
        imported = 0
        updated = 0
        pending_category = 0
        for transaction in transactions or []:
            try:
                existing = self.get_entry_by_external_id(email, "bank", transaction.get("external_id") or transaction.get("id"))
                saved = self.upsert_imported_entry(email, transaction)
            except ValueError:
                continue
            if not saved:
                continue
            if existing:
                updated += 1
            else:
                imported += 1
            if saved.get("needs_category"):
                pending_category += 1
        return {
            "imported": imported,
            "updated": updated,
            "pending_category": pending_category,
        }

    def build_state(self, email, selected_month, profile_mode="month", cycle_day=25):
        month_value, start_date, end_date = month_bounds(selected_month)
        cached = get_cached_state(email, month_value, profile_mode, cycle_day)
        if cached:
            return cached
        entries = self.list_entries(email, start_date=start_date, end_date=end_date)
        categories = self.list_categories(email, include_archived=True)
        usage = self.category_usage(email)
        categories_out = []
        for item in categories:
            stats = usage.get(int(item["id"]), {})
            categories_out.append(
                {
                    **item,
                    "entry_count": int(stats.get("entry_count", 0)),
                    "expense_total": round(float(stats.get("expense_total", 0.0)), 2),
                    "income_total": round(float(stats.get("income_total", 0.0)), 2),
                }
            )

        summary = self.build_month_summary(entries, month_value)
        profile_period = resolve_profile_period(month_value, profile_mode, cycle_day)
        if profile_period["start_date"] == start_date and profile_period["end_date"] == end_date:
            profile_entries = entries
        else:
            profile_entries = self.list_entries(
                email,
                start_date=profile_period["start_date"],
                end_date=profile_period["end_date"],
            )
        profile_summary = self.build_profile_summary(
            profile_entries,
            profile_period["start_date"],
            profile_period["end_date"],
        )
        payload = {
            "month": month_value,
            "month_label": month_label(month_value),
            "storage_mode": "database" if DB_MODE else "file",
            "categories": categories_out,
            "entries": entries,
            "summary": summary,
            "profile_period": {
                "mode": profile_period["mode"],
                "cycle_day": profile_period["cycle_day"],
                "label": profile_period["label"],
                "start_date": profile_period["start_date"].isoformat(),
                "end_date": (profile_period["end_date"] - timedelta(days=1)).isoformat(),
            },
            "profile_summary": profile_summary,
            "bank": build_bank_state_payload(self.get_bank_link(email), self.get_bank_snapshot(email)),
        }
        set_cached_state(email, month_value, profile_mode, cycle_day, payload)
        return payload

    def build_month_summary(self, entries, month_value):
        expense_total = 0.0
        income_total = 0.0
        expense_count = 0
        income_count = 0
        active_days = set()
        category_totals = {}
        uncategorized_expense = 0.0
        biggest_expense = None

        _, start_date, _ = month_bounds(month_value)
        days_in_month = shift_month(start_date, 1) - start_date
        week_buckets = []
        cursor = start_date
        while cursor.month == start_date.month:
            bucket_start = cursor
            bucket_end = min(cursor + timedelta(days=6), shift_month(start_date, 1) - timedelta(days=1))
            week_buckets.append(
                {
                    "label": f"{bucket_start.day:02d}-{bucket_end.day:02d}",
                    "expense_total": 0.0,
                    "income_total": 0.0,
                    "balance": 0.0,
                }
            )
            cursor = bucket_end + timedelta(days=1)

        for entry in entries:
            amount = money_to_float(entry["amount"])
            occurred = parse_iso_date(entry["occurred_on"])
            active_days.add(entry["occurred_on"])
            bucket_index = min(len(week_buckets) - 1, max(0, (occurred.day - 1) // 7))

            if entry["entry_type"] == "income":
                income_total += amount
                income_count += 1
                week_buckets[bucket_index]["income_total"] += amount
            else:
                expense_total += amount
                expense_count += 1
                week_buckets[bucket_index]["expense_total"] += amount
                category = entry.get("category")
                if category:
                    bucket = category_totals.setdefault(
                        int(category["id"]),
                        {
                            "category_id": int(category["id"]),
                            "name": category["name"],
                            "color": category["color"],
                            "amount": 0.0,
                        },
                    )
                    bucket["amount"] += amount
                else:
                    uncategorized_expense += amount
                if biggest_expense is None or amount > biggest_expense["amount"]:
                    biggest_expense = {
                        "id": entry["id"],
                        "title": entry["title"],
                        "amount": round(amount, 2),
                        "occurred_on": entry["occurred_on"],
                    }

        if uncategorized_expense > 0:
            category_totals[0] = {
                "category_id": 0,
                "name": "Senza categoria",
                "color": "#8b6f47",
                "amount": uncategorized_expense,
            }

        for bucket in week_buckets:
            bucket["expense_total"] = round(bucket["expense_total"], 2)
            bucket["income_total"] = round(bucket["income_total"], 2)
            bucket["balance"] = round(bucket["income_total"] - bucket["expense_total"], 2)

        top_categories = sorted(category_totals.values(), key=lambda item: item["amount"], reverse=True)
        average_expense = round(expense_total / expense_count, 2) if expense_count else 0.0
        balance = round(income_total - expense_total, 2)
        savings_rate = round((balance / income_total) * 100, 1) if income_total > 0 else None
        daily_expense = round(expense_total / max(1, days_in_month.days), 2)

        return {
            "expense_total": round(expense_total, 2),
            "income_total": round(income_total, 2),
            "balance": balance,
            "expense_count": expense_count,
            "income_count": income_count,
            "transaction_count": len(entries),
            "active_days": len(active_days),
            "average_expense": average_expense,
            "daily_expense": daily_expense,
            "savings_rate": savings_rate,
            "top_category": top_categories[0] if top_categories else None,
            "category_totals": top_categories[:6],
            "weekly_totals": week_buckets,
            "biggest_expense": biggest_expense,
        }

    def build_profile_summary(self, entries, start_date, end_date):
        expense_total = 0.0
        income_total = 0.0
        expense_count = 0
        income_count = 0
        active_days = set()
        category_totals = {}
        biggest_expense = None

        for entry in entries:
            amount = money_to_float(entry["amount"])
            active_days.add(entry["occurred_on"])
            if entry["entry_type"] == "income":
                income_total += amount
                income_count += 1
            else:
                expense_total += amount
                expense_count += 1
                category = entry.get("category")
                if category:
                    bucket = category_totals.setdefault(
                        int(category["id"]),
                        {
                            "category_id": int(category["id"]),
                            "name": category["name"],
                            "color": category["color"],
                            "amount": 0.0,
                        },
                    )
                    bucket["amount"] += amount
                else:
                    bucket = category_totals.setdefault(
                        0,
                        {
                            "category_id": 0,
                            "name": "Senza categoria",
                            "color": "#8b6f47",
                            "amount": 0.0,
                        },
                    )
                    bucket["amount"] += amount
                if biggest_expense is None or amount > biggest_expense["amount"]:
                    biggest_expense = {
                        "id": entry["id"],
                        "title": entry["title"],
                        "amount": round(amount, 2),
                        "occurred_on": entry["occurred_on"],
                    }

        period_days = max(1, (end_date - start_date).days)
        balance = round(income_total - expense_total, 2)
        category_totals_list = sorted(category_totals.values(), key=lambda item: item["amount"], reverse=True)
        average_expense = round(expense_total / expense_count, 2) if expense_count else 0.0
        average_income = round(income_total / income_count, 2) if income_count else 0.0
        daily_expense = round(expense_total / period_days, 2)
        savings_rate = round((balance / income_total) * 100, 1) if income_total > 0 else None

        return {
            "expense_total": round(expense_total, 2),
            "income_total": round(income_total, 2),
            "balance": balance,
            "expense_count": expense_count,
            "income_count": income_count,
            "transaction_count": len(entries),
            "active_days": len(active_days),
            "average_expense": average_expense,
            "average_income": average_income,
            "daily_expense": daily_expense,
            "savings_rate": savings_rate,
            "period_days": period_days,
            "top_category": category_totals_list[0] if category_totals_list else None,
            "category_totals": category_totals_list,
            "biggest_expense": biggest_expense,
        }

    def build_trend(self, entries, selected_start):
        months = []
        month_index = {}
        for offset in range(-5, 1):
            current = shift_month(selected_start, offset)
            key = current.strftime("%Y-%m")
            item = {
                "month": key,
                "label": current.strftime("%m/%Y"),
                "expense_total": 0.0,
                "income_total": 0.0,
                "balance": 0.0,
            }
            month_index[key] = item
            months.append(item)

        for entry in entries:
            key = entry["occurred_on"][:7]
            target = month_index.get(key)
            if not target:
                continue
            amount = money_to_float(entry["amount"])
            if entry["entry_type"] == "income":
                target["income_total"] += amount
            else:
                target["expense_total"] += amount

        for item in months:
            item["expense_total"] = round(item["expense_total"], 2)
            item["income_total"] = round(item["income_total"], 2)
            item["balance"] = round(item["income_total"] - item["expense_total"], 2)
        return months

    def export_csv(self, email, selected_month, profile_mode="month", cycle_day=25):
        month_value, start_date, end_date = month_bounds(selected_month)
        period = resolve_profile_period(month_value, profile_mode, cycle_day)
        start_date = period["start_date"]
        end_date = period["end_date"]
        entries = self.list_entries(email, start_date=start_date, end_date=end_date)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["data", "tipo", "categoria", "titolo", "note", "importo"])
        for entry in sorted(entries, key=lambda item: (item["occurred_on"], item["id"])):
            writer.writerow(
                [
                    entry["occurred_on"],
                    entry_type_label(entry["entry_type"]),
                    entry.get("category", {}).get("name", ""),
                    entry["title"],
                    entry["notes"],
                    f"{money_to_float(entry['amount']):.2f}",
                ]
            )
        raw = buffer.getvalue().encode("utf-8-sig")
        return period["label"].replace("/", "-").replace(" ", "_"), raw


store = ExpenseStore(DATA_FILE)


class BankIntegrationError(RuntimeError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = int(status_code)


def enable_banking_configured():
    return bool(ENABLE_BANKING_APP_ID and (ENABLE_BANKING_PRIVATE_KEY.strip() or ENABLE_BANKING_PRIVATE_KEY_PATH))


def load_enable_banking_private_key():
    if ENABLE_BANKING_PRIVATE_KEY.strip():
        return ENABLE_BANKING_PRIVATE_KEY.replace("\\n", "\n")
    if ENABLE_BANKING_PRIVATE_KEY_PATH:
        with open(ENABLE_BANKING_PRIVATE_KEY_PATH, "r", encoding="utf-8") as handle:
            return handle.read()
    raise BankIntegrationError("Chiave privata Enable Banking non configurata.", 503)


def make_enable_banking_token():
    if not enable_banking_configured():
        raise BankIntegrationError("Configura ENABLE_BANKING_APP_ID e la chiave privata di Enable Banking.", 503)
    try:
        import jwt as pyjwt
    except Exception as exc:
        raise BankIntegrationError(f"Dipendenza JWT mancante ({exc}).", 500) from exc

    issued_at = int(time.time())
    payload = {
        "iss": "enablebanking.com",
        "aud": "api.enablebanking.com",
        "iat": issued_at,
        "exp": issued_at + 3600,
    }
    return pyjwt.encode(
        payload,
        load_enable_banking_private_key(),
        algorithm="RS256",
        headers={"kid": ENABLE_BANKING_APP_ID},
    )


def first_non_empty(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def deep_get(source, *paths):
    for path in paths:
        current = source
        ok = True
        for key in path:
            if not isinstance(current, dict) or key not in current:
                ok = False
                break
            current = current[key]
        if ok and current not in (None, ""):
            return current
    return None


def join_text_list(values):
    if not isinstance(values, list):
        return ""
    parts = [clean_text(item, "", 120) for item in values if clean_text(item, "", 120)]
    return " | ".join(parts[:4])


def normalize_bank_date(value):
    text = str(value or "").strip()
    match = re.match(r"^\d{4}-\d{2}-\d{2}", text)
    return match.group(0) if match else ""


def psu_headers():
    if not has_request_context():
        return {}
    forwarded = request.headers.get("X-Forwarded-For", "")
    client_ip = (forwarded.split(",")[0].strip() if forwarded else "") or (request.remote_addr or "")
    headers = {
        "Psu-Ip-Address": client_ip,
        "Psu-User-Agent": request.headers.get("User-Agent", ""),
        "Psu-Referer": request.headers.get("Referer", ""),
        "Psu-Accept": request.headers.get("Accept", ""),
        "Psu-Accept-Charset": request.headers.get("Accept-Charset", ""),
        "Psu-Accept-Encoding": request.headers.get("Accept-Encoding", ""),
        "Psu-Accept-language": request.headers.get("Accept-Language", ""),
    }
    return {key: value for key, value in headers.items() if value}


def enable_banking_request(method, path, params=None, json_body=None):
    url = f"{ENABLE_BANKING_BASE_URL}{path}"
    headers = {
        "Authorization": f"Bearer {make_enable_banking_token()}",
        "Accept": "application/json",
        **psu_headers(),
    }
    if json_body is not None:
        headers["Content-Type"] = "application/json"
    try:
        response = requests.request(method.upper(), url, params=params, json=json_body, headers=headers, timeout=45)
    except requests.RequestException as exc:
        raise BankIntegrationError("Connessione al provider Postepay non riuscita.", 503) from exc

    content_type = response.headers.get("content-type", "")
    data = {}
    if "application/json" in content_type:
        try:
            data = response.json()
        except ValueError:
            data = {}
    if response.ok:
        return data

    message = (
        data.get("message")
        or data.get("error")
        or data.get("error_description")
        or data.get("detail")
        or "Richiesta bancaria non riuscita."
    )
    if response.status_code in {401, 403, 404, 409}:
        message = f"{message} Ricollega la carta se necessario."
    raise BankIntegrationError(message, response.status_code)


def find_postepay_aspsp(force_refresh=False):
    cache_key = f"{ENABLE_BANKING_COUNTRY}:{ENABLE_BANKING_ASPSP_NAME}:{ENABLE_BANKING_ASPSP_MATCH}"
    if not force_refresh and aspsp_cache.get(cache_key):
        return clone_payload(aspsp_cache[cache_key])

    payload = enable_banking_request("GET", "/aspsps", params={"country": ENABLE_BANKING_COUNTRY})
    items = payload.get("aspsps") or []
    if not items:
        raise BankIntegrationError("Nessun provider bancario trovato per il mercato italiano.", 503)

    if ENABLE_BANKING_ASPSP_NAME:
        for item in items:
            if str(item.get("name") or "").strip().lower() == ENABLE_BANKING_ASPSP_NAME.lower():
                aspsp_cache[cache_key] = clone_payload(item)
                return clone_payload(item)

    keywords = [keyword.strip().lower() for keyword in ENABLE_BANKING_ASPSP_MATCH.split(",") if keyword.strip()]
    scored = []
    for item in items:
        name = str(item.get("name") or "").strip()
        lower_name = name.lower()
        score = 0
        for index, keyword in enumerate(keywords):
            if keyword and keyword in lower_name:
                score = max(score, 100 - index)
        if score > 0:
            scored.append((score, name, item))
    if not scored:
        raise BankIntegrationError("Postepay non risulta disponibile nel provider configurato.", 503)
    scored.sort(key=lambda item: (-item[0], item[1]))
    winner = clone_payload(scored[0][2])
    aspsp_cache[cache_key] = clone_payload(winner)
    return winner


def bank_account_name(account):
    return clean_text(
        first_non_empty(
            account.get("name"),
            account.get("product"),
            account.get("cash_account_type"),
            account.get("cashAccountType"),
            "Carta Postepay",
        ),
        "Carta Postepay",
        120,
    )


def bank_account_iban(account):
    return str(
        first_non_empty(
            deep_get(account, ("account_id", "iban")),
            deep_get(account, ("accountId", "iban")),
            account.get("iban"),
            account.get("masked_pan"),
            account.get("maskedPan"),
            "",
        )
        or ""
    )


def bank_account_currency(account):
    return str(
        first_non_empty(
            account.get("currency"),
            deep_get(account, ("balance_amount", "currency")),
            "EUR",
        )
        or "EUR"
    )


def choose_postepay_account(accounts):
    valid_accounts = []
    for item in accounts or []:
        account_uid = first_non_empty(item.get("uid"), item.get("account_uid"), item.get("accountId"))
        if not account_uid:
            continue
        valid_accounts.append({**item, "uid": str(account_uid)})
    if not valid_accounts:
        return None
    preferred = [item for item in valid_accounts if "postepay" in bank_account_name(item).lower()]
    return preferred[0] if preferred else valid_accounts[0]


def money_payload_value(payload):
    if isinstance(payload, dict):
        return round(money_to_float(payload.get("amount")), 2), str(payload.get("currency") or "EUR")
    return round(money_to_float(payload), 2), "EUR"


def normalize_bank_balances(payload):
    raw_items = payload.get("balances") or []
    if not raw_items:
        return {
            "currency": "EUR",
            "current_balance": None,
            "available_balance": None,
            "booked_balance": None,
            "balance_label": "",
        }

    first_item = raw_items[0]
    first_amount, first_currency = money_payload_value(first_non_empty(first_item.get("balance_amount"), first_item.get("balanceAmount")))
    current_balance = round(first_amount, 2)
    available_balance = None
    booked_balance = None
    balance_label = str(first_item.get("name") or first_item.get("balance_type") or "")

    for item in raw_items:
        amount, currency = money_payload_value(first_non_empty(item.get("balance_amount"), item.get("balanceAmount")))
        name = str(item.get("name") or "").strip().lower()
        balance_type = str(item.get("balance_type") or item.get("balanceType") or "").strip().lower()
        if available_balance is None and ("available" in name or "available" in balance_type):
            available_balance = round(amount, 2)
        if booked_balance is None and ("booked" in name or "booked" in balance_type):
            booked_balance = round(amount, 2)
        if current_balance is None:
            current_balance = round(amount, 2)
            first_currency = currency or first_currency

    if current_balance is None:
        current_balance = available_balance if available_balance is not None else booked_balance

    return {
        "currency": first_currency or "EUR",
        "current_balance": current_balance,
        "available_balance": available_balance,
        "booked_balance": booked_balance,
        "balance_label": balance_label,
    }


def normalize_bank_transactions(payload):
    items = []
    for index, raw in enumerate(payload.get("transactions") or [], start=1):
        amount_node = first_non_empty(raw.get("transaction_amount"), raw.get("transactionAmount"), raw.get("amount"))
        amount, currency = money_payload_value(amount_node)
        indicator = str(first_non_empty(raw.get("credit_debit_indicator"), raw.get("creditDebitIndicator"), "") or "").upper()
        signed_amount = amount
        if amount > 0 and indicator in {"DBIT", "DEBIT"}:
            signed_amount = -amount
        if amount < 0:
            signed_amount = amount

        title = clean_text(
            first_non_empty(
                raw.get("remittance_information_unstructured"),
                raw.get("remittanceInformationUnstructured"),
                join_text_list(raw.get("remittance_information")),
                join_text_list(raw.get("remittanceInformation")),
                deep_get(raw, ("creditor", "name")),
                raw.get("creditor_name"),
                raw.get("creditorName"),
                deep_get(raw, ("debtor", "name")),
                raw.get("debtor_name"),
                raw.get("debtorName"),
                raw.get("additional_information"),
                raw.get("additionalInformation"),
                raw.get("reference_number"),
                raw.get("referenceNumber"),
                raw.get("entry_reference"),
                raw.get("entryReference"),
                "Movimento Postepay",
            ),
            "Movimento Postepay",
            120,
        )
        party_name = first_non_empty(
            deep_get(raw, ("creditor", "name")),
            raw.get("creditor_name"),
            raw.get("creditorName"),
            deep_get(raw, ("debtor", "name")),
            raw.get("debtor_name"),
            raw.get("debtorName"),
        )
        reference = first_non_empty(
            raw.get("transaction_id"),
            raw.get("transactionId"),
            raw.get("entry_reference"),
            raw.get("entryReference"),
            raw.get("internal_transaction_id"),
            raw.get("internalTransactionId"),
            raw.get("reference_number"),
            raw.get("referenceNumber"),
        )
        status = str(raw.get("status") or "")
        notes = " | ".join(
            [
                piece
                for piece in [
                    str(party_name or "").strip(),
                    f"Rif. {reference}" if reference else "",
                    join_text_list(raw.get("remittance_information")),
                    raw.get("note"),
                    status,
                ]
                if piece
            ]
        )
        items.append(
            {
                "id": str(reference or index),
                "external_id": str(reference or index),
                "date": normalize_bank_date(
                    first_non_empty(
                        raw.get("booking_date"),
                        raw.get("bookingDate"),
                        raw.get("booked_date"),
                        raw.get("value_date"),
                        raw.get("valueDate"),
                        raw.get("booking_date_time"),
                        raw.get("bookingDateTime"),
                        raw.get("transaction_date"),
                        raw.get("transactionDate"),
                    )
                ),
                "title": title,
                "notes": notes,
                "currency": currency or "EUR",
                "amount": round(abs(signed_amount), 2),
                "signed_amount": round(signed_amount, 2),
                "direction": "income" if signed_amount >= 0 else "expense",
                "status": status,
            }
        )
    items.sort(key=lambda item: (item["date"], item["id"]), reverse=True)
    return items


def build_bank_state_payload(bank_link, bank_snapshot):
    bank_link = bank_link or {}
    bank_snapshot = bank_snapshot or {}
    transactions = bank_snapshot.get("transactions") or []
    return {
        "configured": enable_banking_configured(),
        "provider": bank_link.get("provider") or ENABLE_BANKING_PROVIDER,
        "connected": bool(bank_link.get("account_uid")),
        "aspsp_name": bank_link.get("aspsp_name") or "Postepay Evolution",
        "account_name": bank_snapshot.get("account_name") or bank_link.get("account_name") or "Carta Postepay",
        "account_iban": bank_snapshot.get("account_iban") or bank_link.get("account_iban") or "",
        "currency": bank_snapshot.get("currency") or bank_link.get("account_currency") or "EUR",
        "current_balance": bank_snapshot.get("current_balance"),
        "available_balance": bank_snapshot.get("available_balance"),
        "booked_balance": bank_snapshot.get("booked_balance"),
        "balance_label": bank_snapshot.get("balance_label") or "",
        "last_sync_at": bank_snapshot.get("synced_at") or "",
        "transaction_count": int(bank_snapshot.get("transaction_count", len(transactions)) or 0),
        "transactions": transactions[:12],
        "access_valid_until": bank_link.get("access_valid_until") or "",
        "pending_category_count": int(bank_snapshot.get("pending_category_count", 0) or 0),
        "auto_sync_minutes": BANK_AUTO_SYNC_MINUTES,
    }


def fetch_session_details(session_id):
    session_id = str(session_id or "").strip()
    if not session_id:
        return {}
    return enable_banking_request("GET", f"/sessions/{session_id}")


def account_candidates_from_session_payload(payload):
    candidates = []
    for item in payload.get("accounts") or []:
        if isinstance(item, dict):
            account_uid = first_non_empty(item.get("uid"), item.get("account_uid"), item.get("accountId"))
            if account_uid:
                candidates.append({**item, "uid": str(account_uid)})
    for item in payload.get("accounts_data") or []:
        if isinstance(item, dict):
            account_uid = first_non_empty(item.get("uid"), item.get("account_uid"), item.get("accountId"))
            if account_uid:
                candidates.append({"uid": str(account_uid)})
    for item in payload.get("accounts") or []:
        if isinstance(item, str) and item.strip():
            try:
                details = enable_banking_request("GET", f"/accounts/{item}/details")
            except BankIntegrationError:
                continue
            account_uid = first_non_empty(details.get("uid"), item)
            if account_uid:
                candidates.append({**details, "uid": str(account_uid)})

    deduped = {}
    for item in candidates:
        key = str(item.get("uid") or "").strip()
        if key:
            deduped[key] = {**deduped.get(key, {}), **item}
    return list(deduped.values())


def resolve_bank_link_from_code(code, aspsp_name, access_valid_until):
    session_data = enable_banking_request("POST", "/sessions", json_body={"code": code})
    session_id = str(session_data.get("session_id") or session_data.get("uid") or session_data.get("sessionId") or "")
    if not session_id:
        raise BankIntegrationError("Il provider non ha restituito il session ID del collegamento.", 502)

    session_details = {}
    for _ in range(3):
        try:
            session_details = fetch_session_details(session_id)
        except BankIntegrationError:
            session_details = {}
        status = str(session_details.get("status") or "")
        if status in {"AUTHORIZED", "RETURNED_FROM_BANK"} or session_details.get("accounts") or session_details.get("accounts_data"):
            break
        time.sleep(1)

    accounts = account_candidates_from_session_payload(session_data)
    if session_details:
        accounts.extend(account_candidates_from_session_payload(session_details))
    account = choose_postepay_account(accounts)
    if not account:
        raise BankIntegrationError("Nessun conto Postepay disponibile da collegare.", 400)

    valid_until = first_non_empty(
        deep_get(session_details, ("access", "valid_until")),
        deep_get(session_data, ("access", "valid_until")),
        access_valid_until,
    )
    return {
        "provider": ENABLE_BANKING_PROVIDER,
        "aspsp_name": aspsp_name,
        "account_uid": str(account.get("uid") or ""),
        "account_name": bank_account_name(account),
        "account_iban": bank_account_iban(account),
        "account_currency": bank_account_currency(account),
        "session_id": session_id,
        "access_valid_until": str(valid_until or ""),
    }


def start_bank_connect_flow(user_email):
    aspsp = find_postepay_aspsp()
    flow_state = uuid.uuid4().hex
    access_valid_until = iso_utc(datetime.utcnow() + timedelta(days=ENABLE_BANKING_CONSENT_DAYS))
    payload = {
        "access": {"valid_until": access_valid_until},
        "aspsp": {
            "name": aspsp.get("name"),
            "country": aspsp.get("country") or ENABLE_BANKING_COUNTRY,
        },
        "state": flow_state,
        "redirect_url": request.host_url.rstrip("/") + url_for("auth_enable_banking_callback"),
        "psu_type": "personal",
    }
    response = enable_banking_request("POST", "/auth", json_body=payload)
    redirect_url = str(first_non_empty(response.get("url"), response.get("redirect_url"), "") or "")
    if not redirect_url:
        raise BankIntegrationError("Il provider bancario non ha restituito l'URL di autorizzazione.", 502)
    store.save_bank_auth_flow(
        flow_state,
        {
            "user_email": normalize_email(user_email),
            "aspsp_name": str(aspsp.get("name") or "Postepay Evolution"),
            "access_valid_until": access_valid_until,
        },
    )
    session["enable_banking_state"] = flow_state
    session["enable_banking_user_email"] = normalize_email(user_email)
    session["enable_banking_aspsp_name"] = str(aspsp.get("name") or "Postepay Evolution")
    session["enable_banking_access_valid_until"] = access_valid_until
    return {"redirect_url": redirect_url, "aspsp_name": session["enable_banking_aspsp_name"]}


def sync_bank_snapshot(email):
    if not enable_banking_configured():
        raise BankIntegrationError("Configura Enable Banking prima di collegare Postepay.", 503)
    bank_link = store.get_bank_link(email)
    if not bank_link or not bank_link.get("account_uid"):
        raise BankIntegrationError("Collega prima la tua Postepay Evolution.", 400)
    if bank_link.get("session_id"):
        try:
            session_info = fetch_session_details(bank_link.get("session_id"))
            status = str(session_info.get("status") or "")
            if status and status not in {"AUTHORIZED", "RETURNED_FROM_BANK"}:
                raise BankIntegrationError("Il consenso Postepay non e piu attivo. Ricollega la carta.", 409)
        except BankIntegrationError:
            raise

    account_uid = bank_link["account_uid"]
    balances_payload = enable_banking_request("GET", f"/accounts/{account_uid}/balances")
    date_from = (date.today() - timedelta(days=ENABLE_BANKING_TX_DAYS)).isoformat()
    base_params = {
        "date_from": date_from,
        "date_to": date.today().isoformat(),
    }
    raw_transactions = []
    continuation_key = None
    for _ in range(24):
        params = dict(base_params)
        if continuation_key:
            params["continuation_key"] = continuation_key
        page = enable_banking_request("GET", f"/accounts/{account_uid}/transactions", params=params)
        raw_transactions.extend(page.get("transactions") or [])
        continuation_key = page.get("continuation_key")
        if not continuation_key:
            break

    balances = normalize_bank_balances(balances_payload)
    transactions = normalize_bank_transactions({"transactions": raw_transactions})
    imported_stats = {"imported": 0, "updated": 0, "pending_category": 0}
    with lock:
        imported_stats = store.sync_bank_transactions(email, transactions)
    snapshot = {
        "account_name": bank_link.get("account_name") or "Carta Postepay",
        "account_iban": bank_link.get("account_iban") or "",
        "currency": balances.get("currency") or bank_link.get("account_currency") or "EUR",
        "current_balance": balances.get("current_balance"),
        "available_balance": balances.get("available_balance"),
        "booked_balance": balances.get("booked_balance"),
        "balance_label": balances.get("balance_label") or "",
        "transaction_count": len(transactions),
        "transactions": transactions[:60],
        "synced_at": datetime.now().isoformat(timespec="seconds"),
        "date_from": date_from,
        "date_to": date.today().isoformat(),
        "pending_category_count": imported_stats["pending_category"],
        "imported_count": imported_stats["imported"],
        "updated_count": imported_stats["updated"],
    }
    with lock:
        store.save_bank_snapshot(email, snapshot)
    invalidate_state_cache(email)
    return build_bank_state_payload(store.get_bank_link(email), snapshot)


def clear_bank_flow_session():
    flow_state = str(session.get("enable_banking_state") or "")
    for key in [
        "enable_banking_state",
        "enable_banking_user_email",
        "enable_banking_aspsp_name",
        "enable_banking_access_valid_until",
    ]:
        session.pop(key, None)
    return flow_state


def bank_redirect_response(status, message="", auto_sync=False):
    query = {"bank_status": status}
    if message:
        query["bank_message"] = str(message)
    if auto_sync:
        query["bank_autosync"] = "1"
    return redirect(f"{url_for('index')}?{urlencode(query)}")


def session_user_payload(user):
    if not user:
        return None
    return {
        "email": normalize_email(user.get("email")),
        "name": clean_text(user.get("name"), normalize_email(user.get("email")), 80),
        "picture": str(user.get("picture") or ""),
        "created_at": str(user.get("created_at") or ""),
        "last_login": str(user.get("last_login") or ""),
    }


def set_session_user(user):
    payload = session_user_payload(user)
    if not payload:
        return
    session["user_email"] = payload["email"]
    session["user_name"] = payload["name"]
    session["user_picture"] = payload["picture"]
    session["user_created_at"] = payload["created_at"]
    session["user_last_login"] = payload["last_login"]
    session.permanent = True


def get_user_from_session():
    email = normalize_email(session.get("user_email"))
    if not email:
        return None
    if session.get("user_name") is not None:
        return {
            "email": email,
            "name": clean_text(session.get("user_name"), email, 80),
            "picture": str(session.get("user_picture") or ""),
            "created_at": str(session.get("user_created_at") or ""),
            "last_login": str(session.get("user_last_login") or ""),
        }
    user = store.get_user(email)
    if not user:
        session.clear()
        return None
    set_session_user(user)
    return user


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        user = get_user_from_session()
        if not user:
            return jsonify({"ok": False, "message": "Login richiesto.", "error_code": "LOGIN_REQUIRED"}), 401
        g.current_user = user
        return fn(*args, **kwargs)

    return wrapped


@app.get("/manifest.webmanifest")
def manifest_webmanifest():
    icon = get_pwa_icon_descriptor()
    icon_src = f"/app-icon?v={pwa_icon_cache_tag(icon)}" if icon.get("is_custom") else versioned_asset("/pwa-icon.svg")
    manifest = {
        "name": APP_NAME,
        "short_name": SHORT_NAME,
        "description": "Traccia spese, entrate e categorie personalizzate in una PWA semplice e curata.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": pwa_color(BG_COLOR, "#f7f1e8"),
        "theme_color": pwa_color(THEME_COLOR, "#1f7a6f"),
        "icons": [
            {
                "src": icon_src,
                "sizes": icon["sizes"],
                "type": icon["type"],
                "purpose": icon["purpose"],
            }
        ],
    }
    return Response(json.dumps(manifest, ensure_ascii=False), mimetype="application/manifest+json")


@app.get("/service-worker.js")
def service_worker():
    icon = get_pwa_icon_descriptor()
    icon_url = f"/app-icon?v={pwa_icon_cache_tag(icon)}" if icon.get("is_custom") else versioned_asset("/pwa-icon.svg")
    script = """
const CACHE_NAME = "spese-mixet-__ASSET_VERSION__";
const APP_SHELL = [
  "/",
  "/manifest.webmanifest?v=__ASSET_VERSION__",
  "__ICON_URL__",
  "/static/styles.css?v=__ASSET_VERSION__",
  "/static/app.js?v=__ASSET_VERSION__"
];

function isDynamicRequest(url) {
  return url.pathname.startsWith("/api/") || url.pathname.startsWith("/auth/");
}

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);

  if (isDynamicRequest(url)) {
    event.respondWith(fetch(event.request, { cache: "no-store" }));
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request)
        .then((response) => {
          if (!response || response.status !== 200 || response.type !== "basic") return response;
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          return response;
        })
        .catch(() => caches.match("/"));
    })
  );
});
""".strip()
    script = script.replace("__ASSET_VERSION__", ASSET_VERSION)
    script = script.replace("__ICON_URL__", icon_url)
    return Response(script, mimetype="application/javascript", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/app-icon")
def app_icon():
    icon = get_pwa_icon_descriptor()
    if icon.get("is_custom") and icon.get("full_path"):
        return send_file(icon["full_path"], mimetype=icon["type"], max_age=300)
    return pwa_icon()


@app.get("/apple-touch-icon.png")
def apple_touch_icon():
    icon = get_pwa_icon_descriptor()
    if icon.get("is_custom") and icon.get("full_path"):
        return send_file(icon["full_path"], mimetype=icon["type"], max_age=300)
    return pwa_icon()


@app.get("/pwa-icon.svg")
def pwa_icon():
    label = escape(pwa_label(ICON_TEXT))
    start = escape(pwa_color(THEME_COLOR, "#1f7a6f"))
    accent = "#e4845c"
    bg = escape(pwa_color(BG_COLOR, "#f7f1e8"))
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
<defs>
  <linearGradient id="mix" x1="0%" y1="0%" x2="100%" y2="100%">
    <stop offset="0%" stop-color="{start}"/>
    <stop offset="100%" stop-color="{accent}"/>
  </linearGradient>
</defs>
<rect width="512" height="512" rx="128" fill="{bg}"/>
<rect x="46" y="46" width="420" height="420" rx="104" fill="#15322f"/>
<circle cx="386" cy="122" r="68" fill="url(#mix)" opacity="0.92"/>
<path d="M120 154h272c20 0 36 16 36 36v132c0 20-16 36-36 36H120c-20 0-36-16-36-36V190c0-20 16-36 36-36Z" fill="url(#mix)"/>
<path d="M122 212h268" stroke="#15322f" stroke-width="22" stroke-linecap="round" opacity="0.22"/>
<text x="256" y="314" text-anchor="middle" font-family="Georgia, 'Times New Roman', serif" font-size="150" font-weight="700" fill="white">{label}</text>
</svg>"""
    return Response(svg, mimetype="image/svg+xml")


@app.get("/")
def index():
    today = date.today()
    icon = get_pwa_icon_descriptor()
    icon_tag = pwa_icon_cache_tag(icon)
    icon_href = f"/app-icon?v={icon_tag}" if icon.get("is_custom") else versioned_asset("/pwa-icon.svg")
    apple_icon_href = f"/apple-touch-icon.png?v={icon_tag}" if icon.get("is_custom") else versioned_asset("/pwa-icon.svg")
    return render_template(
        "index.html",
        today_date=today.strftime("%Y-%m-%d"),
        current_month=today.strftime("%Y-%m"),
        google_client_id=GOOGLE_CLIENT_ID,
        pwa_app_name=APP_NAME,
        pwa_short_name=SHORT_NAME,
        pwa_theme_color=pwa_color(THEME_COLOR, "#1f7a6f"),
        pwa_icon_href=icon_href,
        pwa_apple_icon_href=apple_icon_href,
        asset_version=ASSET_VERSION,
    )


@app.get("/api/me")
def api_me():
    user = get_user_from_session()
    return jsonify(
        {
            "ok": True,
            "logged_in": bool(user),
            "google_enabled": bool(GOOGLE_CLIENT_ID),
            "user": user,
        }
    )


@app.post("/auth/google")
def auth_google():
    payload = request.get_json(silent=True) or {}
    credential = str(payload.get("credential", "")).strip()
    if not credential:
        return jsonify({"ok": False, "message": "Token Google mancante."}), 400
    if not GOOGLE_CLIENT_ID:
        return jsonify({"ok": False, "message": "GOOGLE_CLIENT_ID non configurato lato server."}), 400

    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token
    except Exception as exc:
        return jsonify({"ok": False, "message": f"Dipendenze Google mancanti ({exc})."}), 500

    try:
        info = id_token.verify_oauth2_token(credential, google_requests.Request(), GOOGLE_CLIENT_ID)
    except Exception:
        return jsonify({"ok": False, "message": "Token Google non valido."}), 401

    email = normalize_email(info.get("email"))
    if not email or not info.get("email_verified", False):
        return jsonify({"ok": False, "message": "Email Google non verificata."}), 401

    name = clean_text(info.get("name"), email, 80)
    picture = str(info.get("picture") or "")
    with lock:
        user = store.ensure_user(email, name, picture)
    set_session_user(user)
    return jsonify({"ok": True, "user": user})


@app.post("/auth/dev-login")
def auth_dev_login():
    if GOOGLE_CLIENT_ID:
        return jsonify({"ok": False, "message": "Dev login disabilitato quando Google e configurato."}), 403
    payload = request.get_json(silent=True) or {}
    email = normalize_email(payload.get("email"))
    name = clean_text(payload.get("name"), email, 80)
    if not email:
        return jsonify({"ok": False, "message": "Email obbligatoria."}), 400
    with lock:
        user = store.ensure_user(email, name, "")
    set_session_user(user)
    return jsonify({"ok": True, "user": user})


@app.post("/auth/logout")
def auth_logout():
    session.clear()
    return jsonify({"ok": True})


@app.post("/api/bank/connect")
@login_required
def api_bank_connect():
    try:
        payload = start_bank_connect_flow(g.current_user["email"])
    except BankIntegrationError as exc:
        return jsonify({"ok": False, "message": str(exc)}), exc.status_code
    return jsonify({"ok": True, **payload, "message": "Reindirizzamento verso l'autorizzazione Postepay."})


@app.get("/auth/enable-banking/callback")
def auth_enable_banking_callback():
    current_state = str(request.args.get("state") or "")
    flow = store.get_bank_auth_flow(current_state)
    user_email = normalize_email((flow or {}).get("user_email") or session.get("enable_banking_user_email") or session.get("user_email"))
    if not current_state or not flow or not user_email:
        clear_bank_flow_session()
        return bank_redirect_response("error", "Sessione bancaria scaduta. Riprova il collegamento.")
    if request.args.get("error"):
        message = request.args.get("error_description") or request.args.get("error") or "Autorizzazione annullata."
        clear_bank_flow_session()
        store.delete_bank_auth_flow(current_state)
        return bank_redirect_response("error", message)

    code = str(request.args.get("code") or "").strip()
    if not code:
        clear_bank_flow_session()
        store.delete_bank_auth_flow(current_state)
        return bank_redirect_response("error", "Codice di autorizzazione mancante.")

    aspsp_name = str((flow or {}).get("aspsp_name") or session.get("enable_banking_aspsp_name") or "Postepay Evolution")
    access_valid_until = str((flow or {}).get("access_valid_until") or session.get("enable_banking_access_valid_until") or "")

    try:
        bank_link = resolve_bank_link_from_code(code, aspsp_name, access_valid_until)
        with lock:
            store.save_bank_link(user_email, bank_link)
    except BankIntegrationError as exc:
        clear_bank_flow_session()
        store.delete_bank_auth_flow(current_state)
        invalidate_state_cache(user_email)
        return bank_redirect_response("error", str(exc))

    clear_bank_flow_session()
    store.delete_bank_auth_flow(current_state)
    invalidate_state_cache(user_email)
    return bank_redirect_response("connected", "Postepay collegata. Sto sincronizzando saldo e movimenti.", auto_sync=True)


@app.post("/api/bank/sync")
@login_required
def api_bank_sync():
    try:
        bank_payload = sync_bank_snapshot(g.current_user["email"])
    except BankIntegrationError as exc:
        return jsonify({"ok": False, "message": str(exc)}), exc.status_code
    pending_count = int(bank_payload.get("pending_category_count", 0) or 0)
    message = "Saldo e movimenti Postepay aggiornati."
    if pending_count > 0:
        message = f"Saldo aggiornato e {pending_count} movimenti sono pronti da catalogare."
    return jsonify({"ok": True, "bank": bank_payload, "message": message})


@app.post("/api/bank/disconnect")
@login_required
def api_bank_disconnect():
    with lock:
        store.clear_bank_data(g.current_user["email"])
    invalidate_state_cache(g.current_user["email"])
    clear_bank_flow_session()
    return jsonify({"ok": True, "message": "Collegamento Postepay rimosso."})


@app.get("/api/state")
@login_required
def api_state():
    try:
        month_value = request.args.get("month", "")
        profile_mode = request.args.get("profile_mode", "month")
        cycle_day = request.args.get("cycle_day", "25")
        with lock:
            payload = store.build_state(g.current_user["email"], month_value, profile_mode=profile_mode, cycle_day=cycle_day)
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    return jsonify({"ok": True, **payload})


@app.post("/api/categories")
@login_required
def api_create_category():
    payload = request.get_json(silent=True) or {}
    try:
        with lock:
            category = store.save_category(g.current_user["email"], payload, category_id=None)
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    invalidate_state_cache(g.current_user["email"])
    return jsonify({"ok": True, "category": category, "message": "Categoria creata."})


@app.put("/api/categories/<int:category_id>")
@login_required
def api_update_category(category_id):
    payload = request.get_json(silent=True) or {}
    try:
        with lock:
            category = store.save_category(g.current_user["email"], payload, category_id=category_id)
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    except KeyError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 404
    invalidate_state_cache(g.current_user["email"])
    return jsonify({"ok": True, "category": category, "message": "Categoria aggiornata."})


@app.delete("/api/categories/<int:category_id>")
@login_required
def api_delete_category(category_id):
    try:
        with lock:
            result = store.delete_category(g.current_user["email"], category_id)
    except KeyError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 404
    invalidate_state_cache(g.current_user["email"])
    return jsonify({"ok": True, **result})


@app.post("/api/entries")
@login_required
def api_create_entry():
    payload = request.get_json(silent=True) or {}
    try:
        with lock:
            entry = store.save_entry(g.current_user["email"], payload, entry_id=None)
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    invalidate_state_cache(g.current_user["email"])
    return jsonify({"ok": True, "entry": entry, "message": "Movimento salvato."})


@app.put("/api/entries/<int:entry_id>")
@login_required
def api_update_entry(entry_id):
    payload = request.get_json(silent=True) or {}
    try:
        with lock:
            entry = store.save_entry(g.current_user["email"], payload, entry_id=entry_id)
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    except KeyError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 404
    invalidate_state_cache(g.current_user["email"])
    return jsonify({"ok": True, "entry": entry, "message": "Movimento aggiornato."})


@app.delete("/api/entries/<int:entry_id>")
@login_required
def api_delete_entry(entry_id):
    try:
        with lock:
            store.delete_entry(g.current_user["email"], entry_id)
    except KeyError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 404
    invalidate_state_cache(g.current_user["email"])
    return jsonify({"ok": True, "message": "Movimento eliminato."})


@app.get("/api/export.csv")
@login_required
def api_export_csv():
    try:
        profile_mode = request.args.get("profile_mode", "month")
        cycle_day = request.args.get("cycle_day", "25")
        with lock:
            month_value, raw = store.export_csv(
                g.current_user["email"],
                request.args.get("month", ""),
                profile_mode=profile_mode,
                cycle_day=cycle_day,
            )
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    return send_file(
        io.BytesIO(raw),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"spese_mixet_{month_value}.csv",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=APP_PORT, debug=True)
