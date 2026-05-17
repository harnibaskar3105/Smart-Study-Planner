from dataclasses import dataclass
from datetime import date, datetime, timedelta

import database


DEFAULT_SUBJECTS = ["Science", "Technology", "Commerce", "Humanities", "Languages"]
MIN_LINKED_SUBJECTS = 4
GENERIC_LINKED_SUBJECTS = {"general", "unsorted"}
DEFAULT_SETTINGS = {"reminder_start_hour": 18, "reminder_end_hour": 24, "reminder_interval_minutes": 60}
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@dataclass(frozen=True)
class DashboardSnapshot:
    user: dict
    summary: dict
    upcoming_tasks: list
    subjects: list
    settings: dict
    reminder_tasks: list
    attendance: dict


def _row_to_dict(row):
    return dict(row) if row else None


def _parse_iso_day(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _priority_name(value):
    return database.normalize_priority(value)


def _append_unique_subject(subjects, seen_subjects, value):
    subject = (value or "").strip()
    normalized = subject.casefold()
    if subject and normalized not in GENERIC_LINKED_SUBJECTS and normalized not in seen_subjects:
        subjects.append(subject)
        seen_subjects.add(normalized)


def _build_linked_subjects(tasks, sessions, minimum=MIN_LINKED_SUBJECTS):
    subjects = []
    seen_subjects = set()

    for task in tasks:
        _append_unique_subject(subjects, seen_subjects, task.get("subject"))

    for session in sessions:
        _append_unique_subject(subjects, seen_subjects, session.get("subject"))

    for subject in DEFAULT_SUBJECTS:
        if len(subjects) >= minimum:
            break
        _append_unique_subject(subjects, seen_subjects, subject)

    return subjects or DEFAULT_SUBJECTS[:minimum]


def _build_summary(tasks, sessions, today=None):
    today = today or date.today()
    start_of_week = today - timedelta(days=today.weekday())
    week_days = [start_of_week + timedelta(days=index) for index in range(7)]
    weekly_minutes = {day.isoformat(): 0 for day in week_days}
    total_tasks = len(tasks)
    completed_tasks = sum(1 for task in tasks if task["status"] == "completed")
    pending_tasks = total_tasks - completed_tasks
    weekly_completed = 0
    weekly_total = 0
    overdue_tasks = 0
    priority_counts = {"High": 0, "Medium": 0, "Low": 0}
    subject_task_counts = {}

    for task in tasks:
        task_day = _parse_iso_day(task.get("study_date")) or _parse_iso_day(task.get("due_date"))
        priority_counts[_priority_name(task.get("priority"))] += 1
        subject = (task.get("subject") or "Unsorted").strip() or "Unsorted"
        subject_task_counts[subject] = subject_task_counts.get(subject, 0) + 1
        due_day = _parse_iso_day(task.get("due_date")) or task_day
        if due_day and due_day < today and task["status"] != "completed":
            overdue_tasks += 1
        if task_day and start_of_week <= task_day <= start_of_week + timedelta(days=6):
            weekly_total += 1
            if task["status"] == "completed":
                weekly_completed += 1

    total_study_minutes = 0
    subject_minutes = {}
    for session in sessions:
        session_day = _parse_iso_day(session["session_date"])
        study_minutes = int(session["study_minutes"] or 0)
        subject = (session["subject"] or "Unsorted").strip() or "Unsorted"
        subject_minutes[subject] = subject_minutes.get(subject, 0) + study_minutes
        total_study_minutes += study_minutes
        if session_day and start_of_week <= session_day <= start_of_week + timedelta(days=6):
            weekly_minutes[session_day.isoformat()] += study_minutes

    reminders = []
    for task in sorted(tasks, key=lambda row: row.get("due_date") or row.get("study_date") or "9999-12-31"):
        if task["status"] == "completed":
            continue
        task_day = _parse_iso_day(task.get("due_date")) or _parse_iso_day(task.get("study_date"))
        if task_day and task_day >= today:
            reminders.append(task)

    completion_rate = round((completed_tasks / total_tasks) * 100) if total_tasks else 0
    weekly_completion_rate = round((weekly_completed / weekly_total) * 100) if weekly_total else 0
    return {
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "pending_tasks": pending_tasks,
        "completion_rate": completion_rate,
        "weekly_completion_rate": weekly_completion_rate,
        "weekly_minutes": [weekly_minutes[day.isoformat()] for day in week_days],
        "weekly_labels": [day.strftime("%a") for day in week_days],
        "reminders": reminders[:3],
        "total_study_minutes": total_study_minutes,
        "subject_minutes": sorted(subject_minutes.items(), key=lambda item: item[1], reverse=True),
        "subject_task_counts": sorted(subject_task_counts.items(), key=lambda item: item[1], reverse=True),
        "priority_counts": priority_counts,
        "overdue_tasks": overdue_tasks,
    }


def _count_attendance_week(record_by_date, week_days, leave_weekday=None):
    present_count = 0
    required_count = 0
    week = []
    for day in week_days:
        iso_day = day.isoformat()
        is_leave_day = leave_weekday is not None and day.weekday() == leave_weekday
        record = record_by_date.get(iso_day)
        status = record["status"] if record else ("leave" if is_leave_day else "missing")
        if not is_leave_day:
            required_count += 1
        if status == "present":
            present_count += 1
        week.append(
            {
                "date": iso_day,
                "label": day.strftime("%a"),
                "day_name": WEEKDAY_NAMES[day.weekday()],
                "status": status,
                "is_today": day == date.today(),
                "is_leave_day": is_leave_day,
            }
        )
    percentage = round((present_count / required_count) * 100) if required_count else 100
    return present_count, required_count, percentage, week


def _build_attendance_summary(records, leave_weekday, today=None):
    today = today or date.today()
    start_of_week = today - timedelta(days=today.weekday())
    record_by_date = {record["attendance_date"]: record for record in records}
    week_days = [start_of_week + timedelta(days=index) for index in range(7)]
    present_count, required_count, percentage, week = _count_attendance_week(record_by_date, week_days, leave_weekday)
    leave_enabled = percentage >= 75
    if not leave_enabled:
        present_count, required_count, percentage, week = _count_attendance_week(record_by_date, week_days, None)
    for item in week:
        item["is_today"] = item["date"] == today.isoformat()

    today_record = record_by_date.get(today.isoformat())
    today_is_leave = leave_enabled and today.weekday() == leave_weekday
    today_status = today_record["status"] if today_record else ("leave" if today_is_leave else "missing")
    return {
        "leave_weekday": leave_weekday,
        "leave_day_name": WEEKDAY_NAMES[leave_weekday],
        "leave_enabled": leave_enabled,
        "today_status": today_status,
        "today_is_leave": today_is_leave,
        "percentage": percentage,
        "present_this_week": present_count,
        "required_this_week": required_count,
        "week": week,
    }


def load_dashboard_snapshot(username, upcoming_limit=3):
    """Return all dashboard data from one DB connection for background loading.

    Keeping this outside dashboard.py separates data preparation from widget code
    and prevents the UI from firing several duplicate full-table reads.
    """
    database.connect()
    conn = database.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", ((username or "").strip(),))
        user = _row_to_dict(cursor.fetchone())
        if user is None:
            cursor.execute("SELECT * FROM users ORDER BY id DESC LIMIT 1")
            user = _row_to_dict(cursor.fetchone()) or {"id": None, "name": username or "Student", "username": username or "Student", "email": ""}

        if user.get("id") is None:
            return DashboardSnapshot(
                user=user,
                summary=_build_summary([], []),
                upcoming_tasks=[],
                subjects=DEFAULT_SUBJECTS,
                settings=DEFAULT_SETTINGS,
                reminder_tasks=[],
                attendance=_build_attendance_summary([], 6),
            )

        cursor.execute(
            "SELECT * FROM tasks WHERE user_id = ? ORDER BY COALESCE(due_date, study_date, created_at)",
            (user["id"],),
        )
        tasks = [_row_to_dict(row) for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT session_date, subject, study_minutes
            FROM study_sessions
            WHERE user_id = ?
            """,
            (user["id"],),
        )
        sessions = [_row_to_dict(row) for row in cursor.fetchall()]

        cursor.execute("SELECT * FROM user_settings WHERE user_id = ?", (user["id"],))
        settings = _row_to_dict(cursor.fetchone())
        if settings is None:
            cursor.execute(
                """
                INSERT INTO user_settings (user_id, reminder_start_hour, reminder_end_hour, reminder_interval_minutes)
                VALUES (?, 18, 24, 60)
                """,
                (user["id"],),
            )
            conn.commit()
            settings = {**DEFAULT_SETTINGS, "user_id": user["id"]}

        cursor.execute("SELECT * FROM attendance_settings WHERE user_id = ?", (user["id"],))
        attendance_settings = _row_to_dict(cursor.fetchone())
        if attendance_settings is None:
            cursor.execute(
                "INSERT INTO attendance_settings (user_id, leave_weekday) VALUES (?, 6)",
                (user["id"],),
            )
            conn.commit()
            attendance_settings = {"user_id": user["id"], "leave_weekday": 6}

        cursor.execute(
            """
            SELECT attendance_date, status
            FROM attendance
            WHERE user_id = ?
            ORDER BY attendance_date DESC
            """,
            (user["id"],),
        )
        attendance_records = [_row_to_dict(row) for row in cursor.fetchall()]

        subjects = _build_linked_subjects(tasks, sessions)

        pending = [task for task in tasks if task["status"] != "completed"]
        pending.sort(
            key=lambda task: (
                task.get("due_date") or task.get("study_date") or "9999-12-31",
                {"High": 0, "Medium": 1, "Low": 2}.get(task.get("priority") or "Medium", 1),
                task["title"].lower(),
            )
        )

        summary = _build_summary(tasks, sessions)
        attendance = _build_attendance_summary(attendance_records, int(attendance_settings.get("leave_weekday", 6)))
        return DashboardSnapshot(
            user=user,
            summary=summary,
            upcoming_tasks=pending[:upcoming_limit],
            subjects=subjects,
            settings=settings,
            reminder_tasks=pending,
            attendance=attendance,
        )
    finally:
        conn.close()
