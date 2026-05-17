from collections import defaultdict

import database


LOW_RATING_THRESHOLD = 2
AVOIDED_STATUSES = {"skipped", "postponed"}


class WeaknessAnalyzer:
    """Turns task and session history into revision recommendations."""

    def __init__(self, username):
        self.username = username

    def analyze(self):
        sessions = database.get_study_sessions_for_username(self.username)
        tasks = database.get_tasks_for_username(self.username)
        subject_stats = defaultdict(lambda: {
            "ratings": [],
            "weak_sessions": 0,
            "minutes": 0,
            "avoids": 0,
        })
        topic_stats = defaultdict(lambda: {
            "subject": "Unsorted",
            "ratings": [],
            "weak_sessions": 0,
            "avoids": 0,
            "minutes": 0,
        })

        for session in sessions:
            subject = (session.get("subject") or "Unsorted").strip() or "Unsorted"
            topic = (session.get("topic") or "General").strip() or "General"
            rating = session.get("understanding_rating")
            status = (session.get("completion_status") or "completed").lower()
            minutes = int(session.get("study_minutes") or 0)

            subject_stats[subject]["minutes"] += minutes
            topic_key = (subject, topic)
            topic_stats[topic_key]["subject"] = subject
            topic_stats[topic_key]["minutes"] += minutes

            if rating:
                rating = int(rating)
                subject_stats[subject]["ratings"].append(rating)
                topic_stats[topic_key]["ratings"].append(rating)
                if rating <= LOW_RATING_THRESHOLD:
                    subject_stats[subject]["weak_sessions"] += 1
                    topic_stats[topic_key]["weak_sessions"] += 1

            if status in AVOIDED_STATUSES:
                subject_stats[subject]["avoids"] += 1
                topic_stats[topic_key]["avoids"] += 1

        task_subject_counts = defaultdict(lambda: {"total": 0, "completed": 0, "postponed": 0})
        for task in tasks:
            subject = (task.get("subject") or "Unsorted").strip() or "Unsorted"
            task_subject_counts[subject]["total"] += 1
            if task.get("status") == "completed":
                task_subject_counts[subject]["completed"] += 1
            postponed = int(task.get("postponed_count") or 0)
            task_subject_counts[subject]["postponed"] += postponed
            if postponed:
                subject_stats[subject]["avoids"] += postponed
                topic_key = (subject, task.get("title") or "Untitled task")
                topic_stats[topic_key]["subject"] = subject
                topic_stats[topic_key]["avoids"] += postponed

        subject_performance = self._build_subject_performance(subject_stats, task_subject_counts)
        weak_topics = self._build_topic_scores(topic_stats)
        weakest_subject = subject_performance[0]["subject"] if subject_performance else "No data yet"
        most_avoided_topic = weak_topics[0]["topic"] if weak_topics else "No avoided topic yet"

        return {
            "weakest_subject": weakest_subject,
            "most_avoided_topic": most_avoided_topic,
            "improvement_trend": self._trend_text(sessions),
            "recommended_tasks": self._recommendations(weak_topics, subject_performance),
            "weak_topics": weak_topics,
            "subject_performance": subject_performance,
            "session_count": len(sessions),
        }

    def _build_subject_performance(self, subject_stats, task_subject_counts):
        rows = []
        all_subjects = set(subject_stats) | set(task_subject_counts)
        for subject in all_subjects:
            ratings = subject_stats[subject]["ratings"]
            avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0
            tasks = task_subject_counts[subject]
            total_tasks = tasks["total"]
            completed_tasks = tasks["completed"]
            completion_rate = (completed_tasks / total_tasks) if total_tasks else 0
            risk_score = (
                (5 - avg_rating if avg_rating else 2.5)
                + subject_stats[subject]["weak_sessions"] * 1.4
                + subject_stats[subject]["avoids"] * 1.1
                + (1 - completion_rate) * 1.5
            )
            rows.append({
                "subject": subject,
                "average_rating": avg_rating,
                "weak_sessions": subject_stats[subject]["weak_sessions"],
                "completed_tasks": completed_tasks,
                "total_tasks": total_tasks,
                "study_minutes": subject_stats[subject]["minutes"],
                "completion_rate": round(completion_rate * 100),
                "risk_score": round(risk_score, 2),
            })
        return sorted(rows, key=lambda row: row["risk_score"], reverse=True)

    def _build_topic_scores(self, topic_stats):
        rows = []
        for (subject, topic), stats in topic_stats.items():
            ratings = stats["ratings"]
            avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0
            low_rating_weight = (5 - avg_rating) if avg_rating else 1.5
            score = low_rating_weight + stats["weak_sessions"] * 2 + stats["avoids"] * 2.5
            if score <= 1.5:
                continue
            rows.append({
                "subject": subject,
                "topic": topic,
                "average_rating": avg_rating,
                "weak_sessions": stats["weak_sessions"],
                "avoid_count": stats["avoids"],
                "study_minutes": stats["minutes"],
                "priority_score": round(score, 2),
            })
        return sorted(rows, key=lambda row: row["priority_score"], reverse=True)

    def _trend_text(self, sessions):
        rated = [int(row["understanding_rating"]) for row in reversed(sessions) if row.get("understanding_rating")]
        if len(rated) < 2:
            return "Add two rated sessions to see a trend."
        midpoint = max(len(rated) // 2, 1)
        earlier = rated[:midpoint]
        recent = rated[midpoint:]
        earlier_avg = sum(earlier) / len(earlier)
        recent_avg = sum(recent) / len(recent)
        delta = recent_avg - earlier_avg
        if delta >= 0.4:
            return f"Improving: recent understanding is up by {delta:.1f} points."
        if delta <= -0.4:
            return f"Needs attention: recent understanding is down by {abs(delta):.1f} points."
        return "Stable: ratings are holding steady."

    def _recommendations(self, weak_topics, subject_performance):
        recommendations = []
        for topic in weak_topics[:5]:
            recommendations.append(
                f"Revise {topic['subject']} - {topic['topic']} for 30 minutes, then rate understanding again."
            )
        if not recommendations:
            for subject in subject_performance[:3]:
                recommendations.append(f"Schedule one focused revision block for {subject['subject']}.")
        return recommendations or ["Complete a study session to unlock recommendations."]
