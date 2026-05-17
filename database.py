import json
import hashlib
import hmac
import os
import re
import sqlite3
import threading
from datetime import date, datetime, timedelta
from functools import lru_cache

DB_FILE = "users.db"
PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 260000
_cache_lock = threading.Lock()
_cached_data = {}
_schema_lock = threading.Lock()
_schema_ready = False

DEFAULT_USER_PREFERENCES = {
    "appearance_mode": "light",
    "theme_name": "green",
    "custom_accent": "#2f9e99",
    "notifications_enabled": True,
    "study_reminders_enabled": True,
    "sound_effects_enabled": True,
    "default_study_duration": 50,
    "font_size": 14,
    "auto_save_enabled": True,
}


def get_connection():
    conn = sqlite3.connect(DB_FILE, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _normalize_identifier(value):
    return (value or "").strip()


def _normalize_email(value):
    return _normalize_identifier(value).lower()


def _validate_email(value):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", _normalize_email(value)))


def _validate_username(value):
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", _normalize_identifier(value)))


def _hash_password(password):
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), PASSWORD_ITERATIONS).hex()
    return f"{PASSWORD_SCHEME}${PASSWORD_ITERATIONS}${salt}${digest}"


def _is_password_hash(value):
    return isinstance(value, str) and value.startswith(f"{PASSWORD_SCHEME}$")


def _verify_password(password, stored):
    if not stored:
        return False
    if not _is_password_hash(stored):
        return hmac.compare_digest(str(stored), password)
    try:
        scheme, iterations, salt, expected = stored.split("$", 3)
        if scheme != PASSWORD_SCHEME:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), int(iterations)).hex()
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)


def _upgrade_password_hash(user_id, password):
    conn = get_connection()
    try:
        conn.execute("UPDATE users SET password = ? WHERE id = ?", (_hash_password(password), user_id))
        conn.commit()
    finally:
        conn.close()


