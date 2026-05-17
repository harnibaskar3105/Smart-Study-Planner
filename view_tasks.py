import os
import subprocess
import sys
import json
import calendar
from datetime import datetime
from tkinter import ttk

import customtkinter as ctk
from PIL import Image, UnidentifiedImageError

import ai_review
import database
from gamification.xp_system import XPSystem
from theme_manager import get_theme_colors, load_theme as global_load_theme, save_theme as global_save_theme
from ui.modern import make_app_shell, style_treeview
from tk_safety import disable_unsafe_windows_titlebar_focus_restore

disable_unsafe_windows_titlebar_focus_restore()

THEME_FILE = "theme.txt"

VIEW_TASKS_SUBTITLE = "Create, complete, and remove tasks without leaving the main window."

LIGHT = {
    "bg": "#f7f2fb",
    "backdrop": "#f2ebf8",
    "backdrop_border": "#ddd0ea",
    "accent_line": "#90d8d0",
    "panel": "#ffffff",
    "panel_border": "#dfd4ea",
    "surface": "#fbf8fe",
    "surface_border": "#e1d8ec",
    "text": "#30253f",
    "muted": "#756785",
    "primary": "#78c8c1",
    "primary_hover": "#61b8b0",
    "secondary": "#ece0f6",
    "secondary_hover": "#e1d1f1",
    "secondary_text": "#493b5e",
    "danger": "#d98da8",
    "danger_hover": "#c77394",
    "header": "#f7f1fb",
    "header_border": "#dfd4ea",
}

DARK = {
    "bg": "#161120",
    "backdrop": "#1d1830",
    "backdrop_border": "#3a3150",
    "accent_line": "#73c8bf",
    "panel": "#211a31",
    "panel_border": "#3c3250",
    "surface": "#291f3b",
    "surface_border": "#47385d",
    "text": "#f8f3ff",
    "muted": "#b8abc9",
    "primary": "#4f9f98",
    "primary_hover": "#468d87",
    "secondary": "#332745",
    "secondary_hover": "#403055",
    "secondary_text": "#eadff8",
    "danger": "#a86f86",
    "danger_hover": "#965f76",
    "header": "#1c152b",
    "header_border": "#342946",
}


def load_theme():
    return global_load_theme()


def palette(theme=None):
    return get_theme_colors()


def load_image(path, size):
    try:
        return ctk.CTkImage(Image.open(path), size=size)
    except (FileNotFoundError, UnidentifiedImageError):
        return None


def maximize_window(window):
    if not window.winfo_exists():
        return
    try:
        window.state("normal")
        window.state("zoomed")
    except Exception:
        try:
            width = window.winfo_screenwidth()
            height = window.winfo_screenheight()
            window.geometry(f"{width}x{height}+0+0")
            window.state("normal")
        except Exception:
            pass


def reveal_window(window):
    maximize_window(window)
    try:
        window.attributes("-alpha", 1.0)
    except Exception:
        pass


