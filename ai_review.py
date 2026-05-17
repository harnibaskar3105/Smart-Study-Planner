import json
import importlib
import os
import re

import study_timetable


QUIZ_FORMAT_VERSION = 7

NOISE_PATTERNS = (
    "prepared by",
    "page ",
    "class ",
    "subject:",
    "date:",
    "website",
    "share",
    "follow",
    "subscribe",
    "contact",
    "social media",
)

STOP_WORDS = {
    "there", "their", "these", "those", "which", "about", "after", "before", "other",
    "between", "because", "during", "where", "while", "could", "would", "should",
    "study", "notes", "final", "revision", "recap", "topic", "session", "important",
    "explain", "define", "state", "point", "process", "system", "method", "used",
    "designed", "groups", "identifies", "includes", "analysis", "term", "whole",
    "it", "this", "that", "these", "those",
    "what",
}


def _normalize_space(text):
    return " ".join((text or "").split()).strip()


def _clean_line(text):
    compact = _normalize_space(text)
    compact = re.sub(r"^\[Page\s+\d+\]\s*$", "", compact, flags=re.IGNORECASE)
    compact = compact.strip(" -|,;")
    return compact


def _is_noise(text):
    lowered = text.lower()
    if not lowered:
        return True
    if any(pattern in lowered for pattern in NOISE_PATTERNS):
        return True
    if lowered.startswith("[page "):
        return True
    return False


def _is_heading(text):
    compact = _normalize_space(text).strip(":")
    if len(compact) < 4 or len(compact) > 90:
        return False
    lowered = compact.lower()
    if _is_noise(compact):
        return False
    if re.match(r"^(module|unit|chapter)\s*[-:\.]?\s*[ivxlcdm\d]+", compact, flags=re.IGNORECASE):
        return True
    if re.match(r"^what\s+is\s+.+\?$", compact, flags=re.IGNORECASE):
        return True
    if compact.endswith(":") and len(compact.split()) <= 6:
        return True
    if compact.istitle() and len(compact.split()) <= 8 and not compact.endswith("."):
        return True
    heading_keywords = (
        "overview", "architecture", "technology", "security", "cyberspace",
        "internet", "communication", "web", "protocols",
    )
    return len(compact.split()) <= 8 and any(word in lowered for word in heading_keywords) and not compact.endswith(".")


def _attached_notes_text(task):
    path = (task.get("notes_path") or "").strip()
    if not path or not os.path.isfile(path):
        return ""
    _pages, text, err = study_timetable.load_notes_pages_and_text(path)
    if err:
        return ""
    return text[:30000]


def _task_learning_text(task):
    chunks = []
    attached = _attached_notes_text(task)
    if attached:
        chunks.append(attached)
    for key in ("notes", "study_plan"):
        value = (task.get(key) or "").strip()
        if value:
            chunks.append(value)
    return "\n\n".join(chunks).strip()


def _extract_segments(task):
    source = _task_learning_text(task)
    if not source:
        source = (task.get("title") or "").strip()
    lines = [_clean_line(line) for line in source.splitlines()]
    lines = [line for line in lines if line and not _is_noise(line)]

    segments = []
    current_heading = task.get("title") or "Topic"
    current_lines = []

    def flush_segment():
        if current_lines:
            segments.append({
                "heading": current_heading,
                "text": _normalize_space(" ".join(current_lines)),
            })

    for line in lines:
        if _is_heading(line):
            flush_segment()
            current_heading = line.strip(":")
            current_lines = []
            continue
        current_lines.append(line)

    flush_segment()
    return [segment for segment in segments if len(segment["text"]) >= 30]