def _ensure_column(cursor, table, column, column_type):
    cursor.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in cursor.fetchall()}
    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def connect():
    global _schema_ready
    # Schema creation and PRAGMA checks are relatively expensive on Windows/OneDrive.
    # Guarding them makes normal read queries cheap after the first startup pass.
    if _schema_ready:
        return

    with _schema_lock:
        if _schema_ready:
            return

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                subject TEXT NOT NULL,
                due_date TEXT,
                study_date TEXT,
                study_hours REAL NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'pending',
                notes TEXT,
                notes_path TEXT,
                study_plan TEXT,
                priority TEXT NOT NULL DEFAULT 'Medium',
                reminder_lead_minutes INTEGER NOT NULL DEFAULT 30,
                reminder_start_hour INTEGER,
                reminder_end_hour INTEGER,
                reminder_interval_minutes INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS study_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subject TEXT,
                topic TEXT,
                study_minutes INTEGER NOT NULL,
                understanding_rating INTEGER,
                completion_status TEXT NOT NULL DEFAULT 'completed',
                break_interval INTEGER,
                break_minutes INTEGER,
                session_date TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS xp_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                points INTEGER NOT NULL,
                reason TEXT NOT NULL,
                source_type TEXT,
                source_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                badge_key TEXT NOT NULL,
                badge_name TEXT NOT NULL,
                description TEXT,
                unlocked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, badge_key),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                reminder_start_hour INTEGER NOT NULL DEFAULT 18,
                reminder_end_hour INTEGER NOT NULL DEFAULT 24,
                reminder_interval_minutes INTEGER NOT NULL DEFAULT 60,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                attendance_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'present',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, attendance_date),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS attendance_settings (
                user_id INTEGER PRIMARY KEY,
                leave_weekday INTEGER NOT NULL DEFAULT 6,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS app_preferences (
                user_id INTEGER PRIMARY KEY,
                settings_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )

        _ensure_column(cursor, "tasks", "notes_path", "TEXT")
        _ensure_column(cursor, "tasks", "study_plan", "TEXT")
        _ensure_column(cursor, "tasks", "priority", "TEXT NOT NULL DEFAULT 'Medium'")
        _ensure_column(cursor, "tasks", "reminder_lead_minutes", "INTEGER NOT NULL DEFAULT 30")
        _ensure_column(cursor, "tasks", "reminder_start_hour", "INTEGER")
        _ensure_column(cursor, "tasks", "reminder_end_hour", "INTEGER")
        _ensure_column(cursor, "tasks", "reminder_interval_minutes", "INTEGER")
        _ensure_column(cursor, "tasks", "flashcards", "TEXT")
        _ensure_column(cursor, "tasks", "quiz", "TEXT")
        _ensure_column(cursor, "tasks", "completed_at", "TEXT")
        _ensure_column(cursor, "tasks", "postponed_count", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(cursor, "study_sessions", "topic", "TEXT")
        _ensure_column(cursor, "study_sessions", "understanding_rating", "INTEGER")
        _ensure_column(cursor, "study_sessions", "completion_status", "TEXT NOT NULL DEFAULT 'completed'")

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_status_date ON tasks(user_id, status, due_date, study_date, created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_subject ON tasks(user_id, subject)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_date ON study_sessions(user_id, session_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_settings_user ON user_settings(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_attendance_user_date ON attendance(user_id, attendance_date)")

        conn.commit()
        conn.close()
        _schema_ready = True


def _row_to_dict(row):
    return dict(row) if row else None


def normalize_user_preferences(settings):
    normalized = {**DEFAULT_USER_PREFERENCES, **(settings or {})}
    mode = str(normalized.get("appearance_mode", "light")).lower()
    normalized["appearance_mode"] = mode if mode in {"light", "dark"} else "light"
    theme_name = str(normalized.get("theme_name", "green")).lower()
    normalized["theme_name"] = theme_name if theme_name in {"green", "blue", "custom"} else "green"
    accent = str(normalized.get("custom_accent") or DEFAULT_USER_PREFERENCES["custom_accent"]).strip()
    normalized["custom_accent"] = accent if accent.startswith("#") and len(accent) in {4, 7} else DEFAULT_USER_PREFERENCES["custom_accent"]
    try:
        normalized["default_study_duration"] = max(5, min(240, int(normalized["default_study_duration"])))
    except (TypeError, ValueError):
        normalized["default_study_duration"] = DEFAULT_USER_PREFERENCES["default_study_duration"]
    try:
        normalized["font_size"] = max(11, min(20, int(normalized["font_size"])))
    except (TypeError, ValueError):
        normalized["font_size"] = DEFAULT_USER_PREFERENCES["font_size"]
    for key in ["notifications_enabled", "study_reminders_enabled", "sound_effects_enabled", "auto_save_enabled"]:
        normalized[key] = bool(normalized.get(key))
    return normalized


def get_user_preferences(username):
    user = get_user_by_username(username)
    if not user:
        return dict(DEFAULT_USER_PREFERENCES)
    connect()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT settings_json FROM app_preferences WHERE user_id = ?", (user["id"],))
    row = cursor.fetchone()
    if not row:
        settings = normalize_user_preferences(DEFAULT_USER_PREFERENCES)
        cursor.execute(
            "INSERT INTO app_preferences (user_id, settings_json) VALUES (?, ?)",
            (user["id"], json.dumps(settings)),
        )
        conn.commit()
        conn.close()
        return settings
    try:
        loaded = json.loads(row["settings_json"])
    except (TypeError, json.JSONDecodeError):
        loaded = {}
    settings = normalize_user_preferences(loaded)
    conn.close()
    return settings


def update_user_preferences(username, **changes):
    user = get_user_by_username(username)
    if not user:
        return normalize_user_preferences(changes)
    settings = normalize_user_preferences({**get_user_preferences(username), **changes})
    connect()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO app_preferences (user_id, settings_json, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            settings_json = excluded.settings_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        (user["id"], json.dumps(settings)),
    )
    conn.commit()
    conn.close()
    return settings


def reset_user_preferences(username):
    return update_user_preferences(username, **DEFAULT_USER_PREFERENCES)


def register_user(name, email, username, password):
    name = _normalize_identifier(name)
    email = _normalize_email(email)
    username = _normalize_identifier(username)
    if not name or not _validate_email(email) or not _validate_username(username) or len(password or "") < 8:
        return False
    connect()
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (name, email, username, password) VALUES (?, ?, ?, ?)",
            (name, email, username, _hash_password(password)),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        if conn is not None:
            conn.close()


def login_user(username, password):
    identifier = _normalize_identifier(username)
    if not identifier or not password:
        return None
    connect()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM users WHERE username = ? OR email = ?",
        (identifier, _normalize_email(identifier)),
    )
    result = cursor.fetchone()
    conn.close()
    user = _row_to_dict(result)
    if not user or not _verify_password(password, user.get("password")):
        return None
    if not _is_password_hash(user.get("password")):
        _upgrade_password_hash(user["id"], password)
        user["password"] = ""
    return user


def get_user_by_username(username):
    connect()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (_normalize_identifier(username),))
    result = cursor.fetchone()
    conn.close()
    return _row_to_dict(result)


def get_latest_user():
    connect()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users ORDER BY id DESC LIMIT 1")
    result = cursor.fetchone()
    conn.close()
    return _row_to_dict(result)


def get_all_users():
    connect()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users ORDER BY name COLLATE NOCASE, username COLLATE NOCASE")
    rows = [_row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def create_task_for_username(
    username,
    title,
    subject="",
    due_date=None,
    study_date=None,
    study_hours=1.0,
    status="pending",
    notes="",
    notes_path=None,
    study_plan="",
    priority="Medium",
    reminder_lead_minutes=30,
    reminder_start_hour=None,
    reminder_end_hour=None,
    reminder_interval_minutes=None,
):
    user = get_user_by_username(username)
    if not user:
        return False
    title = (title or "").strip()
    if not title:
        return False
    try:
        study_hours = max(0.25, min(1000.0, float(study_hours or 1)))
        reminder_lead_minutes = max(0, min(10080, int(reminder_lead_minutes or 0)))
    except (TypeError, ValueError):
        return False
    normalized_status = status if status in {"pending", "completed"} else "pending"

    connect()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO tasks (
            user_id, title, subject, due_date, study_date, study_hours, status,
            notes, notes_path, study_plan, priority, reminder_lead_minutes,
            reminder_start_hour, reminder_end_hour, reminder_interval_minutes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user["id"],
            title,
            (subject or "").strip(),
            due_date.strip() if due_date else None,
            study_date.strip() if study_date else None,
            study_hours,
            normalized_status,
            notes.strip(),
            notes_path.strip() if notes_path else None,
            study_plan.strip(),
            normalize_priority(priority),
            reminder_lead_minutes,
            int(reminder_start_hour) if reminder_start_hour is not None else None,
            int(reminder_end_hour) if reminder_end_hour is not None else None,
            int(reminder_interval_minutes) if reminder_interval_minutes is not None else None,
        ),
    )
    conn.commit()
    conn.close()
    _cached_data.clear()
    return True


def normalize_priority(priority):
    value = (priority or "Medium").strip().title()
    return value if value in {"High", "Medium", "Low"} else "Medium"


def update_task(task_id, title, subject="", due_date=None, study_date=None, study_hours=1.0, status="pending",
                notes="", notes_path=None, study_plan="", priority="Medium", reminder_lead_minutes=30):
    title = (title or "").strip()
    if not title:
        return False
    try:
        study_hours = max(0.25, min(1000.0, float(study_hours or 1)))
        reminder_lead_minutes = max(0, min(10080, int(reminder_lead_minutes or 0)))
    except (TypeError, ValueError):
        return False
    connect()
    conn = get_connection()
    cursor = conn.cursor()
    existing = get_task_by_id(task_id)
    old_study_date = existing.get("study_date") if existing else None
    old_due_date = existing.get("due_date") if existing else None
    old_status = existing.get("status") if existing else None
    normalized_status = status if status in {"pending", "completed"} else "pending"
    completed_at = existing.get("completed_at") if existing else None
    if normalized_status == "completed" and old_status != "completed":
        completed_at = datetime.now().isoformat(timespec="seconds")
    elif normalized_status != "completed":
        completed_at = None
    postponed_count = int(existing.get("postponed_count") or 0) if existing else 0
    if normalized_status != "completed" and (
        (old_study_date and study_date and old_study_date != study_date)
        or (old_due_date and due_date and old_due_date != due_date)
    ):
        postponed_count += 1
    cursor.execute(
        """
        UPDATE tasks
        SET title = ?, subject = ?, due_date = ?, study_date = ?, study_hours = ?, status = ?,
            notes = ?, notes_path = ?, study_plan = ?, priority = ?, reminder_lead_minutes = ?,
            completed_at = ?, postponed_count = ?
        WHERE id = ?
        """,
        (
            title,
            (subject or "").strip(),
            due_date.strip() if due_date else None,
            study_date.strip() if study_date else None,
            study_hours,
            normalized_status,
            (notes or "").strip(),
            notes_path.strip() if notes_path else None,
            (study_plan or "").strip(),
            normalize_priority(priority),
            reminder_lead_minutes,
            completed_at,
            postponed_count,
            task_id,
        ),
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    _cached_data.clear()
    return updated


def get_tasks_for_username(username, status=None):
    user = get_user_by_username(username)
    if not user:
        return []

    conn = get_connection()
    cursor = conn.cursor()
    if status:
        cursor.execute(
            "SELECT * FROM tasks WHERE user_id = ? AND status = ? ORDER BY COALESCE(due_date, study_date, created_at)",
            (user["id"], status),
        )
    else:
        cursor.execute(
            "SELECT * FROM tasks WHERE user_id = ? ORDER BY COALESCE(due_date, study_date, created_at)",
            (user["id"],),
        )
    rows = [_row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_task_by_id(task_id):
    connect()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    return _row_to_dict(row)


def get_user_settings(username):
    user = get_user_by_username(username)
    if not user:
        return {"reminder_start_hour": 18, "reminder_end_hour": 24, "reminder_interval_minutes": 60}

    connect()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_settings WHERE user_id = ?", (user["id"],))
    row = cursor.fetchone()
    if row is None:
        cursor.execute(
            """
            INSERT INTO user_settings (user_id, reminder_start_hour, reminder_end_hour, reminder_interval_minutes)
            VALUES (?, 18, 24, 60)
            """,
            (user["id"],),
        )
        conn.commit()
        cursor.execute("SELECT * FROM user_settings WHERE user_id = ?", (user["id"],))
        row = cursor.fetchone()
    conn.close()
    return _row_to_dict(row)


def update_user_settings(username, reminder_start_hour, reminder_end_hour, reminder_interval_minutes):
    user = get_user_by_username(username)
    if not user:
        return False

    connect()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO user_settings (user_id, reminder_start_hour, reminder_end_hour, reminder_interval_minutes)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            reminder_start_hour = excluded.reminder_start_hour,
            reminder_end_hour = excluded.reminder_end_hour,
            reminder_interval_minutes = excluded.reminder_interval_minutes
        """,
        (user["id"], int(reminder_start_hour), int(reminder_end_hour), int(reminder_interval_minutes)),
    )
    conn.commit()
    conn.close()
    return True


def get_attendance_settings(username):
    user = get_user_by_username(username)
    if not user:
        return {"leave_weekday": 6}

    connect()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM attendance_settings WHERE user_id = ?", (user["id"],))
    row = cursor.fetchone()
    if row is None:
        cursor.execute(
            "INSERT INTO attendance_settings (user_id, leave_weekday) VALUES (?, 6)",
            (user["id"],),
        )
        conn.commit()
        cursor.execute("SELECT * FROM attendance_settings WHERE user_id = ?", (user["id"],))
        row = cursor.fetchone()
    conn.close()
    return _row_to_dict(row)


def update_attendance_leave_day(username, leave_weekday):
    user = get_user_by_username(username)
    if not user:
        return False

    leave_weekday = max(0, min(6, int(leave_weekday)))
    connect()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO attendance_settings (user_id, leave_weekday)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET leave_weekday = excluded.leave_weekday
        """,
        (user["id"], leave_weekday),
    )
    conn.commit()
    conn.close()
    _cached_data.clear()
    return True


def mark_attendance(username, attendance_date=None, status="present"):
    user = get_user_by_username(username)
    if not user:
        return False

    attendance_date = attendance_date or date.today().isoformat()
    normalized_status = status if status in {"present", "leave"} else "present"
    connect()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO attendance (user_id, attendance_date, status)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, attendance_date) DO UPDATE SET status = excluded.status
        """,
        (user["id"], attendance_date, normalized_status),
    )
    conn.commit()
    conn.close()
    _cached_data.clear()
    return True


def get_attendance_for_username(username):
    user = get_user_by_username(username)
    if not user:
        return []

    connect()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM attendance
        WHERE user_id = ?
        ORDER BY attendance_date DESC
        """,
        (user["id"],),
    )
    rows = [_row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_upcoming_tasks(username, limit=3):
    user = get_user_by_username(username)
    if not user:
        return []

    # Let SQLite filter and limit the dashboard list. Pulling every task just to
    # show three rows becomes visible lag once a student has a long planner.
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM tasks
        WHERE user_id = ? AND status != 'completed'
        ORDER BY COALESCE(due_date, study_date, '9999-12-31'),
                 CASE priority WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END,
                 LOWER(title)
        LIMIT ?
        """,
        (user["id"], int(limit)),
    )
    rows = [_row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def _priority_rank(task):
    return {"High": 0, "Medium": 1, "Low": 2}.get(task.get("priority") or "Medium", 1)


def get_subjects_for_username(username):
    user = get_user_by_username(username)
    if not user:
        return []

    # DISTINCT in SQLite avoids creating Python objects for every historical task.
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT DISTINCT TRIM(subject) AS subject
        FROM tasks
        WHERE user_id = ? AND TRIM(COALESCE(subject, '')) != ''
        ORDER BY subject
        """,
        (user["id"],),
    )
    rows = [row["subject"] for row in cursor.fetchall()]
    conn.close()
    return rows


def _parse_iso_day(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def get_progress_summary(username):
    cache_key = ("progress_summary", username)
    cached = _cached_data.get(cache_key)
    if cached:
        cached_at, cached_value = cached
        if (datetime.now() - cached_at).total_seconds() < 10:
            return cached_value

    tasks = get_tasks_for_username(username)
    total_tasks = len(tasks)
    completed_tasks = sum(1 for task in tasks if task["status"] == "completed")
    pending_tasks = total_tasks - completed_tasks

    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    week_days = [start_of_week + timedelta(days=index) for index in range(7)]
    weekly_minutes = {day.isoformat(): 0 for day in week_days}
    weekly_completed = 0
    weekly_total = 0
    overdue_tasks = 0
    priority_counts = {"High": 0, "Medium": 0, "Low": 0}
    subject_task_counts = {}

    for task in tasks:
        task_day = _parse_iso_day(task.get("study_date")) or _parse_iso_day(task.get("due_date"))
        priority_counts[normalize_priority(task.get("priority"))] += 1
        subject = (task.get("subject") or "Unsorted").strip() or "Unsorted"
        subject_task_counts[subject] = subject_task_counts.get(subject, 0) + 1
        due_day = _parse_iso_day(task.get("due_date")) or task_day
        if due_day and due_day < today and task["status"] != "completed":
            overdue_tasks += 1
        if task_day and start_of_week <= task_day <= start_of_week + timedelta(days=6):
            weekly_total += 1
            if task["status"] == "completed":
                weekly_completed += 1

    user = get_user_by_username(username)
    total_study_minutes = 0
    subject_minutes = {}
    if user:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT session_date, subject, study_minutes
            FROM study_sessions
            WHERE user_id = ?
            """,
            (user["id"],),
        )
        session_rows = cursor.fetchall()
        conn.close()

        for session in session_rows:
            session_day = _parse_iso_day(session["session_date"])
            study_minutes = int(session["study_minutes"] or 0)
            subject = (session["subject"] or "Unsorted").strip() or "Unsorted"
            subject_minutes[subject] = subject_minutes.get(subject, 0) + study_minutes
            total_study_minutes += study_minutes
            if session_day and start_of_week <= session_day <= start_of_week + timedelta(days=6):
                weekly_minutes[session_day.isoformat()] += study_minutes

    completion_rate = round((completed_tasks / total_tasks) * 100) if total_tasks else 0
    weekly_completion_rate = round((weekly_completed / weekly_total) * 100) if weekly_total else 0

    reminders = []
    for task in sorted(tasks, key=lambda row: row.get("due_date") or row.get("study_date") or "9999-12-31"):
        if task["status"] == "completed":
            continue
        task_day = _parse_iso_day(task.get("due_date")) or _parse_iso_day(task.get("study_date"))
        if task_day and task_day >= today:
            reminders.append(task)
    reminders = reminders[:3]

    summary = {
        "total_tasks": total_tasks,
          "completed_tasks": completed_tasks,
          "pending_tasks": pending_tasks,
          "completion_rate": completion_rate,
          "weekly_completion_rate": weekly_completion_rate,
          "weekly_minutes": [weekly_minutes[day.isoformat()] for day in week_days],
          "weekly_labels": [day.strftime("%a") for day in week_days],
          "reminders": reminders,
          "total_study_minutes": total_study_minutes,
          "subject_minutes": sorted(subject_minutes.items(), key=lambda item: item[1], reverse=True),
          "subject_task_counts": sorted(subject_task_counts.items(), key=lambda item: item[1], reverse=True),
          "priority_counts": priority_counts,
          "overdue_tasks": overdue_tasks,
      }
    _cached_data[cache_key] = (datetime.now(), summary)
    return summary


def mark_task_status(task_id, status):
    connect()
    normalized_status = status if status in {"pending", "completed"} else "pending"
    completed_at = datetime.now().isoformat(timespec="seconds") if normalized_status == "completed" else None
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET status = ?, completed_at = ? WHERE id = ?",
        (normalized_status, completed_at, task_id),
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    _cached_data.clear()
    return updated


def save_task_review_materials(task_id, flashcards, quiz):
    connect()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET flashcards = ?, quiz = ? WHERE id = ?",
        ((flashcards or "").strip(), (quiz or "").strip(), task_id),
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    _cached_data.clear()
    return updated


def delete_task(task_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    _cached_data.clear()
    return deleted


def log_study_session(
    username,
    study_minutes,
    subject=None,
    break_interval=None,
    break_minutes=None,
    session_date=None,
    topic=None,
    understanding_rating=None,
    completion_status="completed",
):
    user = get_user_by_username(username)
    if not user:
        return False
    try:
        study_minutes = max(1, min(1440, int(study_minutes)))
        understanding_rating = int(understanding_rating) if understanding_rating else None
        if understanding_rating is not None:
            understanding_rating = max(1, min(5, understanding_rating))
    except (TypeError, ValueError):
        return False

    connect()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO study_sessions (
            user_id, subject, topic, study_minutes, understanding_rating,
            completion_status, break_interval, break_minutes, session_date
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user["id"],
            subject.strip() if subject else None,
            topic.strip() if topic else None,
            study_minutes,
            understanding_rating,
            normalize_completion_status(completion_status),
            int(break_interval) if break_interval else None,
            int(break_minutes) if break_minutes else None,
            (session_date or date.today().isoformat()),
        ),
    )
    conn.commit()
    conn.close()
    _cached_data.clear()
    return True


def normalize_completion_status(value):
    normalized = (value or "completed").strip().lower()
    return normalized if normalized in {"completed", "partial", "skipped", "postponed"} else "completed"


def add_xp_event(username, points, reason, source_type=None, source_id=None):
    user = get_user_by_username(username)
    if not user:
        return False
    connect()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO xp_events (user_id, points, reason, source_type, source_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user["id"], int(points), reason, source_type, source_id),
    )
    conn.commit()
    conn.close()
    _cached_data.clear()
    return True


def get_xp_events(username):
    user = get_user_by_username(username)
    if not user:
        return []
    connect()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM xp_events WHERE user_id = ? ORDER BY created_at DESC",
        (user["id"],),
    )
    rows = [_row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def unlock_achievement(username, badge_key, badge_name, description=""):
    user = get_user_by_username(username)
    if not user:
        return False
    connect()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR IGNORE INTO achievements (user_id, badge_key, badge_name, description)
        VALUES (?, ?, ?, ?)
        """,
        (user["id"], badge_key, badge_name, description),
    )
    conn.commit()
    unlocked = cursor.rowcount > 0
    conn.close()
    return unlocked


def get_achievements(username):
    user = get_user_by_username(username)
    if not user:
        return []
    connect()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM achievements WHERE user_id = ? ORDER BY unlocked_at DESC",
        (user["id"],),
    )
    rows = [_row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_study_sessions_for_username(username):
    user = get_user_by_username(username)
    if not user:
        return []
    connect()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM study_sessions
        WHERE user_id = ?
        ORDER BY session_date DESC, created_at DESC
        """,
        (user["id"],),
    )
    rows = [_row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def seed_sample_study_data(username):
    user = get_user_by_username(username)
    if not user:
        return False
    if get_tasks_for_username(username) or get_study_sessions_for_username(username):
        return False

    today = date.today()
    sample_tasks = [
        ("Revise limits", "Mathematics", 2, "pending", "High", 2),
        ("SQL joins practice", "DBMS", 5, "completed", "Medium", 0),
        ("Organic reactions sheet", "Chemistry", 7, "pending", "High", 3),
        ("OS scheduling notes", "Operating Systems", 4, "completed", "Medium", 1),
        ("Statistics worksheet", "Mathematics", 10, "pending", "Low", 1),
    ]
    for title, subject, days, status, priority, postponed in sample_tasks:
        create_task_for_username(
            username,
            title,
            subject=subject,
            due_date=(today + timedelta(days=days)).isoformat(),
            study_date=(today + timedelta(days=max(days - 1, 0))).isoformat(),
            study_hours=1.5,
            status=status,
            priority=priority,
        )
        task = get_tasks_for_username(username)[-1]
        if task:
            conn = get_connection()
            cursor = conn.cursor()
            completed_at = datetime.now().isoformat(timespec="seconds") if status == "completed" else None
            cursor.execute(
                "UPDATE tasks SET postponed_count = ?, completed_at = ? WHERE id = ?",
                (postponed, completed_at, task["id"]),
            )
            conn.commit()
            conn.close()

    sample_sessions = [
        ("Mathematics", "Limits", 45, 2, "partial", 6),
        ("Mathematics", "Derivatives", 60, 3, "completed", 5),
        ("Chemistry", "Organic reactions", 35, 1, "postponed", 4),
        ("DBMS", "Joins", 50, 4, "completed", 3),
        ("Operating Systems", "Scheduling", 55, 5, "completed", 2),
        ("Chemistry", "Aldehydes", 30, 2, "skipped", 1),
    ]
    for subject, topic, minutes, rating, status, days_back in sample_sessions:
        log_study_session(
            username,
            minutes,
            subject=subject,
            topic=topic,
            understanding_rating=rating,
            completion_status=status,
            session_date=(today - timedelta(days=days_back)).isoformat(),
        )
    return True


def reset_user_progress(username):
    user = get_user_by_username(username)
    if not user:
        return False
    connect()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM xp_events WHERE user_id = ?", (user["id"],))
    cursor.execute("DELETE FROM achievements WHERE user_id = ?", (user["id"],))
    cursor.execute(
        """
        UPDATE tasks
        SET status = 'pending', completed_at = NULL, postponed_count = 0
        WHERE user_id = ?
        """,
        (user["id"],),
    )
    cursor.execute("DELETE FROM study_sessions WHERE user_id = ?", (user["id"],))
    conn.commit()
    conn.close()
    _cached_data.clear()
    return True


# ========== ASYNC WRAPPERS FOR PERFORMANCE ==========
def run_async_db(func, args=(), on_complete=None, on_error=None):
    """Run database function asynchronously to avoid blocking UI"""
    def _execute():
        try:
            result = func(*args)
            if on_complete:
                on_complete(result)
            return result
        except Exception as e:
            if on_error:
                on_error(e)
            return None
    
    thread = threading.Thread(target=_execute, daemon=True)
    thread.start()
    return thread


def get_user_by_username_async(username, on_complete=None):
    """Async version of get_user_by_username"""
    return run_async_db(get_user_by_username, (username,), on_complete)


def get_progress_summary_async(username, on_complete=None):
    """Async version of get_progress_summary"""
    return run_async_db(get_progress_summary, (username,), on_complete)


def get_upcoming_tasks_async(username, limit=3, on_complete=None):
    """Async version of get_upcoming_tasks"""
    return run_async_db(get_upcoming_tasks, (username, limit), on_complete)


def get_tasks_for_username_async(username, on_complete=None):
    """Async version of get_tasks_for_username"""
    return run_async_db(get_tasks_for_username, (username,), on_complete)


def get_subjects_for_username_async(username, on_complete=None):
    """Async version of get_subjects_for_username"""
    return run_async_db(get_subjects_for_username, (username,), on_complete)


def create_task_async(username, title, subject="", due_date=None, study_date=None, 
                     study_hours=1.0, status="pending", notes="", priority="Medium", 
                     on_complete=None, on_error=None):
    """Async version of create_task_for_username"""
    def _create():
        return create_task_for_username(
            username, title, subject, due_date, study_date, study_hours,
            status, notes, None, "", priority, 30, None, None, None
        )
    return run_async_db(_create, (), on_complete, on_error)
