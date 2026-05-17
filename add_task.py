"""
Add / edit a task with an auto-generated study timetable from attached notes.
Run: python add_task.py [username] [--edit TASK_ID]
"""

import sys
import os
import re
import json
from datetime import datetime, date
import calendar
from tkinter import filedialog, ttk
import customtkinter as ctk
from PIL import Image, UnidentifiedImageError

import database
import study_timetable
from theme_manager import get_theme_colors, load_theme as global_load_theme, save_theme as global_save_theme
from ui.modern import make_app_shell, style_treeview
from tk_safety import disable_unsafe_windows_titlebar_focus_restore

disable_unsafe_windows_titlebar_focus_restore()


def parse_cli(argv):
    edit_id = None
    rest = []
    args = argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--edit" and i + 1 < len(args):
            try:
                edit_id = int(args[i + 1])
            except ValueError:
                edit_id = None
            i += 2
            continue
        rest.append(args[i])
        i += 1
    return rest, edit_id


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


def load_theme():
    return global_load_theme()


def palette():
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


def center_modal(window, parent, width=440, height=240):
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
        "success": colors.get("success", colors["primary"]),
        "warning": "#d7a14d" if current_theme == "light" else "#e0b15a",
        "error": "#d98da8" if current_theme == "light" else "#a86f86",
    }
    accent = accent_map.get(kind, colors["primary"])
    result = {"value": False}

    modal = ctk.CTkToplevel(app)
    modal.title(title)
    modal.resizable(False, False)
    modal.transient(app)
    modal.grab_set()
    modal.configure(fg_color=colors["bg"])
    center_modal(modal, app, width=480, height=250 if confirm else 230)

    panel = ctk.CTkFrame(
        modal,
        fg_color=colors["panel"],
        border_color=colors["panel_border"],
        border_width=1,
        corner_radius=22,
    )
    panel.pack(fill="both", expand=True, padx=16, pady=16)

    ctk.CTkLabel(panel, text=title, font=("Segoe UI Semibold", 22), text_color=colors["text"]).pack(anchor="center", pady=(22, 10))
    ctk.CTkFrame(panel, fg_color=accent, height=4, corner_radius=999).pack(fill="x", padx=32, pady=(0, 16))
    ctk.CTkLabel(
        panel,
        text=message,
        font=("Segoe UI", 14),
        text_color=colors["muted"],
        wraplength=380,
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
            hover_color=accent,
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
            hover_color=accent,
            text_color="#ffffff",
            command=modal.destroy,
        ).grid(row=0, column=0, columnspan=2, sticky="ew")

    modal.wait_window()
    return result["value"]


def to_storage_date(value):
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError("Date must be in DD-MM-YYYY format.")


def count_words(text):
    if not text:
        return 0
    return len(re.findall(r"\w+", text, flags=re.UNICODE))


def analyze_document(path):
    ext = os.path.splitext(path or "")[1].lower()
    out = {"pages": 0, "readable_pages": 0, "words": 0, "error": None}
    try:
        if ext == ".pdf":
            from PyPDF2 import PdfReader

            reader = PdfReader(path)
            out["pages"] = len(reader.pages)
            chunks = []
            for page in reader.pages:
                text = page.extract_text() or ""
                if text.strip():
                    out["readable_pages"] += 1
                chunks.append(text)
            out["words"] = count_words("\n".join(chunks))
        elif ext == ".docx":
            from docx import Document

            doc = Document(path)
            blob = "\n".join(p.text for p in doc.paragraphs)
            out["words"] = count_words(blob)
            approx = max(1, round(out["words"] / 280)) if out["words"] else 1
            out["pages"] = approx
            out["readable_pages"] = approx if blob.strip() else 0
        else:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                blob = handle.read()
            out["words"] = count_words(blob)
            approx = max(1, round(out["words"] / 350)) if out["words"] else 1
            out["pages"] = approx
            out["readable_pages"] = approx if blob.strip() else 0
    except Exception as exc:
        out["error"] = str(exc)
    return out


def format_notes_attachment_line(path, stats):
    base = os.path.basename(path) if path else ""
    if stats.get("error"):
        return f"Attached Document : {base} | No. of words : — (read error)"
    return f"Attached Document : {base} | No. of words : {stats['words']}"


