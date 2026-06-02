import asyncio
import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DB_PATH = Path("/config/mediasync.db")

DEFAULT_SETTINGS = {
    "timezone": "America/New_York",
    "mediasync_url": "",
    "tv_poll_interval_seconds": "60",
    "tv_interim_scan_minutes": "10",
    "tv_final_scan_enabled": "1",
    "activity_display_limit": "100",
    "activity_retention_limit": "1000",
    "activity_file_detail": "filename",
}


_ACTIVITY_SUBSCRIBERS = set()
_ACTIVITY_LOOP = None


def register_activity_loop(loop):
    global _ACTIVITY_LOOP
    _ACTIVITY_LOOP = loop


def subscribe_activity_queue():
    queue = asyncio.Queue()
    _ACTIVITY_SUBSCRIBERS.add(queue)
    return queue


def unsubscribe_activity_queue(queue):
    _ACTIVITY_SUBSCRIBERS.discard(queue)


def _get_activity_timezone():
    settings = get_app_settings()
    timezone_name = settings.get("timezone", DEFAULT_SETTINGS["timezone"])

    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return ZoneInfo(DEFAULT_SETTINGS["timezone"])


def _parse_sqlite_utc_timestamp(value):
    if not value:
        return None

    raw_value = str(value).strip()

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw_value[:19], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    return None


def _format_activity_timestamp(value):
    utc_dt = _parse_sqlite_utc_timestamp(value)

    if not utc_dt:
        return value

    local_dt = utc_dt.astimezone(_get_activity_timezone())
    return local_dt.strftime("%Y-%m-%d %H:%M:%S")


def _activity_basename(value):
    if not value:
        return value

    normalized = str(value).strip().replace("\\", "/").rstrip("/")

    if not normalized:
        return value

    return normalized.split("/")[-1]


def _normalize_activity_file_name(file_name=None, file_path=None):
    if file_name:
        return _activity_basename(file_name)

    if file_path:
        return _activity_basename(file_path)

    return file_name


def _format_activity_event(event):
    if not event:
        return event

    formatted_event = dict(event)
    formatted_event["created_at"] = _format_activity_timestamp(
        formatted_event.get("created_at")
    )
    formatted_event["file_name"] = _normalize_activity_file_name(
        formatted_event.get("file_name"),
        formatted_event.get("file_path"),
    )
    return formatted_event


def _broadcast_activity_event(event):
    if not event or not _ACTIVITY_SUBSCRIBERS:
        return

    event = _format_activity_event(event)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = _ACTIVITY_LOOP

    stale_queues = []

    for queue in list(_ACTIVITY_SUBSCRIBERS):
        try:
            if loop and loop.is_running():
                loop.call_soon_threadsafe(queue.put_nowait, event)
            else:
                queue.put_nowait(event)
        except Exception:
            stale_queues.append(queue)

    for queue in stale_queues:
        _ACTIVITY_SUBSCRIBERS.discard(queue)


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS media_server (
            id INTEGER PRIMARY KEY,
            server_type TEXT,
            server_url TEXT,
            api_key TEXT,
            timezone TEXT,
            connected INTEGER DEFAULT 0,
            server_name TEXT,
            version TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_url TEXT NOT NULL,
            api_key TEXT NOT NULL,
            version TEXT,
            connected INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS source_library_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            library_id TEXT NOT NULL,
            library_name TEXT NOT NULL,
            library_type TEXT DEFAULT 'unknown',
            library_image_url TEXT,
            FOREIGN KEY(source_id) REFERENCES sources(id) ON DELETE CASCADE
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS sync_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            source_id INTEGER,
            source_name TEXT,
            source_type TEXT,
            library_id TEXT,
            library_name TEXT,
            event_type TEXT NOT NULL,
            status TEXT NOT NULL,
            media_title TEXT,
            file_name TEXT,
            file_path TEXT,
            details TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS auth_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_login_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    _add_column_if_missing(c, "source_library_map", "library_type", "TEXT DEFAULT 'unknown'")
    _add_column_if_missing(c, "source_library_map", "library_image_url", "TEXT")
    _add_column_if_missing(c, "sources", "sort_order", "INTEGER DEFAULT 0")
    for key, value in DEFAULT_SETTINGS.items():
        c.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", (key, value))
    c.execute("SELECT id, sort_order FROM sources ORDER BY id ASC")
    for index, row in enumerate(c.fetchall(), start=1):
        if not row["sort_order"]:
            c.execute("UPDATE sources SET sort_order = ? WHERE id = ?", (index, row["id"]))
    conn.commit()
    conn.close()


def _add_column_if_missing(cursor, table_name, column_name, column_definition):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row["name"] for row in cursor.fetchall()]
    if column_name not in columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")



