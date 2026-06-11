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



def _ensure_column(cursor, table_name, column_name, column_definition):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]

    if column_name not in columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")

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
        CREATE TABLE IF NOT EXISTS request_apps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app_name TEXT NOT NULL,
            app_type TEXT NOT NULL,
            app_url TEXT NOT NULL,
            api_key TEXT NOT NULL,
            version TEXT,
            connected INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS downloaders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            downloader_name TEXT NOT NULL,
            downloader_type TEXT NOT NULL,
            downloader_url TEXT NOT NULL,
            api_key TEXT NOT NULL,
            username TEXT,
            password TEXT,
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
        CREATE TABLE IF NOT EXISTS lifecycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            media_type TEXT,
            title TEXT NOT NULL,
            normalized_title TEXT NOT NULL,
            tmdb_id TEXT,
            tvdb_id TEXT,
            imdb_id TEXT,
            quality_profile TEXT,
            poster_url TEXT,
            created_by TEXT,
            source_app TEXT,
            source_type TEXT,
            status TEXT DEFAULT 'created'
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS lifecycle_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lifecycle_id INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            stage TEXT NOT NULL,
            status TEXT NOT NULL,
            source_name TEXT,
            source_type TEXT,
            title TEXT,
            details TEXT,
            activity_id INTEGER,
            FOREIGN KEY(lifecycle_id) REFERENCES lifecycles(id) ON DELETE CASCADE
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS sync_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            lifecycle_id INTEGER,
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
    _add_column_if_missing(c, "request_apps", "sort_order", "INTEGER DEFAULT 0")
    _add_column_if_missing(c, "downloaders", "sort_order", "INTEGER DEFAULT 0")
    _add_column_if_missing(c, "downloaders", "username", "TEXT")
    _add_column_if_missing(c, "downloaders", "password", "TEXT")
    _add_column_if_missing(c, "sync_activity", "lifecycle_id", "INTEGER")
    _add_column_if_missing(c, "lifecycles", "quality_profile", "TEXT")
    _add_column_if_missing(c, "lifecycles", "poster_url", "TEXT")
    _add_column_if_missing(c, "lifecycles", "imdb_id", "TEXT")
    for key, value in DEFAULT_SETTINGS.items():
        c.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", (key, value))
    c.execute("SELECT id, sort_order FROM sources ORDER BY id ASC")
    for index, row in enumerate(c.fetchall(), start=1):
        if not row["sort_order"]:
            c.execute("UPDATE sources SET sort_order = ? WHERE id = ?", (index, row["id"]))

    c.execute("SELECT id, sort_order FROM request_apps ORDER BY id ASC")
    for index, row in enumerate(c.fetchall(), start=1):
        if not row["sort_order"]:
            c.execute("UPDATE request_apps SET sort_order = ? WHERE id = ?", (index, row["id"]))

    c.execute("SELECT id, sort_order FROM downloaders ORDER BY id ASC")
    for index, row in enumerate(c.fetchall(), start=1):
        if not row["sort_order"]:
            c.execute("UPDATE downloaders SET sort_order = ? WHERE id = ?", (index, row["id"]))

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



def save_request_app(app_name, app_type, app_url, api_key, version="", connected=1, request_app_id=None):
    conn = get_connection()
    c = conn.cursor()

    if request_app_id:
        c.execute("""
            UPDATE request_apps SET app_name = ?, app_type = ?, app_url = ?,
                api_key = ?, version = ?, connected = ?
            WHERE id = ?
        """, (
            app_name, app_type, app_url, api_key, version, connected, request_app_id
        ))
        saved_request_app_id = int(request_app_id)
    else:
        c.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM request_apps")
        next_order = c.fetchone()[0]
        c.execute("""
            INSERT INTO request_apps (
                app_name, app_type, app_url, api_key, version, connected, sort_order
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            app_name, app_type, app_url, api_key, version, connected, next_order
        ))
        saved_request_app_id = c.lastrowid

    conn.commit()
    conn.close()

    return saved_request_app_id


def get_request_app(request_app_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM request_apps WHERE id = ?", (request_app_id,))
    row = c.fetchone()
    conn.close()

    return dict(row) if row else None


def get_request_apps():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM request_apps ORDER BY sort_order ASC, id ASC")
    rows = [dict(row) for row in c.fetchall()]
    conn.close()

    return rows


def update_request_app_config(request_app_id, app_name, app_url, api_key, version="", connected=1):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE request_apps SET app_name = ?, app_url = ?, api_key = ?,
            version = ?, connected = ?
        WHERE id = ?
    """, (
        app_name, app_url, api_key, version, connected, request_app_id
    ))
    conn.commit()
    conn.close()