def _parse_date_for_calendar(value):
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


database.connect()
_cli_args, EDIT_TASK_ID = parse_cli(sys.argv)
username = resolve_username(_cli_args[0] if _cli_args else "")
current_theme = load_theme()
ctk.set_appearance_mode(current_theme)
ctk.set_default_color_theme("blue")

current_plan = {"summary": "", "sessions": []}

app = ctk.CTk()
app.title("Add Task — Study Planner" if not EDIT_TASK_ID else f"Edit Timetable — Study Planner")
app.minsize(1180, 760)
try:
    app.attributes("-alpha", 0.0)
except Exception:
    pass

sun_icon = load_image("sun.png", (20, 20))
moon_icon = load_image("moon.png", (20, 20))

notes_path_var = ctk.StringVar(value="")

root_frame = ctk.CTkFrame(app, fg_color="transparent")
root_frame.pack(fill="both", expand=True)

app_shell, nav_rail, content_area = make_app_shell(root_frame, palette(), active_label="Add Task")

shell_frame = ctk.CTkFrame(content_area, fg_color="transparent")
shell_frame.grid(row=0, column=0, rowspan=2, sticky="nsew")

card = ctk.CTkFrame(shell_frame, corner_radius=24, border_width=1)
card.pack(fill="both", expand=True, padx=0, pady=0)
card.grid_columnconfigure(0, weight=1)
card.grid_columnconfigure(1, weight=1)
card.grid_rowconfigure(1, weight=1)

header = ctk.CTkFrame(card, corner_radius=22, border_width=1)
header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(20, 12))
header.grid_columnconfigure(0, weight=1)

title_label = ctk.CTkLabel(header, text="Add Task" if not EDIT_TASK_ID else "Edit task & timetable", font=("Segoe UI Semibold", 26))
title_label.grid(row=0, column=0, sticky="w", padx=22, pady=(18, 0))
subtitle_label = ctk.CTkLabel(
    header,
    text=f"{username}: attach notes, set dates, then generate and save your timetable.",
    font=("Segoe UI", 13),
    wraplength=720,
    anchor="w",
    justify="left",
)
subtitle_label.grid(row=1, column=0, sticky="w", padx=22, pady=(6, 18))


def toggle_theme():
    global current_theme
    current_theme = "dark" if current_theme == "light" else "light"
    ctk.set_appearance_mode(current_theme)
    global_save_theme(current_theme)
    apply_theme()


theme_btn = ctk.CTkButton(header, text="", width=42, height=42, corner_radius=16, border_width=1, command=toggle_theme)
theme_btn.grid(row=0, column=1, rowspan=2, sticky="e", padx=22, pady=18)

form_left = ctk.CTkScrollableFrame(card, fg_color="transparent", width=420)
form_left.grid(row=1, column=0, sticky="nsew", padx=(20, 10), pady=(4, 20))

timetable_panel = ctk.CTkFrame(card, corner_radius=22, border_width=1)
timetable_panel.grid(row=1, column=1, sticky="nsew", padx=(10, 20), pady=(4, 20))

field_labels = []


def make_label(parent, text, pady=(0, 6)):
    label = ctk.CTkLabel(parent, text=text, font=("Segoe UI Semibold", 12))
    label.pack(anchor="w", pady=pady)
    field_labels.append(label)
    return label


make_label(form_left, "Task title")
title_entry = ctk.CTkEntry(form_left, height=42, corner_radius=14, border_width=1)
title_entry.pack(fill="x", pady=(0, 12))

make_label(form_left, "Study start date")
study_start_row = ctk.CTkFrame(form_left, fg_color="transparent")
study_start_row.pack(fill="x", pady=(0, 12))
study_start_row.grid_columnconfigure(0, weight=1)
study_date_entry = ctk.CTkEntry(study_start_row, height=42, corner_radius=14, border_width=1, placeholder_text="DD-MM-YYYY")
study_date_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
study_start_pick_btn = ctk.CTkButton(study_start_row, text="Choose", width=100, height=42, corner_radius=14, command=lambda: open_calendar(study_date_entry))
study_start_pick_btn.grid(row=0, column=1)

