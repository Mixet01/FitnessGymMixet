import csv
import io
import json
import os
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
from html import escape
from threading import Lock

from flask import Flask, Response, g, jsonify, render_template, request, send_file, session

try:
    import psycopg
except Exception:
    psycopg = None


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
ICON_TEXT = os.environ.get("PWA_ICON_TEXT", "SM").strip() or "SM"
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
APP_PORT = int(os.environ.get("PWA_PORT", "8010"))
SESSION_DAYS = int(os.environ.get("SPESE_MIXET_SESSION_DAYS", "90"))
ASSET_VERSION = os.environ.get("SPESE_MIXET_ASSET_VERSION", "2026-05-18-v2").strip() or "2026-05-18-v2"

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

    def ensure_file_state(self):
        if not os.path.exists(self.data_file):
            self.save_file_state(self.default_file_state())

    def default_file_state(self):
        return {
            "users": {},
            "categories": {},
            "entries": {},
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
                            "category_id": row[8],
                            "category_name": row[9],
                            "category_color": row[10],
                            "category_archived": row[11],
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
                                user_email, category_id, entry_type, title, notes, amount, occurred_on, created_at, updated_at
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
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

    def build_state(self, email, selected_month):
        month_value, start_date, end_date = month_bounds(selected_month)
        entries = self.list_entries(email, start_date=start_date, end_date=end_date)
        recent_entries = self.list_entries(email, limit=6)
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

        trend_start = shift_month(start_date, -5)
        trend_entries = self.list_entries(email, start_date=trend_start, end_date=end_date)
        summary = self.build_month_summary(entries, month_value)
        trend = self.build_trend(trend_entries, start_date)
        return {
            "month": month_value,
            "month_label": month_label(month_value),
            "storage_mode": "database" if DB_MODE else "file",
            "categories": categories_out,
            "entries": entries,
            "recent_entries": recent_entries,
            "summary": summary,
            "trend": trend,
        }

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

    def export_csv(self, email, selected_month):
        month_value, start_date, end_date = month_bounds(selected_month)
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
        return month_value, raw


store = ExpenseStore(DATA_FILE)


def get_user_from_session():
    email = normalize_email(session.get("user_email"))
    if not email:
        return None
    user = store.get_user(email)
    if not user:
        session.pop("user_email", None)
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
                "src": versioned_asset("/pwa-icon.svg"),
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any maskable",
            }
        ],
    }
    return Response(json.dumps(manifest, ensure_ascii=False), mimetype="application/manifest+json")


@app.get("/service-worker.js")
def service_worker():
    script = """
const CACHE_NAME = "spese-mixet-v2";
const APP_SHELL = [
  "/",
  "/manifest.webmanifest?v=2026-05-18-v2",
  "/pwa-icon.svg?v=2026-05-18-v2",
  "/static/styles.css?v=2026-05-18-v2",
  "/static/app.js?v=2026-05-18-v2"
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
    return Response(script, mimetype="application/javascript", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


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
    return render_template(
        "index.html",
        today_date=today.strftime("%Y-%m-%d"),
        current_month=today.strftime("%Y-%m"),
        google_client_id=GOOGLE_CLIENT_ID,
        pwa_app_name=APP_NAME,
        pwa_short_name=SHORT_NAME,
        pwa_theme_color=pwa_color(THEME_COLOR, "#1f7a6f"),
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
    session["user_email"] = email
    session.permanent = True
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
    session["user_email"] = email
    session.permanent = True
    return jsonify({"ok": True, "user": user})


@app.post("/auth/logout")
def auth_logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/state")
@login_required
def api_state():
    try:
        month_value = request.args.get("month", "")
        with lock:
            payload = store.build_state(g.current_user["email"], month_value)
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
    return jsonify({"ok": True, "category": category, "message": "Categoria aggiornata."})


@app.delete("/api/categories/<int:category_id>")
@login_required
def api_delete_category(category_id):
    try:
        with lock:
            result = store.delete_category(g.current_user["email"], category_id)
    except KeyError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 404
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
    return jsonify({"ok": True, "entry": entry, "message": "Movimento aggiornato."})


@app.delete("/api/entries/<int:entry_id>")
@login_required
def api_delete_entry(entry_id):
    try:
        with lock:
            store.delete_entry(g.current_user["email"], entry_id)
    except KeyError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 404
    return jsonify({"ok": True, "message": "Movimento eliminato."})


@app.get("/api/export.csv")
@login_required
def api_export_csv():
    try:
        with lock:
            month_value, raw = store.export_csv(g.current_user["email"], request.args.get("month", ""))
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
