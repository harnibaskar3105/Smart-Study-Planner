"""
Generate a suggested study timetable from attached notes and a date range.
Output is JSON-serializable for storage in tasks.study_plan.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
from typing import Any


def _count_words(text: str) -> int:
    if not text:
        return 0
    return len(re.findall(r"\w+", text, flags=re.UNICODE))


def _read_pdf_pages_and_text(path: str) -> tuple[int, str]:
    from PyPDF2 import PdfReader

    reader = PdfReader(path)
    n = len(reader.pages)
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return n, "\n".join(parts)


def _read_docx_text(path: str) -> tuple[int, str]:
    from docx import Document

    doc = Document(path)
    blob = "\n".join(p.text for p in doc.paragraphs)
    w = _count_words(blob)
    pages = max(1, round(w / 280)) if w else 1
    return pages, blob


def _read_plain_text(path: str) -> tuple[int, str]:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        blob = f.read()
    w = _count_words(blob)
    pages = max(1, round(w / 350)) if w else 1
    return pages, blob


def load_notes_pages_and_text(path: str) -> tuple[int, str, str | None]:
    """Return (page_count, full_text_or_sample, error)."""
    ext = os.path.splitext(path or "")[1].lower()
    try:
        if ext == ".pdf":
            return (*_read_pdf_pages_and_text(path), None)
        if ext == ".docx":
            return (*_read_docx_text(path), None)
        return (*_read_plain_text(path), None)
    except Exception as exc:
        return 1, "", str(exc)


def _daterange_inclusive(start: date, end: date) -> list[date]:
    days = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    return days


def _split_page_ranges(total_pages: int, n_days: int) -> list[tuple[int, int]]:
    """Split real page numbers across n_days; pad virtually so every day gets a slice."""
    total_pages = max(1, int(total_pages))
    n_days = max(1, int(n_days))
    effective = max(total_pages, n_days)
    base, rem = divmod(effective, n_days)
    ranges = []
    page = 1
    for i in range(n_days):
        take = base + (1 if i < rem else 0)
        if take == 0:
            lo, hi = page, page - 1
        else:
            lo, hi = page, page + take - 1
            page = hi + 1
        lo_c = max(1, min(lo, total_pages))
        hi_c = max(lo_c, min(hi, total_pages))
        ranges.append((lo_c, hi_c))
    return ranges


def _extract_topic_candidates(text: str, max_topics: int) -> list[str]:
    if not text.strip():
        return []
    sample = text[:12000]
    seen = set()
    candidates = []

    for line in sample.splitlines():
        s = line.strip()
        if len(s) < 4 or len(s) > 72:
            continue
        if re.match(r"^[\d\s.\-–—]+$", s):
            continue
        m = re.match(r"^(\d+[\.)])\s*(.+)$", s)
        if m:
            s = m.group(2).strip()
        if s in seen:
            continue
        if len(s.split()) > 14:
            continue
        if s.islower() and len(s) < 12:
            continue
        seen.add(s)
        candidates.append(s[:68])
        if len(candidates) >= max_topics:
            break

    return candidates


def _fallback_topics(n: int, subject: str) -> list[str]:
    sub = (subject or "Topic").strip() or "Topic"
    base = [
        "Introduction",
        "Core concepts",
        "Practice & examples",
        "Advanced topics",
        "Review & applications",
        "Data selection",
        "Data mining",
        "Online analytical processing",
        "Algorithms",
        "Case study",
        "Assessment prep",
    ]
    out = []
    for i in range(n):
        if i < len(base):
            out.append(base[i])
        else:
            out.append(f"{sub} — block {i + 1}")
    return out


def parse_storage_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _build_timetable_from_content(
    pages_total: int,
    text: str,
    page_label_prefix: str,
    start: date,
    end: date,
    task_title: str,
    subject: str,
) -> dict[str, Any]:
    if start > end:
        start, end = end, start

    day_dates = _daterange_inclusive(start, end)
    n = len(day_dates)
    ranges = _split_page_ranges(pages_total, n)

    topics = _extract_topic_candidates(text, max_topics=max(n, 8))
    if len(topics) < n:
        topics.extend(_fallback_topics(n, subject))
    topics = topics[:n]

    raw_hours = pages_total * 0.22 / max(n, 1)
    session_hours = max(1.0, min(2.5, round(raw_hours * 2) / 2))
    if abs(session_hours - 1.7) < 0.15:
        session_hours = 1.7

    sessions = []
    for i, d in enumerate(day_dates):
        lo, hi = ranges[i] if i < len(ranges) else (1, 1)
        if hi < lo:
            continue
        unit_num = i // 3 + 1
        sessions.append({
            "day_index": i + 1,
            "date": d.strftime("%d-%m-%Y"),
            "unit": f"Unit {unit_num}",
            "task": topics[i] if i < len(topics) else f"Session {i + 1}",
            "pages": f"{page_label_prefix} {lo}-{hi}",
            "hours": float(session_hours),
        })

    total_h = round(sum(s["hours"] for s in sessions), 1)
    summary = (
        f"Estimated effort: {total_h} hour(s) across {len(sessions)} practical session(s), "
        f"based on the extracted notes size. It fits within {len(sessions)} day(s) "
        f"from {day_dates[0].strftime('%d-%m-%Y')} to {day_dates[-1].strftime('%d-%m-%Y')}."
    )

    return {
        "version": 1,
        "type": "study_planner_timetable",
        "summary": summary,
        "sessions": sessions,
        "pages_total": pages_total,
        "words_approx": _count_words(text),
    }


def generate_timetable(
    notes_path: str,
    start: date,
    end: date,
    task_title: str,
    subject: str,
) -> dict[str, Any]:
    """
    Build timetable dict: summary, sessions (day index, date, unit, task, pages label, hours).
    """
    pages_total, text, err = load_notes_pages_and_text(notes_path)
    if err:
        return {"error": err, "summary": "", "sessions": []}

    ext = os.path.splitext(notes_path)[1].lower()
    page_label_prefix = "PDF pages" if ext == ".pdf" else "Pages"
    return _build_timetable_from_content(pages_total, text, page_label_prefix, start, end, task_title, subject)


def generate_timetable_from_text(
    notes_text: str,
    start: date,
    end: date,
    task_title: str,
    subject: str,
) -> dict[str, Any]:
    words = _count_words(notes_text)
    pages_total = max(1, round(words / 350)) if words else 1
    return _build_timetable_from_content(pages_total, notes_text or task_title, "Notes pages", start, end, task_title, subject)


def plan_to_json(plan: dict[str, Any]) -> str:
    return json.dumps(plan, ensure_ascii=False, indent=2)


def parse_plan_json(raw: str | None) -> dict[str, Any] | None:
    if not raw or not raw.strip():
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("type") == "study_planner_timetable" and "sessions" in data:
            return data
    except json.JSONDecodeError:
        pass
    return None


def plan_plain_lines(plan: dict[str, Any]) -> str:
    lines = [plan.get("summary") or "", ""]
    for s in plan.get("sessions") or []:
        lines.append(
            f"Day {s.get('day_index')} | {s.get('date')} | {s.get('unit')} | {s.get('task')} | "
            f"{s.get('pages')} | {s.get('hours')} h"
        )
    return "\n".join(lines)