make_label(form_left, "Due date")
due_row = ctk.CTkFrame(form_left, fg_color="transparent")
due_row.pack(fill="x", pady=(0, 12))
due_row.grid_columnconfigure(0, weight=1)
due_date_entry = ctk.CTkEntry(due_row, height=42, corner_radius=14, border_width=1, placeholder_text="DD-MM-YYYY")
due_date_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
due_pick_btn = ctk.CTkButton(due_row, text="Choose", width=100, height=42, corner_radius=14, command=lambda: open_calendar(due_date_entry))
due_pick_btn.grid(row=0, column=1)

make_label(form_left, "Priority")
priority_var = ctk.StringVar(value="Medium")
priority_menu = ctk.CTkOptionMenu(form_left, values=["High", "Medium", "Low"], variable=priority_var, height=42, corner_radius=14)
priority_menu.pack(fill="x", pady=(0, 12))
computed_hours = {"value": 2.0}

make_label(form_left, "Notes")
notes_box = ctk.CTkTextbox(form_left, height=88, corner_radius=14, border_width=1)
notes_box.pack(fill="x", pady=(0, 12))

doc_row = ctk.CTkFrame(form_left, fg_color="transparent")
doc_row.pack(fill="x", pady=(0, 12))
doc_row.grid_columnconfigure(0, weight=1)
attach_btn = ctk.CTkButton(doc_row, text="Attach file", height=42, corner_radius=14, command=lambda: attach_file())
attach_btn.grid(row=0, column=0, sticky="ew", padx=(0, 8))
generate_btn = ctk.CTkButton(doc_row, text="Generate timetable", height=42, corner_radius=14, command=lambda: run_generate_timetable())
generate_btn.grid(row=0, column=1, sticky="ew")

notes_info_label = ctk.CTkLabel(form_left, text="Attached Document : — | No. of words : —", font=("Segoe UI", 11), wraplength=400, justify="left", anchor="w")
notes_info_label.pack(anchor="w", pady=(0, 14))

action_row = ctk.CTkFrame(form_left, fg_color="transparent")
action_row.pack(fill="x", pady=(8, 12))
action_row.grid_columnconfigure((0, 1), weight=1)
save_btn = ctk.CTkButton(action_row, text="Save task" if not EDIT_TASK_ID else "Save changes", height=46, corner_radius=16, command=lambda: save_task())
save_btn.grid(row=0, column=0, sticky="ew", padx=(0, 8))
cancel_btn = ctk.CTkButton(action_row, text="Close", height=46, corner_radius=16, command=app.destroy)
cancel_btn.grid(row=0, column=1, sticky="ew", padx=(8, 0))

# --- Timetable (right)
tt_head = ctk.CTkFrame(timetable_panel, fg_color="transparent")
tt_head.pack(fill="x", padx=18, pady=(16, 8))
ctk.CTkLabel(tt_head, text="Suggested Study Timetable", font=("Segoe UI Semibold", 20)).pack(anchor="w")
timetable_summary = ctk.CTkLabel(
    tt_head,
    text="Attach notes or paste notes text, choose dates, then tap Generate timetable.",
    font=("Segoe UI", 12),
    wraplength=520,
    justify="left",
    anchor="w",
)
timetable_summary.pack(anchor="w", pady=(8, 0))

table_holder = ctk.CTkFrame(timetable_panel, fg_color="transparent")
table_holder.pack(fill="both", expand=True, padx=14, pady=(0, 16))

style = ttk.Style()
style.theme_use("default")
style.configure("Timetable.Treeview", rowheight=30, font=("Segoe UI", 11))
style.configure("Timetable.Treeview.Heading", font=("Segoe UI Semibold", 11))

timetable_tree = ttk.Treeview(
    table_holder,
    columns=("day", "date", "unit", "task", "pages", "hours"),
    show="headings",
    style="Timetable.Treeview",
    height=18,
)
for col, label, width, stretch in [
    ("day", "Day", 44, False),
    ("date", "Date", 100, False),
    ("unit", "Unit", 72, False),
    ("task", "Task", 200, True),
    ("pages", "Pages", 120, False),
    ("hours", "Hours", 56, False),
]:
    timetable_tree.heading(col, text=label)
    timetable_tree.column(col, width=width, anchor="w", stretch=stretch)