def _hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)

    password_bytes = str(password).encode("utf-8")
    salt_bytes = salt.encode("utf-8")
    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        password_bytes,
        salt_bytes,
        260000,
    )
    return f"pbkdf2_sha256$260000${salt}${derived_key.hex()}"


def _verify_password(password, stored_hash):
    try:
        algorithm, iterations, salt, expected_hash = str(stored_hash).split("$", 3)
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    try:
        iteration_count = int(iterations)
    except ValueError:
        return False

    password_bytes = str(password).encode("utf-8")
    salt_bytes = salt.encode("utf-8")
    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        password_bytes,
        salt_bytes,
        iteration_count,
    ).hex()

    return hmac.compare_digest(derived_key, expected_hash)


def admin_exists():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM auth_users")
    count = c.fetchone()[0]
    conn.close()
    return count > 0


def create_admin_user(username, password):
    normalized_username = str(username or "").strip()
    normalized_password = str(password or "")

    if not normalized_username:
        return {"success": False, "message": "Username is required."}

    if len(normalized_password) < 8:
        return {"success": False, "message": "Password must be at least 8 characters."}

    if admin_exists():
        return {"success": False, "message": "Admin account already exists."}

    conn = get_connection()
    c = conn.cursor()

    try:
        c.execute(
            "INSERT INTO auth_users (username, password_hash) VALUES (?, ?)",
            (normalized_username, _hash_password(normalized_password)),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return {"success": False, "message": "Admin account already exists."}

    user_id = c.lastrowid
    conn.close()

    return {
        "success": True,
        "message": "Admin account created.",
        "user_id": user_id,
        "username": normalized_username,
    }


def authenticate_admin(username, password):
    normalized_username = str(username or "").strip()

    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM auth_users WHERE username = ? ORDER BY id ASC LIMIT 1",
        (normalized_username,),
    )
    row = c.fetchone()

    if not row:
        conn.close()
        return None

    user = dict(row)

    if not _verify_password(password, user.get("password_hash")):
        conn.close()
        return None

    c.execute(
        "UPDATE auth_users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?",
        (user["id"],),
    )
    conn.commit()
    conn.close()

    return {
        "id": user["id"],
        "username": user["username"],
    }


def get_admin_user(user_id):
    if not user_id:
        return None

    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, username, created_at, last_login_at FROM auth_users WHERE id = ?",
        (user_id,),
    )
    row = c.fetchone()
    conn.close()

    return dict(row) if row else None


def get_app_settings():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT key, value FROM app_settings")
    settings = DEFAULT_SETTINGS.copy()
    for row in c.fetchall():
        settings[row["key"]] = row["value"]
    conn.close()
    return settings