def _extract_facts(task):
    segments = _extract_segments(task)
    facts = []
    seen = set()

    def add_fact(concept, answer, question, kind="short_answer", options=None, helper=""):
        concept = _normalize_space(concept)
        answer = _normalize_space(answer)
        question = _normalize_space(question)
        helper = _normalize_space(helper)
        if not concept or not answer or not question:
            return
        key = (concept.lower(), answer.lower(), question.lower())
        if key in seen:
            return
        seen.add(key)
        facts.append({
            "concept": concept,
            "answer": answer,
            "question": question,
            "type": kind,
            "options": options or [],
            "helper": helper,
        })

    for segment in segments:
        heading = segment["heading"]
        text = segment["text"]
        sentences = [
            _normalize_space(part)
            for part in re.split(r"(?<=[.!?])\s+", text)
            if len(_normalize_space(part)) >= 25
        ]
        if not sentences:
            continue

        intro = sentences[0]
        intro_question = re.match(r"^What\s+is\s+(.+?)\?\s*(.+)$", intro, flags=re.IGNORECASE)
        if intro_question:
            concept = _normalize_space(intro_question.group(1))
            definition_sentence = _normalize_space(intro_question.group(2))
            if definition_sentence:
                add_fact(
                    concept,
                    definition_sentence,
                    f"What is {concept}?",
                )

        question_heading = re.match(r"^What\s+is\s+(.+?)\?$", heading, flags=re.IGNORECASE)
        if question_heading:
            concept = _normalize_space(question_heading.group(1))
            definition_sentence = next(
                (
                    sentence for sentence in sentences
                    if re.search(rf"\b{re.escape(concept)}\b\s+is\b", sentence, flags=re.IGNORECASE)
                ),
                intro,
            )
            add_fact(
                concept,
                definition_sentence,
                f"What is {concept}?",
            )
            continue

        define_heading = re.match(r"^Defining\s+(.+)$", heading, flags=re.IGNORECASE)
        if define_heading:
            concept = _normalize_space(define_heading.group(1))
            definition_sentence = next(
                (
                    sentence for sentence in sentences
                    if re.search(rf"\b{re.escape(concept)}\b\s+is\b", sentence, flags=re.IGNORECASE)
                ),
                sentences[min(1, len(sentences) - 1)],
            )
            add_fact(
                concept,
                definition_sentence,
                f"What is {concept}?",
            )
        elif heading and not re.match(r"^(module|unit|chapter|overview of)\b", heading, flags=re.IGNORECASE):
            if not re.search(r"\b1\.\s", intro):
                add_fact(
                    heading,
                    intro,
                    f"Define {heading}.",
                )

        coined = re.search(r"The term\s+(.+?)\s+was first coined by\s+(.+?)\s+in the year\s+(\d{4})", text, flags=re.IGNORECASE)
        if coined:
            concept = _normalize_space(coined.group(1))
            person = _normalize_space(coined.group(2))
            year = coined.group(3)
            add_fact(
                concept,
                f"{person} in {year}.",
                f"Who first coined the term {concept}, and in which year?",
            )

        for match in re.finditer(r"([A-Za-z][A-Za-z0-9 /\-()]+?)\s+is\s+(.+?)(?:\.|$)", text, flags=re.IGNORECASE):
            concept = _normalize_space(match.group(1)).strip(":")
            definition = _normalize_space(match.group(2)).strip(".")
            if concept.lower().startswith("what "):
                continue
            if len(concept.split()) <= 7 and len(definition) >= 18 and len(definition) <= 220 and concept.lower() not in STOP_WORDS:
                add_fact(
                    concept,
                    f"{concept} is {definition}.",
                    f"What is {concept}?",
                )
                break

        purpose_match = re.search(r"The primary purpose of\s+(.+?)\s+is to\s+(.+?)(?:\.|$)", text, flags=re.IGNORECASE)
        if purpose_match:
            subject = _normalize_space(purpose_match.group(1))
            purpose = _normalize_space(purpose_match.group(2))
            add_fact(
                subject,
                purpose + ".",
                f"What is the primary purpose of {subject}?",
            )

        process_match = re.search(r"(.+?)\s+(?:works|operates|functions)\s+by\s+(.+?)(?:\.|$)", text, flags=re.IGNORECASE)
        if process_match:
            concept = _normalize_space(process_match.group(1))
            explanation = _normalize_space(process_match.group(2))
            if len(concept.split()) <= 8 and len(explanation) >= 18:
                add_fact(
                    concept,
                    f"{concept} works by {explanation}.",
                    f"How does {concept} work?",
                )

        component_match = re.search(r"(.+?)\s+(?:includes|consists of|contains)\s+(.+?)(?:\.|$)", text, flags=re.IGNORECASE)
        if component_match:
            concept = _normalize_space(component_match.group(1))
            parts = _normalize_space(component_match.group(2))
            if len(concept.split()) <= 8 and len(parts) >= 12:
                add_fact(
                    concept,
                    parts + ".",
                    f"What are the main parts or components of {concept}?",
                )

        advantage_match = re.search(r"(?:advantages|benefits)\s+of\s+(.+?)\s+(?:include|are)\s+(.+?)(?:\.|$)", text, flags=re.IGNORECASE)
        if advantage_match:
            concept = _normalize_space(advantage_match.group(1))
            benefits = _normalize_space(advantage_match.group(2))
            add_fact(
                concept,
                benefits + ".",
                f"What are the advantages of {concept}?",
            )

        for line in text.split("  "):
            compact = _normalize_space(line)
            numbered = re.match(r"(\d+)\.\s*([^:]{2,50}):\s*(.+)", compact)
            if numbered:
                label = _normalize_space(numbered.group(2))
                detail = _normalize_space(numbered.group(3))
                if len(detail) >= 18:
                    add_fact(
                        label,
                        f"{label}: {detail}",
                        f"What is {label} in the context of {heading}?",
                    )

        colon_line = re.match(r"([^:]{3,50}):\s*(.+)", intro)
        if colon_line:
            concept = _normalize_space(colon_line.group(1))
            detail = _normalize_space(colon_line.group(2))
            if len(detail) >= 18:
                add_fact(
                    concept,
                    detail,
                    f"Write a short note on {concept}.",
                )

        for sentence in sentences[:8]:
            compact = _normalize_space(sentence)
            if len(compact) < 45 or len(compact) > 240:
                continue
            nouns = re.findall(r"\b[A-Z][A-Za-z0-9/\-]{3,}(?:\s+[A-Z][A-Za-z0-9/\-]{2,}){0,4}\b", compact)
            concept = _normalize_space(nouns[0]) if nouns else _normalize_space(heading)
            if not concept or concept.lower() in STOP_WORDS:
                continue
            add_fact(
                concept,
                compact,
                f"Explain this concept from the notes: {concept}.",
            )

    return facts[:20]