tt_scroll = ttk.Scrollbar(table_holder, orient="vertical", command=timetable_tree.yview)
timetable_tree.configure(yscrollcommand=tt_scroll.set)
timetable_tree.pack(side="left", fill="both", expand=True)
tt_scroll.pack(side="right", fill="y")


def open_calendar(target_entry):
    colors = palette()
    modal = ctk.CTkToplevel(app)
    modal.title("Select Date")
    modal.geometry("420x460")
    modal.resizable(False, False)
    modal.grab_set()
    modal.configure(fg_color=colors["bg"])

    frame = ctk.CTkFrame(modal, fg_color=colors["panel"], border_color=colors["panel_border"], border_width=1, corner_radius=20)
    frame.pack(fill="both", expand=True, padx=16, pady=16)

    current = datetime.today().replace(day=1)
    parsed = _parse_date_for_calendar(target_entry.get())
    if parsed:
        current = parsed.replace(day=1)

    hdr = ctk.CTkFrame(frame, fg_color="transparent")
    hdr.pack(fill="x", padx=16, pady=(16, 8))
    month_label = ctk.CTkLabel(hdr, text="", font=("Segoe UI Semibold", 18), text_color=colors["text"])
    month_label.pack(side="left")
    nav = ctk.CTkFrame(hdr, fg_color="transparent")
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
            ctk.CTkLabel(grid_frame, text=name, text_color=colors["muted"], font=("Segoe UI Semibold", 11)).grid(row=0, column=col, padx=3, pady=(0, 8))
        month = calendar.monthcalendar(current.year, current.month)
        for row_index, week in enumerate(month, start=1):
            for col_index, day in enumerate(week):
                if day == 0:
                    ctk.CTkLabel(grid_frame, text="", width=36).grid(row=row_index, column=col_index, padx=3, pady=3)
                    continue
                ctk.CTkButton(
                    grid_frame,
                    text=str(day),
                    width=36,
                    height=32,
                    corner_radius=12,
                    fg_color=colors["surface"],
                    hover_color=colors["secondary_hover"],
                    text_color=colors["text"],
                    border_width=1,
                    border_color=colors["surface_border"],
                    command=lambda chosen=day: select_day(chosen),
                ).grid(row=row_index, column=col_index, padx=3, pady=3)

    def shift(delta):
        nonlocal current
        mv = current.month + delta
        yv = current.year
        if mv < 1:
            mv, yv = 12, yv - 1
        elif mv > 12:
            mv, yv = 1, yv + 1
        current = current.replace(year=yv, month=mv, day=1)
        render()

    ctk.CTkButton(nav, text="<", width=32, height=28, corner_radius=10, fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"], command=lambda: shift(-1)).pack(side="left", padx=(0, 6))
    ctk.CTkButton(nav, text=">", width=32, height=28, corner_radius=10, fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"], command=lambda: shift(1)).pack(side="left")
    footer = ctk.CTkFrame(frame, fg_color="transparent")
    footer.pack(fill="x", padx=16, pady=(0, 16))
    ctk.CTkButton(footer, text="Today", height=36, corner_radius=14, fg_color=colors["primary"], hover_color=colors["primary_hover"], command=lambda: select_day(datetime.today().day)).pack(side="left")
    ctk.CTkButton(footer, text="Cancel", height=36, corner_radius=14, fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"], command=modal.destroy).pack(side="right")
    render()


def clear_timetable_tree():
    for item in timetable_tree.get_children():
        timetable_tree.delete(item)


def apply_plan_to_ui(plan: dict):
    global current_plan
    current_plan = dict(plan)
    clear_timetable_tree()
    if plan.get("error"):
        timetable_summary.configure(text=plan.get("error", "Could not build timetable."), text_color=palette().get("danger", "#c84d6d"))
        return
    timetable_summary.configure(text=plan.get("summary", ""), text_color=palette().get("success", palette()["primary"]))
    for s in plan.get("sessions") or []:
        timetable_tree.insert(
            "",
            "end",
            values=(
                s.get("day_index"),
                s.get("date"),
                s.get("unit"),
                s.get("task"),
                s.get("pages"),
                f"{float(s.get('hours', 0)):.1f}",
            ),
        )
    total_h = sum(float(s.get("hours", 0)) for s in plan.get("sessions") or [])
    computed_hours["value"] = round(total_h, 2) or computed_hours["value"]


def run_generate_timetable():
    path = notes_path_var.get().strip()
    notes_text = notes_box.get("1.0", "end").strip()
    has_file = bool(path and os.path.isfile(path))
    if not has_file and not notes_text:
        show_app_dialog("Notes", "Attach a notes file or paste notes text first.", kind="warning")
        return
    try:
        start_d = datetime.strptime(study_date_entry.get().strip(), "%d-%m-%Y").date()
        end_d = datetime.strptime(due_date_entry.get().strip(), "%d-%m-%Y").date()
    except ValueError:
        show_app_dialog("Dates", "Set valid start and due dates (DD-MM-YYYY) using Choose.", kind="warning")
        return
    title = title_entry.get().strip() or "Study"
    if has_file:
        plan = study_timetable.generate_timetable(path, start_d, end_d, title, "General")
    else:
        plan = study_timetable.generate_timetable_from_text(notes_text, start_d, end_d, title, "General")
    if plan.get("error"):
        show_app_dialog("Timetable", plan["error"], kind="error")
        return
    apply_plan_to_ui(plan)


def attach_file():
    path = filedialog.askopenfilename(
        title="Attach document",
        filetypes=[
            ("Documents", "*.pdf *.docx *.txt *.md *.csv"),
            ("PDF", "*.pdf"),
            ("Word", "*.docx"),
            ("Text", "*.txt *.md *.csv"),
        ],
    )
    if not path:
        return
    notes_path_var.set(path)
    notes_info_label.configure(text="Reading document…")
    app.update_idletasks()
    stats = analyze_document(path)
    notes_info_label.configure(text=format_notes_attachment_line(path, stats))
    clear_timetable_tree()
    timetable_summary.configure(
        text="Document updated. Set dates and tap Generate timetable.",
        text_color=palette()["muted"],
    )


def save_task():
    title = title_entry.get().strip()
    if not title:
        show_app_dialog("Missing", "Please enter a task title.", kind="warning")
        return
    try:
        due_date_value = to_storage_date(due_date_entry.get().strip()) if due_date_entry.get().strip() else None
        study_date_value = to_storage_date(study_date_entry.get().strip()) if study_date_entry.get().strip() else None
    except ValueError as exc:
        show_app_dialog("Invalid Input", str(exc), kind="warning")
        return

    path = notes_path_var.get().strip()
    notes_path_value = path if path and os.path.isfile(path) else None
    notes_text = notes_box.get("1.0", "end").strip()

    sessions = (current_plan or {}).get("sessions") or []
    if not sessions:
        show_app_dialog("Timetable Required", "Click Generate timetable before saving this task.", kind="warning")
        return
    if sessions:
        try:
            study_hours_val = round(sum(float(s.get("hours", 0)) for s in sessions), 2)
        except (TypeError, ValueError):
            study_hours_val = float(computed_hours["value"] or 2)
    else:
        study_hours_val = float(computed_hours["value"] or 2)

    plan_json = ""
    if current_plan and not current_plan.get("error") and sessions:
        payload = {k: v for k, v in current_plan.items() if k != "error"}
        payload["plain"] = study_timetable.plan_plain_lines(payload)
        plan_json = json.dumps(payload, ensure_ascii=False)

    if EDIT_TASK_ID:
        existing = database.get_task_by_id(EDIT_TASK_ID)
        if not existing:
            show_app_dialog("Missing", "Task not found.", kind="error")
            return
        ok = database.update_task(
            EDIT_TASK_ID,
            title=title,
            subject=existing.get("subject") or "General",
            due_date=due_date_value,
            study_date=study_date_value,
            study_hours=study_hours_val,
            status=existing.get("status") or "pending",
            notes=notes_text,
            notes_path=notes_path_value,
            study_plan=plan_json,
            priority=priority_var.get(),
            reminder_lead_minutes=int(existing.get("reminder_lead_minutes") or 30),
        )
        msg = "Task and timetable updated."
    else:
        ok = database.create_task_for_username(
            username,
            title=title,
            subject="General",
            due_date=due_date_value,
            study_date=study_date_value,
            study_hours=study_hours_val,
            notes=notes_text,
            notes_path=notes_path_value,
            study_plan=plan_json,
            priority=priority_var.get(),
            reminder_lead_minutes=30,
        )
        msg = "Task saved with timetable."

    if not ok:
        show_app_dialog("Save Failed", "Could not save this task.", kind="error")
        return
    show_app_dialog("Saved", msg, kind="success")
    app.destroy()


def load_edit_task():
    if not EDIT_TASK_ID:
        return
    task = database.get_task_by_id(EDIT_TASK_ID)
    if not task:
        app.after(60, lambda: show_app_dialog("Not found", "That task no longer exists.", kind="warning"))
        return
    title_entry.delete(0, "end")
    title_entry.insert(0, task.get("title") or "")
    study_date_entry.delete(0, "end")
    if task.get("study_date"):
        study_date_entry.insert(0, datetime.strptime(task["study_date"][:10], "%Y-%m-%d").strftime("%d-%m-%Y"))
    due_date_entry.delete(0, "end")
    if task.get("due_date"):
        due_date_entry.insert(0, datetime.strptime(task["due_date"][:10], "%Y-%m-%d").strftime("%d-%m-%Y"))
    priority_var.set(task.get("priority") or "Medium")
    computed_hours["value"] = float(task.get("study_hours") or 2)
    notes_box.delete("1.0", "end")
    notes_box.insert("1.0", task.get("notes") or "")
    if task.get("notes_path"):
        notes_path_var.set(task["notes_path"])
        stats = analyze_document(task["notes_path"])
        notes_info_label.configure(text=format_notes_attachment_line(task["notes_path"], stats))
    parsed = study_timetable.parse_plan_json(task.get("study_plan"))
    if parsed:
        apply_plan_to_ui(parsed)


def apply_theme():
    colors = palette()
    app.configure(fg_color=colors["bg"])
    root_frame.configure(fg_color=colors["bg"])
    app_shell.configure(fg_color=colors["panel"], border_color=colors["panel_border"])
    nav_rail.configure(fg_color=colors["sidebar"], border_color=colors["sidebar_border"])
    shell_frame.configure(fg_color="transparent")
    card.configure(fg_color=colors["panel"], border_color=colors["panel_border"])
    header.configure(fg_color=colors["header"], border_color=colors["header_border"])
    timetable_panel.configure(fg_color=colors["surface"], border_color=colors["surface_border"])
    form_left.configure(fg_color="transparent")
    title_label.configure(text_color=colors["text"])
    subtitle_label.configure(text_color=colors["muted"])
    notes_info_label.configure(text_color=colors["muted"])
    theme_btn.configure(
        image=sun_icon if current_theme == "dark" else moon_icon,
        fg_color=colors["panel"],
        hover_color=colors["surface"],
        border_color=colors["panel_border"],
        text_color=colors["secondary_text"],
    )
    for entry in [title_entry, due_date_entry, study_date_entry]:
        entry.configure(fg_color=colors["entry"], border_color=colors["entry_border"], text_color=colors["text"], placeholder_text_color=colors["muted"])
    notes_box.configure(fg_color=colors["entry"], border_color=colors["entry_border"], text_color=colors["text"])
    priority_menu.configure(
        fg_color=colors["entry"],
        button_color=colors["primary"],
        button_hover_color=colors["primary_hover"],
        text_color=colors["text"],
        dropdown_fg_color=colors["panel"],
        dropdown_hover_color=colors["surface"],
        dropdown_text_color=colors["text"],
    )
    for label in field_labels:
        label.configure(text_color=colors["text"])
    due_pick_btn.configure(fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"])
    study_start_pick_btn.configure(fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"])
    attach_btn.configure(fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"])
    generate_btn.configure(fg_color=colors["primary"], hover_color=colors["primary_hover"], text_color="#ffffff")
    save_btn.configure(fg_color=colors["primary"], hover_color=colors["primary_hover"], text_color="#ffffff")
    cancel_btn.configure(fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"])
    style_treeview(style, "Timetable.Treeview", colors, rowheight=30)


apply_theme()
load_edit_task()
app.after(80, lambda: reveal_window(app))
app.mainloop()