def center_modal(window, parent, width=480, height=240):
    window.update_idletasks()
    parent.update_idletasks()
    parent_x = parent.winfo_rootx()
    parent_y = parent.winfo_rooty()
    parent_width = max(parent.winfo_width(), 1)
    parent_height = max(parent.winfo_height(), 1)
    x = parent_x + max((parent_width - width) // 2, 0)
    y = parent_y + max((parent_height - height) // 2, 0)
    window.geometry(f"{width}x{height}+{x}+{y}")


def show_app_dialog(title, message, kind="info", confirm=False):
    colors = palette()
    accent_map = {
        "info": colors["primary"],
        "success": colors["primary"],
        "warning": "#d7a14d" if current_theme == "light" else "#e0b15a",
        "error": colors["danger"],
    }
    accent = accent_map.get(kind, colors["primary"])
    result = {"value": False}

    modal = ctk.CTkToplevel(app)
    modal.title(title)
    modal.resizable(False, False)
    modal.transient(app)
    modal.grab_set()
    modal.configure(fg_color=colors["bg"])
    center_modal(modal, app, width=520, height=280 if "\n" in message else 230)

    panel = ctk.CTkFrame(
        modal,
        fg_color=colors["panel"],
        border_color=colors["panel_border"],
        border_width=1,
        corner_radius=22,
    )
    panel.pack(fill="both", expand=True, padx=16, pady=16)

    ctk.CTkLabel(panel, text=title, font=("Verdana", 22, "bold"), text_color=colors["text"]).pack(anchor="center", pady=(22, 10))
    ctk.CTkFrame(panel, fg_color=accent, height=4, corner_radius=999).pack(fill="x", padx=36, pady=(0, 16))
    ctk.CTkLabel(
        panel,
        text=message,
        font=("Verdana", 14),
        text_color=colors["muted"],
        wraplength=410,
        justify="center",
    ).pack(expand=True, padx=28, pady=(0, 16))

    actions = ctk.CTkFrame(panel, fg_color="transparent")
    actions.pack(fill="x", padx=24, pady=(0, 20))
    actions.grid_columnconfigure((0, 1), weight=1)

    if confirm:
        def confirm_action():
            result["value"] = True
            modal.destroy()

        ctk.CTkButton(
            actions,
            text="Cancel",
            height=42,
            corner_radius=14,
            fg_color=colors["secondary"],
            hover_color=colors["secondary_hover"],
            text_color=colors["secondary_text"],
            command=modal.destroy,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(
            actions,
            text="Confirm",
            height=42,
            corner_radius=14,
            fg_color=accent,
            hover_color=colors["danger_hover"] if kind == "error" else accent,
            text_color="#ffffff",
            command=confirm_action,
        ).grid(row=0, column=1, sticky="ew", padx=(8, 0))
    else:
        ctk.CTkButton(
            actions,
            text="OK",
            height=42,
            corner_radius=14,
            fg_color=accent,
            hover_color=colors["danger_hover"] if kind == "error" else accent,
            text_color="#ffffff",
            command=modal.destroy,
        ).grid(row=0, column=0, columnspan=2, sticky="ew")

    modal.wait_window()
    return result["value"]


def resolve_username(raw_username):
    raw_username = (raw_username or "").strip()
    if raw_username:
        user = database.get_user_by_username(raw_username)
        if user:
            return user["username"]
    latest_user = database.get_latest_user()
    if latest_user:
        return latest_user["username"]
    return raw_username or "Student"


def format_indian_date(value):
    if not value:
        return "-"
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d-%m-%Y")
    except ValueError:
        return value


def to_storage_date(value):
    value = (value or "").strip()
    if not value or value == "-":
        return None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError("Dates must be DD-MM-YYYY or YYYY-MM-DD.")


def pick_date_for_entry(target_entry):
    colors = palette()
    modal = ctk.CTkToplevel(app)
    modal.title("Choose date")
    modal.geometry("420x460")
    modal.resizable(False, False)
    modal.transient(app)
    modal.grab_set()
    modal.configure(fg_color=colors["bg"])

    frame = ctk.CTkFrame(modal, fg_color=colors["panel"], border_color=colors["panel_border"], border_width=1, corner_radius=20)
    frame.pack(fill="both", expand=True, padx=16, pady=16)

    current = datetime.today().replace(day=1)
    if target_entry.get().strip():
        for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
            try:
                current = datetime.strptime(target_entry.get().strip(), fmt).replace(day=1)
                break
            except ValueError:
                pass

    header = ctk.CTkFrame(frame, fg_color="transparent")
    header.pack(fill="x", padx=16, pady=(16, 8))
    month_label = ctk.CTkLabel(header, text="", font=("Verdana", 18, "bold"), text_color=colors["text"])
    month_label.pack(side="left")
    nav = ctk.CTkFrame(header, fg_color="transparent")
    nav.pack(side="right")
    grid_frame = ctk.CTkFrame(frame, fg_color="transparent")
    grid_frame.pack(fill="both", expand=True, padx=16, pady=(4, 8))

    def select_day(day):
        target_entry.delete(0, "end")
        target_entry.insert(0, datetime(current.year, current.month, day).strftime("%d-%m-%Y"))
        modal.destroy()

    def render():
        nonlocal current
        for child in grid_frame.winfo_children():
            child.destroy()
        month_label.configure(text=current.strftime("%B %Y"))
        for col, name in enumerate(["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]):
            ctk.CTkLabel(grid_frame, text=name, text_color=colors["muted"], font=("Verdana", 12, "bold")).grid(row=0, column=col, padx=4, pady=(0, 8))
        month = calendar.monthcalendar(current.year, current.month)
        for row_index, week in enumerate(month, start=1):
            for col_index, day in enumerate(week):
                if day == 0:
                    ctk.CTkLabel(grid_frame, text="", width=38).grid(row=row_index, column=col_index, padx=4, pady=4)
                    continue
                ctk.CTkButton(
                    grid_frame,
                    text=str(day),
                    width=38,
                    height=34,
                    corner_radius=12,
                    fg_color=colors["surface"],
                    hover_color=colors["secondary_hover"],
                    text_color=colors["text"],
                    border_width=1,
                    border_color=colors["surface_border"],
                    command=lambda chosen=day: select_day(chosen),
                ).grid(row=row_index, column=col_index, padx=4, pady=4)

    def shift(delta):
        nonlocal current
        month_value = current.month + delta
        year_value = current.year
        if month_value < 1:
            month_value = 12
            year_value -= 1
        elif month_value > 12:
            month_value = 1
            year_value += 1
        current = current.replace(year=year_value, month=month_value, day=1)
        render()

    ctk.CTkButton(nav, text="<", width=34, height=30, corner_radius=10, fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"], command=lambda: shift(-1)).pack(side="left", padx=(0, 6))
    ctk.CTkButton(nav, text=">", width=34, height=30, corner_radius=10, fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"], command=lambda: shift(1)).pack(side="left")
    footer = ctk.CTkFrame(frame, fg_color="transparent")
    footer.pack(fill="x", padx=16, pady=(0, 16))
    ctk.CTkButton(footer, text="Today", height=38, corner_radius=14, fg_color=colors["primary"], hover_color=colors["primary_hover"], command=lambda: select_day(datetime.today().day)).pack(side="left")
    ctk.CTkButton(footer, text="Cancel", height=38, corner_radius=14, fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"], command=modal.destroy).pack(side="right")
    render()


def parse_quiz_items(text):
    items = []
    raw = (text or "").strip()
    if not raw:
        return items
    if raw.startswith("{"):
        try:
            payload = json.loads(raw)
            for item in payload.get("quiz", []):
                question = (item.get("question") or "").strip()
                answer = (item.get("answer") or "").strip()
                question_type = (item.get("type") or "short_answer").strip().lower()
                options = []
                for option in item.get("options") or []:
                    compact = (option or "").strip()
                    if compact:
                        options.append(compact)
                helper = (item.get("helper") or "").strip()
                if question and answer:
                    items.append({
                        "question": question,
                        "answer": answer,
                        "type": question_type,
                        "options": options,
                        "helper": helper,
                    })
            if items:
                return items
        except Exception:
            pass
    for block in raw.split("\n\n"):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        question = lines[0]
        answer = ""
        for line in lines[1:]:
            if line.startswith("Answer:"):
                answer = line.replace("Answer:", "", 1).strip()
                break
        if question and answer:
            items.append({"question": question, "answer": answer, "type": "short_answer", "options": [], "helper": ""})
    return items


def quiz_needs_upgrade(text):
    raw = (text or "").strip()
    if not raw:
        return True
    if not raw.startswith("{"):
        return True
    try:
        payload = json.loads(raw)
    except Exception:
        return True
    if int(payload.get("version") or 0) < 7:
        return True
    items = payload.get("quiz")
    if not isinstance(items, list) or len(items) < 8:
        return True
    return any(not (item.get("type") and item.get("question") and item.get("answer")) for item in items)


def ensure_current_quiz(task_id, task):
    quiz_text = (task.get("quiz") or "").strip()
    if not quiz_needs_upgrade(quiz_text):
        return task, "Saved Google Form quiz"
    flashcards, quiz, generation_source = ai_review.generate_review_pack(task)
    database.save_task_review_materials(task_id, flashcards, quiz)
    refreshed = database.get_task_by_id(task_id)
    label = "OpenAI-generated Google Form quiz" if generation_source == "openai" else "Locally generated Google Form quiz"
    return refreshed, label


def create_review_cards(parent, items, colors, kind_label, on_answer=None, reveal_once=False):
    container = ctk.CTkScrollableFrame(parent, fg_color="transparent")
    container.pack(fill="both", expand=True, padx=12, pady=12)

    if not items:
        empty = ctk.CTkLabel(
            container,
            text=f"No {kind_label.lower()} available yet.",
            font=("Verdana", 14),
            text_color=colors["muted"],
            justify="left",
        )
        empty.pack(anchor="w", padx=8, pady=8)
        return

    card_frames = []

    def unlock_next(current_index):
        if reveal_once and current_index + 1 < len(card_frames):
            next_card = card_frames[current_index + 1]
            if not next_card.winfo_ismapped():
                next_card.pack(fill="x", padx=6, pady=8)

    for index, item in enumerate(items, start=1):
        card = ctk.CTkFrame(
            container,
            corner_radius=20,
            border_width=1,
            fg_color=colors["surface"],
            border_color=colors["surface_border"],
        )
        if not reveal_once or index == 1:
            card.pack(fill="x", padx=6, pady=8)
        card_frames.append(card)

        badge = ctk.CTkLabel(
            card,
            text=f" {kind_label} {index} ",
            font=("Verdana", 11, "bold"),
            corner_radius=999,
            fg_color=colors["primary"],
            text_color="#ffffff",
            padx=10,
            pady=5,
        )
        badge.pack(anchor="w", padx=18, pady=(16, 10))

        question_label = ctk.CTkLabel(
            card,
            text=item["question"],
            font=("Verdana", 16, "bold"),
            text_color=colors["text"],
            wraplength=720,
            justify="left",
            anchor="w",
        )
        question_label.pack(anchor="w", padx=18, pady=(0, 12))

        helper_text = (item.get("helper") or "").strip()
        if helper_text:
            helper_label = ctk.CTkLabel(
                card,
                text=helper_text,
                font=("Verdana", 12),
                text_color=colors["muted"],
                wraplength=720,
                justify="left",
                anchor="w",
            )
            helper_label.pack(anchor="w", padx=18, pady=(0, 10))

        options = item.get("options") or []
        if options:
            option_labels = "ABCD"
            for option_index, option in enumerate(options):
                option_row = ctk.CTkFrame(
                    card,
                    corner_radius=12,
                    border_width=1,
                    fg_color=colors["panel"],
                    border_color=colors["panel_border"],
                )
                option_row.pack(fill="x", padx=18, pady=(0, 8))
                prefix = option_labels[option_index] if option_index < len(option_labels) else str(option_index + 1)
                ctk.CTkLabel(
                    option_row,
                    text=f"{prefix}.",
                    font=("Verdana", 13, "bold"),
                    text_color=colors["primary"],
                    width=28,
                ).pack(side="left", padx=(12, 4), pady=10)
                ctk.CTkLabel(
                    option_row,
                    text=option,
                    font=("Verdana", 13),
                    text_color=colors["text"],
                    wraplength=640,
                    justify="left",
                    anchor="w",
                ).pack(side="left", fill="x", expand=True, padx=(0, 12), pady=10)

        answer_box = ctk.CTkFrame(
            card,
            corner_radius=16,
            border_width=1,
            fg_color=colors["panel"],
            border_color=colors["panel_border"],
        )
        answer_label = ctk.CTkLabel(
            answer_box,
            text=f"Answer: {item['answer']}",
            font=("Verdana", 14),
            text_color=colors["text"],
            wraplength=720,
            justify="left",
            anchor="w",
        )
        answer_label.pack(anchor="w", padx=14, pady=14)

        answered = {"done": False}

        answer_btn = ctk.CTkButton(
            card,
            text="Answer",
            height=38,
            width=120,
            corner_radius=14,
            fg_color=colors["secondary"],
            hover_color=colors["secondary_hover"],
            text_color=colors["secondary_text"],
        )

        def make_toggle_answer(item_idx, box, btn, answered_state):
            def toggle_answer():
                if answered_state["done"]:
                    return

                box.pack(fill="x", padx=18, pady=(0, 14))
                answered_state["done"] = True
                btn.configure(text="Answered", state="disabled")
                if callable(on_answer):
                    on_answer(item_idx)
                unlock_next(item_idx)
            return toggle_answer

        answer_btn.configure(command=make_toggle_answer(index - 1, answer_box, answer_btn, answered))
        answer_btn.pack(anchor="w", padx=18, pady=(0, 16))


def show_review_pack(task, source_label="AI quiz", complete_on_finish=False, task_id=None):
    colors = palette()

    modal = ctk.CTkToplevel(app)
    modal.title("AI Quiz")
    modal.geometry("960x720")
    modal.configure(fg_color=colors["bg"])
    modal.grab_set()

    panel = ctk.CTkFrame(modal, corner_radius=24, border_width=1,
                         fg_color=colors["panel"], border_color=colors["panel_border"])
    panel.pack(fill="both", expand=True, padx=20, pady=20)

    quiz_items = parse_quiz_items(task.get("quiz"))
    total_items = len(quiz_items)

    answered_items = set()

    ctk.CTkLabel(panel, text=f"AI Quiz: {task['title']}",
                 font=("Verdana", 24, "bold"),
                 text_color=colors["text"]).pack(anchor="w", padx=20, pady=(18, 8))

    ctk.CTkLabel(panel,
        text=f"{source_label}. The quiz is drafted like a teacher checking understanding.",
        font=("Verdana", 13),
        text_color=colors["muted"]
    ).pack(anchor="w", padx=20, pady=(0, 12))

    progress_label = ctk.CTkLabel(
        panel,
        text=f"Answered 0 of {total_items}",
        font=("Verdana", 13, "bold"),
        text_color=colors["primary"],
    )
    progress_label.pack(anchor="w", padx=20, pady=(0, 12))

    quiz_frame = ctk.CTkFrame(panel, corner_radius=18, border_width=1,
                              fg_color=colors["surface"], border_color=colors["surface_border"])
    quiz_frame.pack(fill="both", expand=True, padx=20, pady=(0, 18))

    actions = ctk.CTkFrame(panel, fg_color="transparent")
    actions.pack(fill="x", padx=20, pady=(0, 18))
    actions.grid_columnconfigure(0, weight=1)
    actions.grid_columnconfigure(1, weight=1)

    # ✅ CREATE BUTTON FIRST
    finish_btn = ctk.CTkButton(
        actions,
        text="Mark Completed" if complete_on_finish else "Done",
        height=42,
        corner_radius=14,
        fg_color=colors["primary"],
        hover_color=colors["primary_hover"],
        text_color="#ffffff",
        state="disabled"
    )
    finish_btn.grid(row=0, column=0, sticky="w")

    def handle_answer(item_index):
        answered_items.add(item_index)
        answered_count = len(answered_items)

        progress_label.configure(
            text=f"Answered {answered_count} of {total_items}"
        )

        if answered_count >= total_items:
            finish_btn.configure(state="normal")   # ✅ ENABLE BUTTON
        else:
            finish_btn.configure(state="disabled")  # Ensure button stays disabled

    # ✅ NOW PASS CALLBACK
    create_review_cards(
        quiz_frame,
        quiz_items,
        colors,
        "Quiz",
        on_answer=handle_answer,
        reveal_once=False,
    )

    def finish_review():
        if task_id is not None:
            if not database.mark_task_status(task_id, "completed"):
                show_app_dialog("Completion Failed", "Could not mark this task completed. Please try again.", kind="error")
                return
            XPSystem(username).award_task_completion(task_id)
            refresh_tasks()

        modal.destroy()

        show_app_dialog(
            "Completed",
            "Task marked as completed after finishing the AI quiz.",
            kind="success"
        )

    # ✅ SET COMMAND AFTER FUNCTION EXISTS
    finish_btn.configure(command=finish_review if complete_on_finish else modal.destroy)

    close_btn_modal = ctk.CTkButton(
        actions,
        text="Close",
        height=42,
        corner_radius=14,
        fg_color=colors["secondary"],
        hover_color=colors["secondary_hover"],
        text_color=colors["secondary_text"],
        command=modal.destroy,
    )
    close_btn_modal.grid(row=0, column=1, sticky="e")

def _notes_preview(task):
    n = (task.get("notes") or "").strip().replace("\n", " ")
    if len(n) > 36:
        return n[:33] + "..."
    return n or "-"


def refresh_tasks(selected_id=None):
    tasks = database.get_tasks_for_username(username)
    for item in tree.get_children():
        tree.delete(item)
    for task in tasks:
        tree.insert(
            "",
            "end",
            iid=str(task["id"]),
            values=(
                task["title"],
                format_indian_date(task.get("study_date")),
                format_indian_date(task.get("due_date")),
                _notes_preview(task),
                task.get("priority", "Medium"),
                task.get("status", "pending").title(),
            ),
        )
    if selected_id is not None and tree.exists(str(selected_id)):
        tree.selection_set(str(selected_id))
        tree.focus(str(selected_id))
        tree.see(str(selected_id))
    count_label.configure(text=f"{VIEW_TASKS_SUBTITLE}\n{len(tasks)} task(s) for {username}")


def selected_task_id():
    selection = tree.selection() or ((tree.focus(),) if tree.focus() else ())
    task_id = selection[0] if selection else None
    if not task_id:
        show_app_dialog("Select Task", "Choose a task first.", kind="warning")
        return None
    try:
        return int(task_id)
    except (TypeError, ValueError):
        show_app_dialog("Select Task", "Choose a valid task row first.", kind="warning")
        return None


def select_tree_row(event):
    row_id = tree.identify_row(event.y)
    if row_id:
        tree.selection_set(row_id)
        tree.focus(row_id)


def mark_completed():
    task_id = selected_task_id()

    if task_id is None:
        return

    task = database.get_task_by_id(task_id)

    if task:
        task, source_label = ensure_current_quiz(task_id, task)

    if task:
        show_review_pack(task, source_label, complete_on_finish=True, task_id=task_id)


def mark_pending():
    task_id = selected_task_id()
    if task_id is None:
        return
    database.mark_task_status(task_id, "pending")
    refresh_tasks()


def delete_task():
    task_id = selected_task_id()
    if task_id is None:
        return
    if not show_app_dialog("Delete Task", "Remove this task?", kind="error", confirm=True):
        return
    database.delete_task(task_id)
    refresh_tasks()


def edit_timetable():
    task_id = selected_task_id()
    if task_id is None:
        return
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "add_task.py")
    try:
        subprocess.Popen(
            [sys.executable, script, username, "--edit", str(task_id)],
            close_fds=os.name != "nt",
        )
    except OSError:
        show_app_dialog("Task Editor", "Could not open the task editor.", kind="error")


def edit_task():
    task_id = selected_task_id()
    if task_id is None:
        return
    task = database.get_task_by_id(task_id)
    if not task:
        return

    colors = palette()
    modal = ctk.CTkToplevel(app)
    modal.title("Edit Task")
    modal.geometry("820x640")
    modal.configure(fg_color=colors["bg"])
    modal.grab_set()

    panel = ctk.CTkFrame(modal, corner_radius=24, border_width=1, fg_color=colors["panel"], border_color=colors["panel_border"])
    panel.pack(fill="both", expand=True, padx=20, pady=20)

    ctk.CTkLabel(panel, text="Edit Task", font=("Verdana", 24, "bold"), text_color=colors["text"]).pack(anchor="w", padx=20, pady=(18, 8))
    ctk.CTkLabel(panel, text="Update title, dates, notes, and priority.", font=("Verdana", 13), text_color=colors["muted"]).pack(anchor="w", padx=20, pady=(0, 16))

    form = ctk.CTkFrame(panel, fg_color="transparent")
    form.pack(fill="x", padx=20)
    form.grid_columnconfigure(0, weight=1)
    form.grid_columnconfigure(1, weight=1)

    def labeled_entry(parent, label, value="", placeholder=""):
        ctk.CTkLabel(parent, text=label, font=("Verdana", 12, "bold"), text_color=colors["text"]).pack(anchor="w", pady=(0, 5))
        entry = ctk.CTkEntry(parent, height=40, corner_radius=12, border_width=1, fg_color=colors["entry"] if "entry" in colors else colors["surface"], border_color=colors["panel_border"], text_color=colors["text"], placeholder_text=placeholder, placeholder_text_color=colors["muted"])
        entry.pack(fill="x", pady=(0, 12))
        if value not in (None, ""):
            entry.insert(0, str(value))
        return entry

    left = ctk.CTkFrame(form, fg_color="transparent")
    right = ctk.CTkFrame(form, fg_color="transparent")
    left.grid(row=0, column=0, sticky="ew", padx=(0, 10))
    right.grid(row=0, column=1, sticky="ew", padx=(10, 0))

    title_entry_modal = labeled_entry(left, "Title", task.get("title", ""))

    ctk.CTkLabel(left, text="Study start date", font=("Verdana", 12, "bold"), text_color=colors["text"]).pack(anchor="w", pady=(0, 5))
    row_sd = ctk.CTkFrame(left, fg_color="transparent")
    row_sd.pack(fill="x", pady=(0, 12))
    row_sd.grid_columnconfigure(0, weight=1)
    study_date_entry_modal = ctk.CTkEntry(row_sd, height=40, corner_radius=12, border_width=1, fg_color=colors["entry"] if "entry" in colors else colors["surface"], border_color=colors["panel_border"], text_color=colors["text"], placeholder_text="DD-MM-YYYY", placeholder_text_color=colors["muted"])
    study_date_entry_modal.grid(row=0, column=0, sticky="ew", padx=(0, 8))
    if task.get("study_date"):
        study_date_entry_modal.insert(0, format_indian_date(task.get("study_date")))
    ctk.CTkButton(row_sd, text="Choose", width=80, height=40, corner_radius=12, fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"], command=lambda: pick_date_for_entry(study_date_entry_modal)).grid(row=0, column=1)

    ctk.CTkLabel(right, text="Due date", font=("Verdana", 12, "bold"), text_color=colors["text"]).pack(anchor="w", pady=(0, 5))
    row_dd = ctk.CTkFrame(right, fg_color="transparent")
    row_dd.pack(fill="x", pady=(0, 12))
    row_dd.grid_columnconfigure(0, weight=1)
    due_date_entry_modal = ctk.CTkEntry(row_dd, height=40, corner_radius=12, border_width=1, fg_color=colors["entry"] if "entry" in colors else colors["surface"], border_color=colors["panel_border"], text_color=colors["text"], placeholder_text="DD-MM-YYYY", placeholder_text_color=colors["muted"])
    due_date_entry_modal.grid(row=0, column=0, sticky="ew", padx=(0, 8))
    if task.get("due_date"):
        due_date_entry_modal.insert(0, format_indian_date(task.get("due_date")))
    ctk.CTkButton(row_dd, text="Choose", width=80, height=40, corner_radius=12, fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"], command=lambda: pick_date_for_entry(due_date_entry_modal)).grid(row=0, column=1)
    hours_entry_modal = labeled_entry(right, "Study Hours", task.get("study_hours", 1))
    reminder_entry_modal = labeled_entry(right, "Reminder Minutes Before", task.get("reminder_lead_minutes", 30))

    option_row = ctk.CTkFrame(panel, fg_color="transparent")
    option_row.pack(fill="x", padx=20, pady=(0, 12))
    option_row.grid_columnconfigure(0, weight=1)
    option_row.grid_columnconfigure(1, weight=1)
    priority_var_modal = ctk.StringVar(value=task.get("priority") or "Medium")
    status_var_modal = ctk.StringVar(value=task.get("status") or "pending")

    priority_menu = ctk.CTkOptionMenu(option_row, values=["High", "Medium", "Low"], variable=priority_var_modal, height=40, corner_radius=12, fg_color=colors["entry"] if "entry" in colors else colors["surface"], button_color=colors["primary"], button_hover_color=colors["primary_hover"], text_color=colors["text"], dropdown_fg_color=colors["panel"], dropdown_hover_color=colors["surface"], dropdown_text_color=colors["text"])
    status_menu = ctk.CTkOptionMenu(option_row, values=["pending", "completed"], variable=status_var_modal, height=40, corner_radius=12, fg_color=colors["entry"] if "entry" in colors else colors["surface"], button_color=colors["primary"], button_hover_color=colors["primary_hover"], text_color=colors["text"], dropdown_fg_color=colors["panel"], dropdown_hover_color=colors["surface"], dropdown_text_color=colors["text"])
    ctk.CTkLabel(option_row, text="Priority", font=("Verdana", 12, "bold"), text_color=colors["text"]).grid(row=0, column=0, sticky="w", padx=(0, 10))
    ctk.CTkLabel(option_row, text="Status", font=("Verdana", 12, "bold"), text_color=colors["text"]).grid(row=0, column=1, sticky="w", padx=(10, 0))
    priority_menu.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(5, 0))
    status_menu.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(5, 0))

    ctk.CTkLabel(panel, text="Notes", font=("Verdana", 12, "bold"), text_color=colors["text"]).pack(anchor="w", padx=20, pady=(4, 6))
    notes_box_modal = ctk.CTkTextbox(panel, height=140, corner_radius=14, border_width=1, fg_color=colors["surface"], border_color=colors["surface_border"], text_color=colors["text"])
    notes_box_modal.pack(fill="both", expand=True, padx=20, pady=(0, 16))
    notes_box_modal.insert("1.0", task.get("notes") or "")

    actions = ctk.CTkFrame(panel, fg_color="transparent")
    actions.pack(fill="x", padx=20, pady=(0, 18))
    actions.grid_columnconfigure((0, 1), weight=1)

    def save_changes():
        title = title_entry_modal.get().strip()
        if not title:
            show_app_dialog("Missing Title", "Please enter a task title.", kind="warning")
            return
        try:
            study_date = to_storage_date(study_date_entry_modal.get())
            due_date = to_storage_date(due_date_entry_modal.get())
            study_hours = float(hours_entry_modal.get().strip() or 1)
            reminder_minutes = int(reminder_entry_modal.get().strip() or 30)
        except ValueError as exc:
            show_app_dialog("Invalid Input", str(exc), kind="warning")
            return
        if reminder_minutes < 0:
            show_app_dialog("Invalid Reminder", "Reminder minutes cannot be negative.", kind="warning")
            return
        saved = database.update_task(
            task_id,
            title=title,
            subject=task.get("subject") or "General",
            due_date=due_date,
            study_date=study_date,
            study_hours=study_hours,
            status=status_var_modal.get(),
            notes=notes_box_modal.get("1.0", "end").strip(),
            notes_path=task.get("notes_path"),
            study_plan=(task.get("study_plan") or "").strip(),
            priority=priority_var_modal.get(),
            reminder_lead_minutes=reminder_minutes,
        )
        if not saved:
            show_app_dialog("Save Failed", "Could not update this task. Check the values and try again.", kind="error")
            return
        modal.destroy()
        refresh_tasks(task_id)
        show_app_dialog("Saved", "Task updated.", kind="success")

    ctk.CTkButton(actions, text="Save Changes", height=42, corner_radius=14, fg_color=colors["primary"], hover_color=colors["primary_hover"], text_color="#ffffff", command=save_changes).grid(row=0, column=0, sticky="ew", padx=(0, 8))
    ctk.CTkButton(actions, text="Cancel", height=42, corner_radius=14, fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"], command=modal.destroy).grid(row=0, column=1, sticky="ew", padx=(8, 0))


def open_calendar_view():
    colors = palette()
    modal = ctk.CTkToplevel(app)
    modal.title("Calendar View")
    modal.geometry("980x720")
    modal.configure(fg_color=colors["bg"])
    modal.grab_set()

    current = datetime.today().replace(day=1)
    panel = ctk.CTkFrame(modal, corner_radius=24, border_width=1, fg_color=colors["panel"], border_color=colors["panel_border"])
    panel.pack(fill="both", expand=True, padx=20, pady=20)

    header = ctk.CTkFrame(panel, fg_color="transparent")
    header.pack(fill="x", padx=20, pady=(18, 12))
    month_label = ctk.CTkLabel(header, text="", font=("Verdana", 24, "bold"), text_color=colors["text"])
    month_label.pack(side="left")
    nav = ctk.CTkFrame(header, fg_color="transparent")
    nav.pack(side="right")
    grid = ctk.CTkFrame(panel, fg_color="transparent")
    grid.pack(fill="both", expand=True, padx=20, pady=(0, 18))

    def tasks_for_day(day):
        iso_day = datetime(current.year, current.month, day).strftime("%Y-%m-%d")
        return [
            task for task in database.get_tasks_for_username(username)
            if task.get("study_date") == iso_day or task.get("due_date") == iso_day
        ]

    def render():
        for child in grid.winfo_children():
            child.destroy()
        month_label.configure(text=current.strftime("%B %Y"))
        for col, name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
            ctk.CTkLabel(grid, text=name, font=("Verdana", 12, "bold"), text_color=colors["muted"]).grid(row=0, column=col, sticky="ew", padx=4, pady=(0, 8))
            grid.grid_columnconfigure(col, weight=1, uniform="calendar")
        for row_index, week in enumerate(calendar.monthcalendar(current.year, current.month), start=1):
            grid.grid_rowconfigure(row_index, weight=1, uniform="calendar")
            for col_index, day in enumerate(week):
                cell = ctk.CTkFrame(grid, corner_radius=12, border_width=1, fg_color=colors["surface"], border_color=colors["surface_border"])
                cell.grid(row=row_index, column=col_index, sticky="nsew", padx=4, pady=4)
                if day == 0:
                    continue
                ctk.CTkLabel(cell, text=str(day), font=("Verdana", 12, "bold"), text_color=colors["text"]).pack(anchor="nw", padx=8, pady=(6, 2))
                for task in tasks_for_day(day)[:3]:
                    prefix = "D" if task.get("due_date") == datetime(current.year, current.month, day).strftime("%Y-%m-%d") else "S"
                    text = f"{prefix}: {task.get('priority', 'Medium')[0]} - {task['title']}"
                    ctk.CTkLabel(cell, text=text, font=("Verdana", 10), text_color=colors["muted"], wraplength=110, justify="left").pack(anchor="w", padx=8, pady=(0, 2))

    def shift(delta):
        nonlocal current
        month = current.month + delta
        year = current.year
        if month < 1:
            month = 12
            year -= 1
        elif month > 12:
            month = 1
            year += 1
        current = current.replace(year=year, month=month, day=1)
        render()

    ctk.CTkButton(nav, text="<", width=42, height=36, corner_radius=12, fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"], command=lambda: shift(-1)).pack(side="left", padx=(0, 8))
    ctk.CTkButton(nav, text=">", width=42, height=36, corner_radius=12, fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"], command=lambda: shift(1)).pack(side="left")
    ctk.CTkButton(panel, text="Close", height=40, corner_radius=14, fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"], command=modal.destroy).pack(anchor="e", padx=20, pady=(0, 18))
    render()


def show_details(_event=None):
    task_id = selected_task_id()
    if task_id is None:
        return
    tasks = database.get_tasks_for_username(username)
    task = next((row for row in tasks if row["id"] == task_id), None)
    if not task:
        return
    lines = [
        f"Title: {task['title']}",
        f"Priority: {task.get('priority', 'Medium')}",
        f"Study Date: {format_indian_date(task.get('study_date'))}",
        f"Due Date: {format_indian_date(task.get('due_date'))}",
        f"Study Hours: {task.get('study_hours', 0)}",
        f"Reminder: {task.get('reminder_lead_minutes', 30)} minute(s) before",
        f"Status: {task.get('status', 'pending').title()}",
    ]
    subject = (task.get("subject") or "").strip()
    if subject:
        lines.insert(1, f"Subject: {subject}")
    if task.get("notes_path"):
        lines.append(f"Document: {task['notes_path']}")
    notes = (task.get("notes") or "").strip()
    if notes:
        lines.append("")
        lines.append("Notes:")
        lines.append(notes)
    show_app_dialog("Task Details", "\n".join(lines), kind="info")


def open_review_pack():
    task_id = selected_task_id()
    if task_id is None:
        return
    task = database.get_task_by_id(task_id)
    if not task:
        return
    if task.get("status") != "completed":
        show_app_dialog("Complete First", "Mark the task as completed to generate the AI quiz.", kind="info")
        return
    task, source_label = ensure_current_quiz(task_id, task)
    show_review_pack(task, source_label)


def apply_theme():
    colors = palette()
    app.configure(fg_color=colors["bg"])
    root_frame.configure(fg_color=colors["bg"])
    app_shell.configure(fg_color=colors["panel"], border_color=colors["panel_border"])
    nav_rail.configure(fg_color=colors["sidebar"], border_color=colors["sidebar_border"])
    outer.configure(fg_color="transparent")
    header.configure(fg_color=colors["header"], border_color=colors["header_border"])
    table_frame.configure(fg_color=colors["surface"], border_color=colors["surface_border"])
    heading.configure(text_color=colors["text"])
    count_label.configure(text_color=colors["muted"])
    task_board_heading.configure(text_color=colors["text"])
    toolbar.configure(fg_color="transparent")
    complete_btn.configure(fg_color=colors["primary"], hover_color=colors["primary_hover"], text_color="#ffffff")
    pending_btn.configure(fg_color=colors["danger"], hover_color=colors["danger_hover"], text_color="#ffffff")
    review_btn.configure(fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"])
    timetable_btn.configure(fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"])
    close_btn.configure(fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"])
    delete_btn.configure(fg_color=colors["danger"], hover_color=colors["danger_hover"], text_color="#ffffff")
    theme_btn.configure(
        image=sun_icon if current_theme == "dark" else moon_icon,
        fg_color=colors["panel"],
        hover_color=colors["surface"],
        border_color=colors["panel_border"],
        text_color=colors["secondary_text"],
    )
    style_treeview(style, "Tasks.Treeview", colors, rowheight=38)


username = resolve_username(sys.argv[1] if len(sys.argv) > 1 else "")
current_theme = load_theme()
ctk.set_appearance_mode(current_theme)
ctk.set_default_color_theme("blue")

app = ctk.CTk()
app.title("My Tasks | Schedly")
app.minsize(980, 620)
try:
    app.attributes("-alpha", 0.0)
except Exception:
    pass

sun_icon = load_image("sun.png", (20, 20))
moon_icon = load_image("moon.png", (20, 20))

root_frame = ctk.CTkFrame(app, fg_color="transparent")
root_frame.pack(fill="both", expand=True)

app_shell, nav_rail, content_area = make_app_shell(root_frame, palette(), active_label="Tasks")

outer = ctk.CTkFrame(content_area, corner_radius=0, border_width=0, fg_color="transparent")
outer.grid(row=0, column=0, rowspan=2, sticky="nsew")

header = ctk.CTkFrame(outer, corner_radius=22, border_width=1)
header.pack(fill="x", padx=0, pady=(0, 14))
header.grid_columnconfigure(0, weight=1)
heading = ctk.CTkLabel(header, text="Tasks", font=("Segoe UI Semibold", 28))
heading.grid(row=0, column=0, sticky="w", padx=22, pady=(18, 0))
count_label = ctk.CTkLabel(
    header,
    text=VIEW_TASKS_SUBTITLE,
    font=("Segoe UI", 13),
    wraplength=560,
    justify="left",
    anchor="w",
)
count_label.grid(row=1, column=0, sticky="w", padx=22, pady=(6, 18))

def toggle_theme():
    global current_theme
    current_theme = "dark" if current_theme == "light" else "light"
    ctk.set_appearance_mode(current_theme)
    global_save_theme(current_theme)
    theme_btn.configure(image=sun_icon if current_theme == "dark" else moon_icon)
    apply_theme()

theme_btn = ctk.CTkButton(header, text="", width=42, height=42, corner_radius=16, border_width=1, command=toggle_theme, image=sun_icon if current_theme == "dark" else moon_icon)
theme_btn.grid(row=0, column=1, rowspan=2, sticky="e", padx=20)

toolbar = ctk.CTkFrame(outer, fg_color="transparent")
toolbar.pack(fill="x", padx=0, pady=(0, 14))
timetable_btn = ctk.CTkButton(toolbar, text="Edit task", height=42, corner_radius=14, command=edit_timetable)
timetable_btn.pack(side="left", padx=(0, 8))
complete_btn = ctk.CTkButton(toolbar, text="Mark Completed", height=42, corner_radius=14, command=mark_completed)
complete_btn.pack(side="left", padx=(0, 8))
pending_btn = ctk.CTkButton(toolbar, text="Mark Pending", height=42, corner_radius=14, command=mark_pending)
pending_btn.pack(side="left", padx=(0, 8))
review_btn = ctk.CTkButton(toolbar, text="AI Quiz", height=42, corner_radius=14, command=open_review_pack)
review_btn.pack(side="left", padx=(0, 8))
delete_btn = ctk.CTkButton(toolbar, text="Delete task", height=42, corner_radius=14, command=delete_task)
delete_btn.pack(side="left", padx=(0, 8))
close_btn = ctk.CTkButton(toolbar, text="Close", height=42, corner_radius=14, command=app.destroy)
close_btn.pack(side="right")

task_board_heading = ctk.CTkLabel(outer, text="Task Board", font=("Segoe UI Semibold", 18), anchor="w")
task_board_heading.pack(fill="x", padx=2, pady=(10, 6))

table_frame = ctk.CTkFrame(outer, corner_radius=24, border_width=1)
table_frame.pack(fill="both", expand=True, padx=0, pady=(0, 0))

style = ttk.Style()
style.theme_use("default")
style.configure("Tasks.Treeview", rowheight=38, font=("Segoe UI", 11))
style.configure("Tasks.Treeview.Heading", font=("Segoe UI Semibold", 11))

tree = ttk.Treeview(
    table_frame,
    columns=("title", "start", "due", "notes", "priority", "status"),
    show="headings",
    style="Tasks.Treeview",
)
for key, label, width in [
    ("title", "Title", 240),
    ("start", "Start", 100),
    ("due", "Due", 100),
    ("notes", "Notes", 210),
    ("priority", "Priority", 80),
    ("status", "Status", 90),
]:
    tree.heading(key, text=label)
    tree.column(key, width=width, anchor="w")
scroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
tree.configure(yscrollcommand=scroll.set)
tree.pack(side="left", fill="both", expand=True)
scroll.pack(side="right", fill="y")

tree.bind("<ButtonRelease-1>", select_tree_row)
tree.bind("<Double-1>", lambda event: (select_tree_row(event), edit_timetable()))

apply_theme()
refresh_tasks()
app.after(100, lambda: refresh_tasks())
app.after(80, lambda: reveal_window(app))
app.mainloop()