def save_app_settings(settings):
    conn = get_connection()
    c = conn.cursor()
    for key, value in settings.items():
        if key in DEFAULT_SETTINGS:
            c.execute("""
                INSERT INTO app_settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (key, str(value)))
    conn.commit()
    conn.close()


def get_media_server():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM media_server ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def save_media_server(server_type, server_url, api_key, timezone, connected, server_name, version):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM media_server")
    c.execute("""
        INSERT INTO media_server (
            server_type, server_url, api_key, timezone, connected, server_name, version
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (server_type, server_url, api_key, timezone, connected, server_name, version))
    c.execute("""
        INSERT INTO app_settings (key, value)
        VALUES ('timezone', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (timezone,))
    conn.commit()
    conn.close()


def update_media_server_config(server_url, api_key, timezone):
    server = get_media_server()
    if not server:
        return False
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE media_server SET server_url = ?, api_key = ?, timezone = ?
        WHERE id = ?
    """, (server_url, api_key, timezone, server["id"]))
    c.execute("""
        INSERT INTO app_settings (key, value)
        VALUES ('timezone', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (timezone,))
    conn.commit()
    conn.close()
    return True


def save_source(source_name, source_type, source_url, api_key, version, libraries, source_id=None):
    conn = get_connection()
    c = conn.cursor()
    if source_id:
        c.execute("""
            UPDATE sources SET source_name = ?, source_type = ?, source_url = ?,
                api_key = ?, version = ?, connected = 1
            WHERE id = ?
        """, (source_name, source_type, source_url, api_key, version, source_id))
        c.execute("DELETE FROM source_library_map WHERE source_id = ?", (source_id,))
        saved_source_id = int(source_id)
    else:
        c.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM sources")
        next_order = c.fetchone()[0]
        c.execute("""
            INSERT INTO sources (
                source_name, source_type, source_url, api_key, version, connected, sort_order
            )
            VALUES (?, ?, ?, ?, ?, 1, ?)
        """, (source_name, source_type, source_url, api_key, version, next_order))
        saved_source_id = c.lastrowid
    for library in libraries:
        c.execute("""
            INSERT INTO source_library_map (
                source_id, library_id, library_name, library_type, library_image_url
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            saved_source_id, library["id"], library["name"],
            library.get("type", "unknown"), library.get("image_url")
        ))
    conn.commit()
    conn.close()
    return saved_source_id


def get_source(source_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM sources WHERE id = ?", (source_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def update_source_config(source_id, source_name, source_url, api_key):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE sources SET source_name = ?, source_url = ?, api_key = ?
        WHERE id = ?
    """, (source_name, source_url, api_key, source_id))
    conn.commit()
    conn.close()


def delete_source(source_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM source_library_map WHERE source_id = ?", (source_id,))
    c.execute("DELETE FROM sources WHERE id = ?", (source_id,))
    conn.commit()
    conn.close()


def reorder_sources(source_ids):
    conn = get_connection()
    c = conn.cursor()
    for index, source_id in enumerate(source_ids, start=1):
        c.execute("UPDATE sources SET sort_order = ? WHERE id = ?", (index, source_id))
    conn.commit()
    conn.close()


def get_sources():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM sources ORDER BY sort_order ASC, id ASC")
    rows = c.fetchall()
    sources = []
    for row in rows:
        source = dict(row)
        c.execute("""
            SELECT library_id, library_name, library_type, library_image_url
            FROM source_library_map
            WHERE source_id = ?
            ORDER BY id ASC
        """, (source["id"],))
        source["libraries"] = [dict(library_row) for library_row in c.fetchall()]
        sources.append(source)
    conn.close()
    return sources


def add_activity_event(event_type, status, source_id=None, source_name=None, source_type=None,
                       library_id=None, library_name=None, media_title=None,
                       file_name=None, file_path=None, details=None):
    file_name = _normalize_activity_file_name(file_name, file_path)

    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO sync_activity (
            source_id, source_name, source_type, library_id, library_name,
            event_type, status, media_title, file_name, file_path, details
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        source_id, source_name, source_type, library_id, library_name,
        event_type, status, media_title, file_name, file_path, details
    ))

    event_id = c.lastrowid
    conn.commit()

    c.execute("SELECT * FROM sync_activity WHERE id = ?", (event_id,))
    row = c.fetchone()
    event = dict(row) if row else None

    conn.close()

    _broadcast_activity_event(event)

    return _format_activity_event(event)


def get_activity_events(limit=100):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM sync_activity ORDER BY id DESC LIMIT ?", (limit,))
    rows = [_format_activity_event(dict(row)) for row in c.fetchall()]
    conn.close()
    return rows


def clear_activity_events():
    conn = get_connection()
    conn.execute("DELETE FROM sync_activity")
    conn.commit()
    conn.close()


def reset_configuration():
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM sync_activity")
    c.execute("DELETE FROM source_library_map")
    c.execute("DELETE FROM sources")
    c.execute("DELETE FROM media_server")
    c.execute("DELETE FROM app_settings")
    for key, value in DEFAULT_SETTINGS.items():
        c.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()