def _build_quiz_items(task):
    facts = _extract_facts(task)
    if not facts:
        base = _normalize_space(task.get("title") or "this topic")
        source = _normalize_space(_task_learning_text(task))
        summary = source[:220].rstrip(".") + "." if source else f"{base} should be explained from the study material."
        prompts = [
            ("short_answer", f"Define {base}.", summary, []),
            ("short_answer", f"Write the main idea of {base}.", summary, []),
            ("short_answer", f"List one important point from {base}.", summary, []),
            ("true_false", f"True or False: {base} is part of this study task.", "True", ["True", "False"]),
            ("short_answer", f"Why is {base} important to revise?", f"Because it is part of the planned study material for {base}.", []),
            ("short_answer", f"Name one topic or keyword connected with {base}.", base, []),
            ("short_answer", f"Summarize {base} in one sentence.", summary, []),
            ("short_answer", f"What should you remember before closing {base}?", summary, []),
        ]
        return [
            {
                "type": kind,
                "question": f"{index}. {question}",
                "answer": answer,
                "helper": "",
                "options": options,
            }
            for index, (kind, question, answer, options) in enumerate(prompts, start=1)
        ]

    preferred = [
        fact for fact in facts
        if not re.search(r"^(overview of|defining)\b", fact["concept"], flags=re.IGNORECASE)
    ]
    pool = preferred or facts
    blankable = [
        fact for fact in pool
        if len(fact["concept"]) > 2
        and fact["concept"].lower() not in STOP_WORDS
        and len(fact["answer"]) <= 180
        and re.search(rf"\b{re.escape(fact['concept'])}\b", fact["answer"], flags=re.IGNORECASE)
    ]
    true_false_candidates = [
        fact for fact in pool
        if re.search(r"\b(is|are|was|were|includes|consists|refers|protect)\b", fact["answer"], flags=re.IGNORECASE)
        and len(fact["answer"]) >= 35
    ]

    selected = []
    used = set()

    def take(source):
        for fact in source:
            key = (fact["concept"], fact["answer"])
            if key not in used:
                used.add(key)
                return fact
        return None

    layout = [
        ("short", pool),
        ("short", pool),
        ("blank", blankable),
        ("true_false", true_false_candidates),
        ("short", pool),
        ("short", pool),
        ("true_false", true_false_candidates),
        ("blank", blankable),
    ]
    for kind, source in layout:
        fact = take(source) or take(pool)
        if fact:
            selected.append((kind, fact))
    quiz = []
    for index, entry in enumerate(selected, start=1):
        kind, fact = entry
        if kind == "true_false":
            statement = fact["answer"]
            if len(statement) > 150:
                statement = statement[:147].rstrip() + "..."
            quiz.append({
                "type": "true_false",
                "question": f"{index}. True or False: {statement}",
                "answer": "True",
                "helper": "",
                "options": ["True", "False"],
            })
        elif kind == "blank":
            answer = fact["concept"]
            pattern = re.escape(answer)
            blanked = re.sub(pattern, "______", fact["answer"], count=1, flags=re.IGNORECASE)
            if blanked == fact["answer"]:
                quiz.append({
                    "type": "short_answer",
                    "question": f"{index}. Write the correct term for this description.",
                    "answer": answer,
                    "helper": fact["answer"],
                    "options": [],
                })
            else:
                quiz.append({
                    "type": "short_answer",
                    "question": f"{index}. Fill in the blank: {blanked}",
                    "answer": answer,
                    "helper": "",
                    "options": [],
                })
        else:
            quiz.append({
                "type": "short_answer",
                "question": f"{index}. {fact['question']}",
                "answer": fact["answer"],
                "helper": "",
                "options": [],
            })

    while len(quiz) < 8:
        fallback = pool[len(quiz) % len(pool)]
        index = len(quiz) + 1
        quiz.append({
            "type": "short_answer",
            "question": f"{index}. {fallback['question']}",
            "answer": fallback["answer"],
            "helper": "",
            "options": [],
        })

    return quiz[:8]


