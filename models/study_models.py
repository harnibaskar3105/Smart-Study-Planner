from dataclasses import dataclass


@dataclass(frozen=True)
class WeakTopic:
    subject: str
    topic: str
    average_rating: float
    avoid_count: int
    priority_score: float


@dataclass(frozen=True)
class SubjectPerformance:
    subject: str
    average_rating: float
    weak_sessions: int
    completed_tasks: int
    total_tasks: int
    study_minutes: int