def delete_request_app(request_app_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM request_apps WHERE id = ?", (request_app_id,))
    conn.commit()
    conn.close()


def reorder_request_apps(request_app_ids):
    conn = get_connection()
    c = conn.cursor()

    for index, request_app_id in enumerate(request_app_ids, start=1):
        c.execute(
            "UPDATE request_apps SET sort_order = ? WHERE id = ?",
            (index, request_app_id),
        )

    conn.commit()
    conn.close()


def save_downloader(
    downloader_name,
    downloader_type,
    downloader_url,
    api_key,
    username="",
    password="",
    version="",
    connected=1,
    downloader_id=None,
):
    conn = get_connection()
    c = conn.cursor()

    if downloader_id:
        c.execute("""
            UPDATE downloaders SET downloader_name = ?, downloader_type = ?,
                downloader_url = ?, api_key = ?, username = ?, password = ?,
                version = ?, connected = ?
            WHERE id = ?
        """, (
            downloader_name,
            downloader_type,
            downloader_url,
            api_key,
            username,
            password,
            version,
            connected,
            downloader_id,
        ))
        saved_downloader_id = int(downloader_id)
    else:
        c.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM downloaders")
        next_order = c.fetchone()[0]
        c.execute("""
            INSERT INTO downloaders (
                downloader_name, downloader_type, downloader_url, api_key,
                username, password, version, connected, sort_order
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            downloader_name,
            downloader_type,
            downloader_url,
            api_key,
            username,
            password,
            version,
            connected,
            next_order,
        ))
        saved_downloader_id = c.lastrowid

    conn.commit()
    conn.close()

    return saved_downloader_id


def get_downloader(downloader_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM downloaders WHERE id = ?", (downloader_id,))
    row = c.fetchone()
    conn.close()

    return dict(row) if row else None


def get_downloaders():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM downloaders ORDER BY sort_order ASC, id ASC")
    rows = [dict(row) for row in c.fetchall()]
    conn.close()

    return rows


def update_downloader_config(
    downloader_id,
    downloader_name,
    downloader_url,
    api_key,
    username="",
    password="",
    version="",
    connected=1,
):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE downloaders SET downloader_name = ?, downloader_url = ?,
            api_key = ?, username = ?, password = ?, version = ?, connected = ?
        WHERE id = ?
    """, (
        downloader_name,
        downloader_url,
        api_key,
        username,
        password,
        version,
        connected,
        downloader_id,
    ))
    conn.commit()
    conn.close()


def delete_downloader(downloader_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM downloaders WHERE id = ?", (downloader_id,))
    conn.commit()
    conn.close()


def reorder_downloaders(downloader_ids):
    conn = get_connection()
    c = conn.cursor()

    for index, downloader_id in enumerate(downloader_ids, start=1):
        c.execute(
            "UPDATE downloaders SET sort_order = ? WHERE id = ?",
            (index, downloader_id),
        )

    conn.commit()
    conn.close()

def add_activity_event(event_type, status, source_id=None, source_name=None, source_type=None,
                       library_id=None, library_name=None, media_title=None,
                       file_name=None, file_path=None, details=None, lifecycle_id=None,
                       lifecycle_stage=None):
    file_name = _normalize_activity_file_name(file_name, file_path)

    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO sync_activity (
            lifecycle_id, source_id, source_name, source_type, library_id, library_name,
            event_type, status, media_title, file_name, file_path, details
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        lifecycle_id, source_id, source_name, source_type, library_id, library_name,
        event_type, status, media_title, file_name, file_path, details
    ))

    event_id = c.lastrowid

    if lifecycle_id:
        _add_lifecycle_event_with_cursor(
            c,
            lifecycle_id=lifecycle_id,
            stage=lifecycle_stage or event_type,
            status=status,
            source_name=source_name,
            source_type=source_type,
            title=media_title or event_type,
            details=details,
            activity_id=event_id,
        )

    conn.commit()

    c.execute("SELECT * FROM sync_activity WHERE id = ?", (event_id,))
    row = c.fetchone()
    event = dict(row) if row else None

    feed_event = _get_activity_feed_event_for_lifecycle(c, lifecycle_id) if lifecycle_id else None

    conn.close()

    if feed_event:
        _broadcast_activity_event(feed_event)

    return _format_activity_event(event)


def _normalize_stage_key(value):
    normalized = "".join(
        character.lower() if character.isalnum() else " "
        for character in str(value or "")
    )
    return "_".join(normalized.split())


def _source_label(source_type, source_name=None):
    explicit_name = str(source_name or "").strip()

    if explicit_name:
        return explicit_name

    normalized_type = str(source_type or "").strip().lower()

    labels = {
        "radarr": "Radarr",
        "sonarr": "Sonarr",
        "seerr": "Seerr",
        "jellyseerr": "Jellyseerr",
        "sab": "SABnzbd",
        "sabnzbd": "SABnzbd",
        "emby": "Emby",
        "jellyfin": "Jellyfin",
        "plex": "Plex",
        "mediasync": "MediaSync",
    }

    return labels.get(normalized_type, explicit_name or "MediaSync")


def _arr_label_from_event_or_lifecycle(event_row, lifecycle_row):
    event_source_type = str((event_row or {}).get("source_type") or "").strip().lower()
    lifecycle_media_type = str((lifecycle_row or {}).get("media_type") or "").strip().lower()
    lifecycle_source_type = str((lifecycle_row or {}).get("source_type") or "").strip().lower()

    if event_source_type in {"radarr", "sonarr"}:
        return _source_label(event_source_type, (event_row or {}).get("source_name"))

    if lifecycle_source_type in {"radarr", "sonarr"}:
        return _source_label(lifecycle_source_type, (lifecycle_row or {}).get("source_app"))

    if lifecycle_media_type in {"tv", "show", "series", "tvshows"}:
        return "Sonarr"

    return "Radarr"


def _display_event_type_for_activity(lifecycle_row, event_row, activity_row):
    if not lifecycle_row:
        return "Activity"

    stage = str((event_row or {}).get("stage") or "").strip()
    stage_key = _normalize_stage_key(stage)

    if not stage_key:
        source_type = str(lifecycle_row.get("source_type") or "").strip().lower()

        if source_type in {"radarr", "sonarr"}:
            return f"Added to {_source_label(source_type, lifecycle_row.get('source_app'))}"

        return "Requested"

    if stage_key in {"requested", "request", "request_activity", "approved", "processing"}:
        return "Requested"

    if stage_key in {"grabbed", "added", "added_to_arr", "sent_to_arr"}:
        return f"Added to {_arr_label_from_event_or_lifecycle(event_row, lifecycle_row)}"

    if stage_key in {"download_started", "downloading"}:
        return "Download Started"

    if stage_key in {"download_completed", "downloaded"}:
        return "Download Completed"

    if stage_key in {"download_cancelled", "download_canceled"}:
        return "Download Cancelled"

    if stage_key == "download_failed":
        return "Download Failed"

    if stage_key in {"imported", "importing", "arr_import", "radarr_importing", "sonarr_importing"}:
        return f"{_arr_label_from_event_or_lifecycle(event_row, lifecycle_row)} Importing"

    if stage_key.startswith("library_sync") or stage_key in {"scan", "scanning", "library_scan", "library_scanned"}:
        return "Scanning"

    if stage_key in {"available", "available_in_emby", "available_in_jellyfin", "available_in_plex"}:
        source_name = str((event_row or {}).get("source_name") or "").strip()
        source_type = str((event_row or {}).get("source_type") or "").strip().lower()
        media_server_name = _source_label(source_type, source_name)

        if media_server_name and media_server_name != "MediaSync":
            return f"Available in {media_server_name}"

        return "Available"

    return stage


def _get_latest_lifecycle_event_with_activity(cursor, lifecycle_id):
    cursor.execute(
        """
        SELECT
            le.*,
            sa.id AS activity_id,
            sa.source_id AS activity_source_id,
            sa.source_name AS activity_source_name,
            sa.source_type AS activity_source_type,
            sa.library_id AS activity_library_id,
            sa.library_name AS activity_library_name,
            sa.event_type AS activity_event_type,
            sa.media_title AS activity_media_title,
            sa.file_name AS activity_file_name,
            sa.file_path AS activity_file_path,
            sa.details AS activity_details
        FROM lifecycle_events le
        LEFT JOIN sync_activity sa ON sa.id = le.activity_id
        WHERE le.lifecycle_id = ?
        ORDER BY le.id DESC
        LIMIT 1
        """,
        (lifecycle_id,),
    )

    row = cursor.fetchone()
    return dict(row) if row else None


def _get_activity_feed_event_for_lifecycle(cursor, lifecycle_id):
    cursor.execute("SELECT * FROM lifecycles WHERE id = ?", (lifecycle_id,))
    lifecycle_row = cursor.fetchone()

    if not lifecycle_row:
        return None

    lifecycle = dict(lifecycle_row)
    latest_event = _get_latest_lifecycle_event_with_activity(cursor, lifecycle_id)

    origin_source_type = str(lifecycle.get("source_type") or "").strip().lower()
    origin_source_name = _source_label(origin_source_type, lifecycle.get("source_app"))

    activity_source_id = (latest_event or {}).get("activity_source_id")
    activity_library_id = (latest_event or {}).get("activity_library_id")
    activity_library_name = (latest_event or {}).get("activity_library_name")
    file_name = (latest_event or {}).get("activity_file_name")
    file_path = (latest_event or {}).get("activity_file_path")
    details = (latest_event or {}).get("activity_details") or (latest_event or {}).get("details") or ""

    event = {
        "id": (latest_event or {}).get("activity_id") or (latest_event or {}).get("id") or lifecycle.get("id"),
        "created_at": lifecycle.get("created_at"),
        "lifecycle_id": lifecycle.get("id"),
        "source_id": activity_source_id,
        "source_name": origin_source_name,
        "source_type": origin_source_type,
        "library_id": activity_library_id,
        "library_name": activity_library_name,
        "event_type": _display_event_type_for_activity(lifecycle, latest_event, None),
        "status": (latest_event or {}).get("status") or lifecycle.get("status") or "active",
        "media_title": lifecycle.get("title"),
        "file_name": file_name,
        "file_path": file_path,
        "details": details,
        "updated_at": (latest_event or {}).get("created_at") or lifecycle.get("updated_at"),
    }

    return _format_activity_event(event)


def get_activity_events(limit=100):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        SELECT id
        FROM lifecycles
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    lifecycle_ids = [row["id"] for row in c.fetchall()]
    rows = [
        event
        for event in (_get_activity_feed_event_for_lifecycle(c, lifecycle_id) for lifecycle_id in lifecycle_ids)
        if event
    ]
    conn.close()
    return rows



def normalize_lifecycle_title(title):
    return " ".join(str(title or "").strip().lower().split())


def _lifecycle_has_events(cursor, lifecycle_id):
    cursor.execute(
        "SELECT COUNT(*) AS count FROM lifecycle_events WHERE lifecycle_id = ?",
        (lifecycle_id,),
    )
    row = cursor.fetchone()

    return bool(row and row["count"])


def _initial_lifecycle_stage_for_origin(source_type, source_app=None):
    normalized_source_type = str(source_type or "").strip().lower()

    if normalized_source_type in {"seerr", "jellyseerr"}:
        return "Requested"

    if normalized_source_type in {"radarr", "sonarr"}:
        return f"Added to {_source_label(normalized_source_type, source_app)}"

    return None


def _add_initial_lifecycle_event_for_origin(cursor, lifecycle_id, lifecycle):
    if not lifecycle_id or _lifecycle_has_events(cursor, lifecycle_id):
        return None

    source_type = str((lifecycle or {}).get("source_type") or "").strip().lower()
    source_app = (lifecycle or {}).get("source_app")
    stage = _initial_lifecycle_stage_for_origin(source_type, source_app)

    if not stage:
        return None

    return _add_lifecycle_event_with_cursor(
        cursor,
        lifecycle_id=lifecycle_id,
        stage=stage,
        status="success",
        source_name=_source_label(source_type, source_app),
        source_type=source_type,
        title=(lifecycle or {}).get("title"),
        details=(lifecycle or {}).get("quality_profile") or "",
        activity_id=None,
    )


def get_or_create_lifecycle(
    media_type=None,
    title=None,
    tmdb_id=None,
    tvdb_id=None,
    imdb_id=None,
    created_by=None,
    source_app=None,
    source_type=None,
    quality_profile=None,
    poster_url=None,
    status="created",
):
    normalized_title = normalize_lifecycle_title(title)

    if not normalized_title:
        return None

    conn = get_connection()
    c = conn.cursor()

    row = None

    if tmdb_id:
        c.execute("SELECT * FROM lifecycles WHERE tmdb_id = ? ORDER BY id DESC LIMIT 1", (str(tmdb_id),))
        row = c.fetchone()

    if not row and tvdb_id:
        c.execute("SELECT * FROM lifecycles WHERE tvdb_id = ? ORDER BY id DESC LIMIT 1", (str(tvdb_id),))
        row = c.fetchone()

    if not row:
        c.execute(
            """
            SELECT * FROM lifecycles
            WHERE normalized_title = ? AND COALESCE(media_type, '') = COALESCE(?, '')
            ORDER BY id DESC LIMIT 1
            """,
            (normalized_title, media_type),
        )
        row = c.fetchone()

    if row:
        lifecycle_id = row["id"]
        c.execute(
            """
            UPDATE lifecycles
            SET updated_at = CURRENT_TIMESTAMP,
                tmdb_id = COALESCE(NULLIF(?, ''), tmdb_id),
                tvdb_id = COALESCE(NULLIF(?, ''), tvdb_id),
                imdb_id = COALESCE(NULLIF(?, ''), imdb_id),
                quality_profile = COALESCE(NULLIF(?, ''), quality_profile),
                poster_url = COALESCE(NULLIF(?, ''), poster_url),
                created_by = COALESCE(created_by, NULLIF(?, '')),
                source_app = COALESCE(source_app, NULLIF(?, '')),
                source_type = COALESCE(source_type, NULLIF(?, '')),
                status = COALESCE(NULLIF(?, ''), status)
            WHERE id = ?
            """,
            (
                str(tmdb_id or ""),
                str(tvdb_id or ""),
                str(imdb_id or ""),
                str(quality_profile or ""),
                str(poster_url or ""),
                str(created_by or ""),
                str(source_app or ""),
                str(source_type or ""),
                str(status or ""),
                lifecycle_id,
            ),
        )
        lifecycle_for_initial = dict(row)
        lifecycle_for_initial.update({
            "title": lifecycle_for_initial.get("title") or title,
            "quality_profile": lifecycle_for_initial.get("quality_profile") or quality_profile,
            "source_app": lifecycle_for_initial.get("source_app") or source_app,
            "source_type": lifecycle_for_initial.get("source_type") or source_type,
        })
        added_initial_event = _add_initial_lifecycle_event_for_origin(c, lifecycle_id, lifecycle_for_initial)

        conn.commit()

        feed_event = _get_activity_feed_event_for_lifecycle(c, lifecycle_id) if added_initial_event else None
        conn.close()

        if feed_event:
            _broadcast_activity_event(feed_event)

        return lifecycle_id

    c.execute(
        """
        INSERT INTO lifecycles (
            media_type, title, normalized_title, tmdb_id, tvdb_id, imdb_id,
            quality_profile, poster_url, created_by, source_app, source_type, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            media_type,
            title,
            normalized_title,
            str(tmdb_id or "") or None,
            str(tvdb_id or "") or None,
            str(imdb_id or "") or None,
            quality_profile,
            poster_url,
            created_by,
            source_app,
            source_type,
            status,
        ),
    )
    lifecycle_id = c.lastrowid

    _add_initial_lifecycle_event_for_origin(
        c,
        lifecycle_id,
        {
            "title": title,
            "quality_profile": quality_profile,
            "source_app": source_app,
            "source_type": source_type,
        },
    )

    conn.commit()

    feed_event = _get_activity_feed_event_for_lifecycle(c, lifecycle_id)
    conn.close()

    if feed_event:
        _broadcast_activity_event(feed_event)

    return lifecycle_id


def update_lifecycle_status(lifecycle_id, status):
    if not lifecycle_id or not status:
        return

    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE lifecycles SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, lifecycle_id),
    )
    conn.commit()
    conn.close()


def add_lifecycle_event(lifecycle_id, stage, status="success", source_name=None, source_type=None, title=None, details=None, activity_id=None):
    if not lifecycle_id or not stage:
        return None

    conn = get_connection()
    c = conn.cursor()
    event_id = _add_lifecycle_event_with_cursor(
        c,
        lifecycle_id=lifecycle_id,
        stage=stage,
        status=status,
        source_name=source_name,
        source_type=source_type,
        title=title,
        details=details,
        activity_id=activity_id,
    )
    conn.commit()

    feed_event = _get_activity_feed_event_for_lifecycle(c, lifecycle_id)
    conn.close()

    if feed_event:
        _broadcast_activity_event(feed_event)

    return event_id


def _add_lifecycle_event_with_cursor(cursor, lifecycle_id, stage, status="success", source_name=None, source_type=None, title=None, details=None, activity_id=None):
    cursor.execute(
        """
        INSERT INTO lifecycle_events (
            lifecycle_id, stage, status, source_name, source_type, title, details, activity_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (lifecycle_id, stage, status, source_name, source_type, title, details, activity_id),
    )
    return cursor.lastrowid


def get_lifecycle(lifecycle_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM lifecycles WHERE id = ?", (lifecycle_id,))
    lifecycle_row = c.fetchone()

    if not lifecycle_row:
        conn.close()
        return None

    c.execute(
        """
        SELECT
            le.*,
            sa.source_id AS activity_source_id,
            sa.library_id AS activity_library_id,
            sa.library_name AS activity_library_name,
            sa.file_name AS activity_file_name,
            sa.file_path AS activity_file_path,
            sa.event_type AS activity_event_type,
            sa.media_title AS activity_media_title,
            slm.library_image_url AS activity_library_image_url
        FROM lifecycle_events le
        LEFT JOIN sync_activity sa ON sa.id = le.activity_id
        LEFT JOIN source_library_map slm
            ON slm.source_id = sa.source_id
            AND slm.library_id = sa.library_id
        WHERE le.lifecycle_id = ?
        ORDER BY le.id ASC
        """,
        (lifecycle_id,),
    )
    event_rows = [dict(row) for row in c.fetchall()]
    conn.close()

    return {
        "lifecycle": dict(lifecycle_row),
        "events": event_rows,
    }

def clear_activity_events():
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM lifecycle_events")
    c.execute("DELETE FROM lifecycles")
    c.execute("DELETE FROM sync_activity")
    conn.commit()
    conn.close()


def reset_configuration():
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM lifecycle_events")
    c.execute("DELETE FROM lifecycles")
    c.execute("DELETE FROM sync_activity")
    c.execute("DELETE FROM source_library_map")
    c.execute("DELETE FROM sources")
    c.execute("DELETE FROM request_apps")
    c.execute("DELETE FROM downloaders")
    c.execute("DELETE FROM media_server")
    c.execute("DELETE FROM app_settings")
    for key, value in DEFAULT_SETTINGS.items():
        c.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()