def _sanitize_item(item, index):
    question = _normalize_space(item.get("question"))
    answer = _normalize_space(item.get("answer"))
    if not question or not answer:
        return None

    question_type = _normalize_space(item.get("type") or "short_answer").lower()
    if question_type not in {"multiple_choice", "short_answer", "true_false"}:
        question_type = "short_answer"

    sanitized = {
        "type": question_type,
        "question": question if re.match(r"^\d+\.", question) else f"{index}. {question}",
        "answer": answer,
        "helper": _normalize_space(item.get("helper")),
    }

    if question_type in {"multiple_choice", "true_false"}:
        options = []
        seen = set()
        for option in item.get("options") or []:
            compact = _normalize_space(option)
            lowered = compact.lower()
            if compact and lowered not in seen:
                seen.add(lowered)
                options.append(compact)
        if question_type == "true_false":
            options = ["True", "False"]
        elif answer.lower() not in {option.lower() for option in options}:
            options.insert(0, answer)
        sanitized["options"] = options[:4]
    else:
        sanitized["options"] = []
    return sanitized


def _pack_quiz_result(items, source):
    payload = {"version": QUIZ_FORMAT_VERSION, "quiz": items}
    return "", json.dumps(payload, ensure_ascii=False), source


def _local_quiz_pack(task):
    items = []
    for index, item in enumerate(_build_quiz_items(task), start=1):
        sanitized = _sanitize_item(item, index)
        if sanitized:
            items.append(sanitized)
    return _pack_quiz_result(items, "local")


def _task_source_text(task):
    chunks = []
    attached = _attached_notes_text(task)
    if attached:
        chunks.append(f"Attached Notes Content: {attached}")
    for key in ["title", "subject", "notes", "study_plan"]:
        value = (task.get(key) or "").strip()
        if value:
            chunks.append(f"{key.title()}: {value}")
    return "\n\n".join(chunks)


def _ai_quiz_pack(task):
    try:
        OpenAI = getattr(importlib.import_module("openai"), "OpenAI")
    except (ImportError, AttributeError):
        return None

    if not os.getenv("OPENAI_API_KEY"):
        return None

    client = OpenAI()
    content = _task_source_text(task)
    if not content:
        return None

    prompt = f"""
You are an experienced teacher creating a revision quiz in the style of a clear Google Form after a lesson.

Return strict JSON with this shape:
{{
  "quiz": [
    {{
      "type": "multiple_choice" | "short_answer" | "true_false",
      "question": "1. ...",
      "options": ["...", "...", "...", "..."],
      "answer": "...",
      "helper": "optional short context line"
    }}
  ]
}}

Requirements:
- Read the study content carefully and write relevant questions from the actual concepts in it.
- Prefer definitions, named components, purposes, years, protocols, and architecture points when present.
- Ignore filler, credits, page labels, and OCR junk.
- Create exactly 8 questions.
- Use a clear teacher tone, like a proper Google Form.
- Keep questions specific, not generic.
- Do not use vague matching questions like "Which term matches this description?".
- Use this mix: 6 short-answer, 2 true/false.
- Do not include markdown fences.

Study content:
{content[:18000]}
""".strip()

    response = client.responses.create(
        model="gpt-5",
        input=prompt,
    )
    raw = (response.output_text or "").strip()
    if not raw:
        return None

    data = json.loads(raw)
    items = []
    for index, item in enumerate(data.get("quiz", [])[:8], start=1):
        sanitized = _sanitize_item(item, index)
        if sanitized:
            items.append(sanitized)

    if len(items) < 8:
        return None
    return _pack_quiz_result(items, "openai")


def generate_review_pack(task):
    try:
        ai_result = _ai_quiz_pack(task)
        if ai_result:
            return ai_result
    except Exception:
        pass
    return _local_quiz_pack(task)
