from datetime import date, datetime, timedelta

import database


XP_PER_TASK = 50
XP_PER_STUDY_SESSION = 20
XP_PER_STUDY_HOUR = 10
XP_PER_ATTENDANCE = 15
XP_DAILY_STUDY_GOAL = 35
XP_WEEKLY_CHALLENGE = 100
PENALTY_MISSED_TASK = -20
PENALTY_LOW_ATTENDANCE = -35
PENALTY_INACTIVITY = -15
LEVEL_SIZE = 250

THEME_UNLOCKS = [
    {"level": 1, "name": "Classic Scholar", "description": "Default warm study theme."},
    {"level": 3, "name": "Focus Forest", "description": "Unlocked by reaching Level 3."},
    {"level": 5, "name": "Neon Academy", "description": "Unlocked by reaching Level 5."},
    {"level": 8, "name": "Mythic Library", "description": "Unlocked by reaching Level 8."},
]


class XPSystem:
    def __init__(self, username):
        self.username = username

    def award_task_completion(self, task_id):
        for event in database.get_xp_events(self.username):
            if event.get("source_type") == "task" and event.get("source_id") == task_id:
                return
        task = database.get_task_by_id(task_id)
        title = task["title"] if task else "task"
        database.add_xp_event(self.username, XP_PER_TASK, f"Completed {title}", "task", task_id)
        self.refresh_achievements()

    def award_study_session(self, minutes, session_id=None):
        points = XP_PER_STUDY_SESSION + int(int(minutes or 0) / 60 * XP_PER_STUDY_HOUR)
        database.add_xp_event(self.username, points, "Logged a study session", "study_session", session_id)
        self.refresh_achievements()

    def award_attendance(self, attendance_date=None):
        attendance_date = attendance_date or date.today().isoformat()
        source_id = int(attendance_date.replace("-", ""))
        for event in database.get_xp_events(self.username):
            if event.get("source_type") == "attendance" and event.get("source_id") == source_id:
                return False
        database.add_xp_event(self.username, XP_PER_ATTENDANCE, "Marked daily attendance", "attendance", source_id)
        self.refresh_achievements()
        return True

    def award_daily_study_goal(self, minutes, goal_minutes=50):
        today_key = int(date.today().strftime("%Y%m%d"))
        for event in database.get_xp_events(self.username):
            if event.get("source_type") == "daily_goal" and event.get("source_id") == today_key:
                return False
        if int(minutes or 0) < goal_minutes:
            return False
        database.add_xp_event(self.username, XP_DAILY_STUDY_GOAL, "Completed daily study goal", "daily_goal", today_key)
        self.refresh_achievements()
        return True

    def apply_daily_penalties(self):
        today = date.today()
        today_key = int(today.strftime("%Y%m%d"))
        events = database.get_xp_events(self.username)
        existing_penalties = {
            event.get("source_type")
            for event in events
            if int(event.get("source_id") or 0) == today_key
        }

        tasks = database.get_tasks_for_username(self.username)
        overdue = [
            task for task in tasks
            if task.get("status") != "completed"
            and self._parse_day(task.get("due_date") or task.get("study_date"))
            and self._parse_day(task.get("due_date") or task.get("study_date")) < today
        ]
        attendance = self.attendance_summary()
        sessions = database.get_study_sessions_for_username(self.username)
        studied_today = any(session.get("session_date") == today.isoformat() for session in sessions)

        if overdue and "penalty_missed_task" not in existing_penalties:
            database.add_xp_event(self.username, PENALTY_MISSED_TASK, "Penalty: overdue task pressure", "penalty_missed_task", today_key)
        if attendance["percentage"] < 60 and "penalty_low_attendance" not in existing_penalties:
            database.add_xp_event(self.username, PENALTY_LOW_ATTENDANCE, "Penalty: attendance below 60%", "penalty_low_attendance", today_key)
        if not studied_today and "penalty_inactivity" not in existing_penalties:
            database.add_xp_event(self.username, PENALTY_INACTIVITY, "Penalty: no study activity today", "penalty_inactivity", today_key)

    def profile(self):
        total_xp = sum(int(event["points"] or 0) for event in database.get_xp_events(self.username))
        level = max(total_xp // LEVEL_SIZE + 1, 1)
        current_level_xp = total_xp % LEVEL_SIZE
        next_level_xp = LEVEL_SIZE
        return {
            "total_xp": total_xp,
            "level": level,
            "current_level_xp": current_level_xp,
            "next_level_xp": next_level_xp,
            "level_progress": current_level_xp / next_level_xp,
            "recent_events": database.get_xp_events(self.username)[:5],
        }

    def game_state(self):
        self.apply_daily_penalties()
        tasks = database.get_tasks_for_username(self.username)
        sessions = database.get_study_sessions_for_username(self.username)
        attendance = self.attendance_summary()
        self.evaluate_bonus_rewards(tasks, sessions, attendance)
        profile = self.profile()
        achievements = database.get_achievements(self.username)
        study_streak = self._study_streak(sessions)
        task_streak = self._completion_streak(tasks)
        missions = self.daily_missions(tasks, sessions, attendance)
        weekly = self.weekly_challenges(tasks, sessions, attendance)
        profile.update(
            {
                "rank_title": self.rank_title(profile["level"]),
                "achievements": achievements,
                "achievement_count": len(achievements),
                "study_streak": study_streak,
                "task_streak": task_streak,
                "consistency_score": self.consistency_score(study_streak, task_streak, attendance["percentage"]),
                "daily_missions": missions,
                "weekly_challenges": weekly,
                "leaderboard": build_leaderboard(),
                "unlocked_themes": [theme for theme in THEME_UNLOCKS if profile["level"] >= theme["level"]],
                "next_unlock": next((theme for theme in THEME_UNLOCKS if profile["level"] < theme["level"]), None),
                "quote": motivational_quote(study_streak, attendance["percentage"], profile["level"]),
            }
        )
        return profile

    def evaluate_bonus_rewards(self, tasks, sessions, attendance):
        today = date.today()
        today_key = int(today.strftime("%Y%m%d"))
        today_minutes = sum(int(session.get("study_minutes") or 0) for session in sessions if session.get("session_date") == today.isoformat())
        self.award_daily_study_goal(today_minutes)

        week_key = int((today - timedelta(days=today.weekday())).strftime("%Y%m%d"))
        events = database.get_xp_events(self.username)
        weekly_done = {event.get("source_type") for event in events if int(event.get("source_id") or 0) == week_key}
        for challenge in self.weekly_challenges(tasks, sessions, attendance):
            source_type = "weekly_" + challenge["title"].lower().replace(" ", "_").replace("+", "plus")
            if challenge["progress"] >= challenge["target"] and source_type not in weekly_done:
                database.add_xp_event(self.username, challenge["reward"], f"Weekly challenge: {challenge['title']}", source_type, week_key)

    def refresh_achievements(self):
        tasks = database.get_tasks_for_username(self.username)
        sessions = database.get_study_sessions_for_username(self.username)
        completed_tasks = [task for task in tasks if task.get("status") == "completed"]
        profile = self.profile()

        if completed_tasks:
            database.unlock_achievement(
                self.username,
                "first_win",
                "First Win",
                "Completed the first planner task.",
            )
        if len(completed_tasks) >= 5:
            database.unlock_achievement(
                self.username,
                "task_runner",
                "Task Runner",
                "Completed five planner tasks.",
            )
        if profile["level"] >= 3:
            database.unlock_achievement(
                self.username,
                "level_three",
                "Level 3 Scholar",
                "Reached level 3 through steady progress.",
            )
        if self._study_streak(sessions) >= 3:
            database.unlock_achievement(
                self.username,
                "three_day_streak",
                "3-Day Streak",
                "Studied on three consecutive days.",
            )
        if self._study_streak(sessions) >= 7:
            database.unlock_achievement(
                self.username,
                "weekly_flame",
                "Weekly Flame",
                "Protected a seven-day study streak.",
            )
        attendance = self.attendance_summary()
        if attendance["percentage"] >= 90:
            database.unlock_achievement(
                self.username,
                "attendance_guardian",
                "Attendance Guardian",
                "Kept weekly attendance at 90% or higher.",
            )
        if profile["level"] >= 5:
            database.unlock_achievement(
                self.username,
                "theme_hunter",
                "Theme Hunter",
                "Unlocked advanced dashboard themes.",
            )

    def attendance_summary(self):
        settings = database.get_attendance_settings(self.username)
        leave_weekday = int(settings.get("leave_weekday", 6))
        records = database.get_attendance_for_username(self.username)
        today = date.today()
        start = today - timedelta(days=today.weekday())
        record_by_day = {row["attendance_date"]: row for row in records}
        required = 0
        present = 0
        for offset in range(7):
            current = start + timedelta(days=offset)
            if current.weekday() == leave_weekday:
                continue
            required += 1
            if record_by_day.get(current.isoformat(), {}).get("status") == "present":
                present += 1
        return {
            "percentage": round((present / required) * 100) if required else 100,
            "present": present,
            "required": required,
            "leave_weekday": leave_weekday,
        }

    def daily_missions(self, tasks, sessions, attendance):
        today = date.today().isoformat()
        completed_today = any((task.get("completed_at") or "").startswith(today) for task in tasks)
        studied_today = sum(int(session.get("study_minutes") or 0) for session in sessions if session.get("session_date") == today)
        attended_today = any(row.get("attendance_date") == today and row.get("status") == "present" for row in database.get_attendance_for_username(self.username))
        return [
            {"title": "Check in", "reward": XP_PER_ATTENDANCE, "done": attended_today, "detail": "Mark attendance today."},
            {"title": "Win one quest", "reward": XP_PER_TASK, "done": completed_today, "detail": "Complete any planner task."},
            {"title": "Deep focus", "reward": XP_DAILY_STUDY_GOAL, "done": studied_today >= 50, "detail": "Log 50 minutes of study."},
        ]

    def weekly_challenges(self, tasks, sessions, attendance):
        today = date.today()
        start = today - timedelta(days=today.weekday())
        completed_week = [
            task for task in tasks
            if task.get("completed_at") and self._parse_day(task.get("completed_at")[:10]) and self._parse_day(task.get("completed_at")[:10]) >= start
        ]
        study_minutes = sum(
            int(session.get("study_minutes") or 0)
            for session in sessions
            if self._parse_day(session.get("session_date")) and self._parse_day(session.get("session_date")) >= start
        )
        return [
            {"title": "Complete 5 tasks", "progress": min(len(completed_week), 5), "target": 5, "reward": XP_WEEKLY_CHALLENGE},
            {"title": "Study 300 minutes", "progress": min(study_minutes, 300), "target": 300, "reward": XP_WEEKLY_CHALLENGE},
            {"title": "Keep attendance 80%+", "progress": min(attendance["percentage"], 80), "target": 80, "reward": XP_WEEKLY_CHALLENGE},
        ]

    def consistency_score(self, study_streak, task_streak, attendance_percent):
        return min(100, round((attendance_percent * 0.45) + (min(study_streak, 7) / 7 * 35) + (min(task_streak, 5) / 5 * 20)))

    def rank_title(self, level):
        if level >= 8:
            return "Mythic Scholar"
        if level >= 5:
            return "Focus Hero"
        if level >= 3:
            return "Quest Climber"
        return "Rookie Planner"

    def _study_streak(self, sessions):
        days = sorted({row.get("session_date") for row in sessions if row.get("session_date")}, reverse=True)
        if not days:
            return 0
        parsed = []
        for day in days:
            try:
                parsed.append(datetime.strptime(day, "%Y-%m-%d").date())
            except ValueError:
                continue
        streak = 0
        cursor = datetime.today().date()
        parsed_set = set(parsed)
        while cursor in parsed_set:
            streak += 1
            cursor -= timedelta(days=1)
        return streak

    def _completion_streak(self, tasks):
        days = sorted({(task.get("completed_at") or "")[:10] for task in tasks if task.get("completed_at")}, reverse=True)
        parsed = {self._parse_day(day) for day in days}
        parsed.discard(None)
        streak = 0
        cursor = date.today()
        while cursor in parsed:
            streak += 1
            cursor -= timedelta(days=1)
        return streak

    def _parse_day(self, value):
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None


def motivational_quote(streak, attendance_percent, level):
    if attendance_percent < 60:
        return "A comeback starts with one check-in. Protect today."
    if streak >= 7:
        return "Your consistency is becoming a superpower."
    if level >= 5:
        return "High-level scholars win by making focus repeatable."
    return "Small quests, every day. That is how levels are built."


def build_leaderboard():
    rows = []
    for user in database.get_all_users():
        username = user["username"]
        total_xp = sum(int(event["points"] or 0) for event in database.get_xp_events(username))
        rows.append(
            {
                "username": username,
                "name": user.get("name") or username,
                "total_xp": total_xp,
                "level": max(total_xp // LEVEL_SIZE + 1, 1),
            }
        )
    return sorted(rows, key=lambda row: (row["total_xp"], row["level"], row["name"].lower()), reverse=True)[:10]


def build_semester_map(username):
    tasks = database.get_tasks_for_username(username)
    subjects = {}
    for task in tasks:
        subject = (task.get("subject") or "Unsorted").strip() or "Unsorted"
        if subject not in subjects:
            subjects[subject] = {"subject": subject, "total": 0, "completed": 0, "boss_fights": 0}
        subjects[subject]["total"] += 1
        if task.get("status") == "completed":
            subjects[subject]["completed"] += 1
        title = (task.get("title") or "").lower()
        priority = (task.get("priority") or "").lower()
        if "exam" in title or "test" in title or priority == "high":
            subjects[subject]["boss_fights"] += 1

    missions = []
    for subject in sorted(subjects.values(), key=lambda row: row["subject"].lower()):
        total = max(subject["total"], 1)
        completion = subject["completed"] / total
        missions.append({
            **subject,
            "completion_percent": round(completion * 100),
            "unlocked": completion > 0 or subject["completed"] == 0,
            "cleared": subject["completed"] == subject["total"] and subject["total"] > 0,
        })
    return missions
