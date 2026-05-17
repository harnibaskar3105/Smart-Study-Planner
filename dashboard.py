if __name__ == "__main__":
    import sys
    import database
    from single_window_app import run

    def dashboard_username():
        if len(sys.argv) > 1 and sys.argv[1].strip():
            return sys.argv[1].strip()
        database.connect()
        user = database.get_latest_user()
        return (user or {}).get("username") or "Student"

    run(initial_page="dashboard", username=dashboard_username())
    raise SystemExit

import os
import calendar
import queue
import subprocess
import sys
import threading
import webbrowser
from datetime import date, datetime
from tkinter import Canvas, messagebox

import customtkinter as ctk

import database
from dashboard_model import WEEKDAY_NAMES, load_dashboard_snapshot
from gamification.xp_system import XPSystem
from theme_manager import get_theme_colors, load_theme
from tk_safety import disable_unsafe_windows_titlebar_focus_restore


disable_unsafe_windows_titlebar_focus_restore()

APP_WIDTH = 1280
APP_HEIGHT = 800

THEME = get_theme_colors()
COLORS = {
    "window": THEME["bg"],
    "shell": THEME["panel"],
    "sidebar": THEME["sidebar"],
    "sidebar_hover": THEME["sidebar_hover"],
    "sidebar_active": THEME.get("sidebar_active", THEME["card_light"]),
    "sidebar_active_border": THEME.get("sidebar_active_border", THEME["entry_border"]),
    "sidebar_icon": THEME.get("sidebar_icon", THEME["card_light"]),
    "sidebar_icon_active": THEME.get("sidebar_icon_active", THEME["primary"]),
    "panel": THEME["surface"],
    "surface": THEME["surface"],
    "panel_soft": THEME["tile"],
    "card": THEME["card"],
    "card_light": THEME["card_light"],
    "primary": THEME["primary"],
    "primary_hover": THEME["primary_hover"],
    "secondary": THEME["secondary"],
    "secondary_hover": THEME["secondary_hover"],
    "secondary_text": THEME["secondary_text"],
    "deep": THEME["deep"],
    "deep_hover": THEME["deep_hover"],
    "text": THEME["text"],
    "muted": THEME["muted"],
    "line": THEME["entry_border"],
    "pink": THEME["pink"],
    "teal": THEME["teal"],
    "yellow": THEME["yellow"],
    "green": THEME["green"],
    "danger": THEME["danger"],
    "white": THEME["white"],
}

RESOURCE_MAP = {
    "Science": [("Khan Academy", "https://www.khanacademy.org/science"), ("Crash Course", "https://thecrashcourse.com/")],
    "Technology": [("freeCodeCamp", "https://www.freecodecamp.org/"), ("CS50", "https://cs50.harvard.edu/")],
    "Commerce": [("Investopedia", "https://www.investopedia.com/"), ("edX Finance", "https://www.edx.org/learn/finance")],
    "Humanities": [("OpenLearn", "https://www.open.edu/openlearn/history-the-arts"), ("BBC History", "https://www.bbc.co.uk/history")],
    "Languages": [("Duolingo", "https://www.duolingo.com/"), ("Memrise", "https://www.memrise.com/")],
}


def resolve_username():
    return (sys.argv[1] if len(sys.argv) > 1 else "Student").strip() or "Student"


username = resolve_username()
load_queue = queue.Queue()
load_token = 0
snapshot = None
game_state = None
displayed_total_xp = None

app = ctk.CTk()
app.title("Schedly")
app.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
app.minsize(1120, 720)
app.configure(fg_color=COLORS["window"])
ctk.set_appearance_mode(load_theme())
ctk.set_default_color_theme("blue")


def open_script(script_name):
    if not os.path.exists(script_name):
        messagebox.showinfo("Coming Soon", f"{script_name} is not available yet.")
        return
    subprocess.Popen([sys.executable, script_name, username])


def logout():
    app.destroy()
    subprocess.Popen([sys.executable, "login.py"])


def format_date(value):
    if not value:
        return "No date"
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %b")
    except ValueError:
        return value


def resource_links_for(subject):
    return RESOURCE_MAP.get(subject, RESOURCE_MAP["Science"])


def user_first_name():
    if snapshot and snapshot.user.get("name"):
        return snapshot.user["name"].split()[0]
    return username


class CircularMeter(ctk.CTkFrame):
    def __init__(self, master, title, value=0, color=COLORS["pink"], command=None, diameter=108):
        self.diameter = diameter
        self.stroke = max(8, diameter // 11)
        self.pad = max(10, diameter // 8)
        super().__init__(master, height=diameter + 64, corner_radius=20, fg_color=COLORS["surface"], border_width=1, border_color=COLORS["line"])
        self.value = value
        self.color = color
        self.command = command
        self.grid_propagate(False)
        self.pack_propagate(False)
        self.configure(cursor="hand2" if command else "")
        self.title_label = ctk.CTkLabel(self, text=title, font=("Segoe UI Semibold", 12), text_color=COLORS["text"])
        self.title_label.pack(anchor="w", padx=16, pady=(14, 4))

        self.meter_box = ctk.CTkFrame(self, width=diameter, height=diameter, fg_color="transparent")
        self.meter_box.pack(anchor="center", pady=(0, 12))
        self.meter_box.pack_propagate(False)
        self.canvas = Canvas(self.meter_box, width=diameter, height=diameter, highlightthickness=0, bd=0, bg=COLORS["surface"])
        self.canvas.place(relx=0.5, rely=0.5, anchor="center")
        self.value_label = ctk.CTkLabel(self, text=f"{value}%", font=("Segoe UI Semibold", 19), text_color=COLORS["text"])
        self.value_label.place(in_=self.meter_box, relx=0.5, rely=0.5, anchor="center")
        if command:
            self.bind("<Button-1>", lambda _event: command())
            self.canvas.bind("<Button-1>", lambda _event: command())
            self.value_label.bind("<Button-1>", lambda _event: command())
        self.draw(value)

    def draw(self, value):
        self.value = max(0, min(100, int(value)))
        self.value_label.configure(text=f"{self.value}%")
        self.canvas.delete("all")
        # Canvas arcs are much lighter than embedding matplotlib figures and
        # redraw instantly during dashboard refreshes.
        end = self.diameter - self.pad
        self.canvas.create_oval(self.pad, self.pad, end, end, outline=COLORS["line"], width=self.stroke)
        self.canvas.create_arc(self.pad, self.pad, end, end, start=90, extent=-(self.value * 3.6), outline=self.color, width=self.stroke, style="arc")


class AnimatedBar(ctk.CTkFrame):
    def __init__(self, master, width=320, height=16, color=COLORS["pink"]):
        super().__init__(master, fg_color="transparent")
        self.width = width
        self.height = height
        self.color = color
        self.target = 0
        self.current = 0
        self.canvas = Canvas(self, width=width, height=height, highlightthickness=0, bd=0, bg=COLORS["surface"])
        self.canvas.pack(fill="x")
        self.draw(0)

    def draw(self, value):
        self.canvas.delete("all")
        radius = self.height // 2
        self.canvas.create_rectangle(radius, 0, self.width - radius, self.height, fill=COLORS["line"], outline="")
        self.canvas.create_oval(0, 0, self.height, self.height, fill=COLORS["line"], outline="")
        self.canvas.create_oval(self.width - self.height, 0, self.width, self.height, fill=COLORS["line"], outline="")
        fill_width = max(self.height, int(self.width * value))
        self.canvas.create_rectangle(radius, 0, fill_width - radius, self.height, fill=self.color, outline="")
        self.canvas.create_oval(0, 0, self.height, self.height, fill=self.color, outline="")
        self.canvas.create_oval(fill_width - self.height, 0, fill_width, self.height, fill=self.color, outline="")

    def animate_to(self, value):
        self.target = max(0, min(1, float(value or 0)))
        self._step()

    def _step(self):
        if abs(self.current - self.target) < 0.01:
            self.current = self.target
            self.draw(self.current)
            return
        self.current += (self.target - self.current) * 0.22
        self.draw(self.current)
        self.after(16, self._step)


class SmallCard(ctk.CTkFrame):
    def __init__(self, master, title):
        super().__init__(master, corner_radius=22, fg_color=COLORS["surface"], border_width=1, border_color=COLORS["line"])
        self.title = ctk.CTkLabel(self, text=title, font=("Segoe UI Semibold", 15), text_color=COLORS["text"])
        self.title.pack(anchor="w", padx=18, pady=(16, 10))


class StatTile(ctk.CTkFrame):
    def __init__(self, master, title, accent):
        super().__init__(master, corner_radius=18, fg_color=COLORS["surface"], border_width=1, border_color=COLORS["line"])
        self.value = ctk.CTkLabel(self, text="0", font=("Segoe UI Semibold", 22), text_color=COLORS["text"])
        self.value.pack(anchor="w", padx=16, pady=(14, 0))
        ctk.CTkLabel(self, text=title, font=("Segoe UI", 12), text_color=COLORS["muted"]).pack(anchor="w", padx=16, pady=(2, 10))
        ctk.CTkFrame(self, height=4, fg_color=accent, corner_radius=999).pack(fill="x", padx=16, pady=(0, 14))

    def set(self, value):
        self.value.configure(text=str(value))


def make_icon(parent, text):
    return ctk.CTkLabel(
        parent,
        text=text,
        width=28,
        height=28,
        corner_radius=8,
        fg_color=COLORS["deep"],
        text_color=COLORS["white"],
        font=("Segoe UI Semibold", 13),
    )


def nav_item(parent, icon, label, command, active=False):
    idle = COLORS["sidebar_active"] if active else "transparent"
    hover = COLORS["sidebar_active"] if active else COLORS["sidebar_hover"]
    row = ctk.CTkFrame(
        parent,
        height=42,
        corner_radius=15,
        fg_color=idle,
        border_width=1 if active else 0,
        border_color=COLORS["sidebar_active_border"],
    )
    row.pack(fill="x", padx=12, pady=3)
    row.pack_propagate(False)
    row.configure(cursor="hand2")

    icon_label = ctk.CTkLabel(
        row,
        text=icon,
        width=28,
        height=28,
        corner_radius=10,
        fg_color=COLORS["sidebar_icon_active"] if active else COLORS["sidebar_icon"],
        text_color=COLORS["white"] if active else COLORS["deep"],
        font=("Segoe UI Semibold", 13),
    )
    icon_label.pack(side="left", padx=(10, 10), pady=7)
    text_label = ctk.CTkLabel(
        row,
        text=label,
        font=("Segoe UI Semibold", 12 if active else 11),
        text_color=COLORS["deep"] if active else COLORS["text"],
        anchor="w",
    )
    text_label.pack(side="left", fill="x", expand=True, padx=(0, 12))

    def enter(_event):
        row.configure(fg_color=hover)

    def leave(_event):
        row.configure(fg_color=idle)

    def click(_event):
        command()

    for widget in (row, icon_label, text_label):
        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)
        widget.bind("<Button-1>", click)
    return row


shell = ctk.CTkFrame(app, corner_radius=32, fg_color=COLORS["shell"], border_width=1, border_color=COLORS["line"])
shell.place(relx=0.5, rely=0.5, relwidth=0.94, relheight=0.91, anchor="center")
shell.grid_columnconfigure(0, weight=0)
shell.grid_columnconfigure(1, weight=1)
shell.grid_rowconfigure(0, weight=1)

sidebar = ctk.CTkFrame(shell, width=214, corner_radius=28, fg_color=COLORS["sidebar"], border_width=1, border_color=COLORS["line"])
sidebar.grid(row=0, column=0, sticky="nsw", padx=(14, 0), pady=14)
sidebar.grid_propagate(False)

ctk.CTkLabel(sidebar, text="Schedly", font=("Segoe UI Semibold", 24), text_color=COLORS["text"]).pack(anchor="w", padx=22, pady=(24, 4))
ctk.CTkLabel(sidebar, text="Study planner", font=("Segoe UI", 12), text_color=COLORS["muted"]).pack(anchor="w", padx=22, pady=(0, 16))

profile = ctk.CTkFrame(sidebar, fg_color=COLORS["sidebar_active"], corner_radius=20, border_width=1, border_color=COLORS["sidebar_active_border"])
profile.pack(fill="x", padx=12, pady=(0, 16))
avatar = ctk.CTkLabel(profile, text="S", width=40, height=40, corner_radius=20, fg_color=COLORS["yellow"], text_color=COLORS["text"], font=("Segoe UI Semibold", 17))
avatar.pack(side="left", padx=(12, 8), pady=12)
profile_text = ctk.CTkLabel(profile, text=username, font=("Segoe UI", 12), text_color=COLORS["muted"], justify="left")
profile_text.pack(side="left", pady=12)

nav_group = ctk.CTkFrame(sidebar, fg_color="transparent")
nav_group.pack(fill="x")
nav_item(nav_group, "⌂", "Dashboard", lambda: None, active=True)
nav_item(nav_group, "+", "Add Task", lambda: open_script("add_task.py"))
nav_item(nav_group, "◉", "Progress", lambda: open_script("progress.py"))
nav_item(nav_group, "☷", "Tasks", lambda: open_script("view_tasks.py"))
nav_item(nav_group, "◆", "Analytics", lambda: open_script("weakness_analyzer.py"))
nav_item(nav_group, "⚙", "Settings", lambda: open_script("settings_page.py"))

ctk.CTkFrame(sidebar, fg_color="transparent").pack(fill="both", expand=True)
nav_item(sidebar, "↩", "Log out", logout).pack_configure(pady=(3, 16))

main = ctk.CTkFrame(shell, fg_color="transparent")
main.grid(row=0, column=1, sticky="nsew", padx=18, pady=14)
main.grid_columnconfigure(0, weight=2, uniform="main")
main.grid_columnconfigure(1, weight=2, uniform="main")
main.grid_columnconfigure(2, weight=0)
main.grid_rowconfigure(3, weight=1, minsize=340)
main.grid_rowconfigure(4, weight=0)
main.grid_rowconfigure(5, weight=0)

top = ctk.CTkFrame(main, fg_color="transparent")
top.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 12))
top.grid_columnconfigure(0, weight=1)
hello = ctk.CTkLabel(top, text="HELLO!", font=("Segoe UI Semibold", 24), text_color=COLORS["text"])
hello.grid(row=0, column=0, sticky="w")
ctk.CTkLabel(top, text="Search", font=("Segoe UI", 11), text_color=COLORS["muted"]).grid(row=0, column=1, sticky="w", padx=(16, 10), pady=(0, 4))
search = ctk.CTkEntry(top, placeholder_text="Search tasks, subjects, goals", width=260, height=40, corner_radius=16, fg_color=COLORS["panel_soft"], border_color=COLORS["line"], text_color=COLORS["text"])
search.grid(row=1, column=1, sticky="e", padx=(16, 10))
ctk.CTkButton(top, text="Today", width=82, height=40, corner_radius=16, fg_color=COLORS["deep"], hover_color=COLORS["deep_hover"], text_color=COLORS["white"], command=lambda: open_script("view_tasks.py")).grid(row=1, column=2, sticky="e")

hero_card = ctk.CTkFrame(main, corner_radius=24, fg_color=COLORS["deep"], border_width=1, border_color=COLORS["line"])
hero_card.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=(0, 12), pady=(0, 12))
hero_card.grid_columnconfigure(0, weight=1)
ctk.CTkLabel(hero_card, text="Focus cockpit", font=("Segoe UI Semibold", 13), text_color=COLORS["white"]).grid(row=0, column=0, sticky="w", padx=22, pady=(18, 2))
hero_title = ctk.CTkLabel(hero_card, text="Plan today, protect attendance, and keep your streak moving.", font=("Segoe UI Semibold", 25), text_color=COLORS["white"], wraplength=660, justify="left")
hero_title.grid(row=1, column=0, sticky="w", padx=22, pady=(0, 16))

metrics = ctk.CTkFrame(main, fg_color="transparent")
metrics.grid(row=2, column=0, columnspan=2, sticky="ew", padx=(0, 12), pady=(0, 12))
for column in range(4):
    metrics.grid_columnconfigure(column, weight=1, uniform="metrics")
total_tile = StatTile(metrics, "Tasks", COLORS["teal"])
total_tile.grid(row=0, column=0, sticky="ew", padx=(0, 8))
completion_tile = StatTile(metrics, "Complete", COLORS["green"])
completion_tile.grid(row=0, column=1, sticky="ew", padx=8)
streak_tile = StatTile(metrics, "Streak", COLORS["yellow"])
streak_tile.grid(row=0, column=2, sticky="ew", padx=8)
consistency_tile = StatTile(metrics, "Consistency", COLORS["pink"])
consistency_tile.grid(row=0, column=3, sticky="ew", padx=(8, 0))

teachers_card = SmallCard(main, "Linked subjects")
teachers_card.grid(row=3, column=0, sticky="nsew", padx=(0, 8), pady=(0, 12))
teachers_card.grid_propagate(False)
events_card = SmallCard(main, "Upcoming events")
events_card.grid(row=3, column=1, sticky="nsew", padx=(8, 12), pady=(0, 12))
events_card.grid_propagate(False)

schedule_card = SmallCard(main, "My schedule")
schedule_card.grid(row=4, column=0, columnspan=2, sticky="nsew", padx=(0, 12), pady=(0, 12))
schedule_body = ctk.CTkFrame(schedule_card, fg_color="transparent")
schedule_body.pack(fill="x", padx=18, pady=(0, 14))
schedule_body.grid_columnconfigure(0, weight=0)
schedule_body.grid_columnconfigure(1, weight=1)

calendar_panel = ctk.CTkFrame(schedule_body, width=170, height=118, corner_radius=18, fg_color=COLORS["panel_soft"])
calendar_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
calendar_panel.grid_propagate(False)
calendar_label = ctk.CTkLabel(calendar_panel, text="", font=("Segoe UI", 11), text_color=COLORS["muted"], justify="center")
calendar_label.place(relx=0.5, rely=0.5, anchor="center")

task_list = ctk.CTkFrame(schedule_body, fg_color="transparent")
task_list.grid(row=0, column=1, sticky="nsew")

projects_card = SmallCard(main, "My projects")
projects_card.grid(row=5, column=0, columnspan=2, sticky="nsew", padx=(0, 12))
project_body = ctk.CTkFrame(projects_card, fg_color="transparent")
project_body.pack(fill="both", expand=True, padx=18, pady=(0, 16))
for column in range(7):
    project_body.grid_columnconfigure(column, weight=1)

right = ctk.CTkFrame(main, width=286, fg_color="transparent")
right.grid(row=1, column=2, rowspan=5, sticky="nsew")
right.grid_propagate(False)

level_card = ctk.CTkFrame(right, fg_color=COLORS["surface"], corner_radius=22, border_width=1, border_color=COLORS["line"])
level_card.pack(fill="x", pady=(0, 12))
rank_label = ctk.CTkLabel(level_card, text="Rookie Planner", font=("Segoe UI Semibold", 14), text_color=COLORS["text"])
rank_label.pack(anchor="w", padx=16, pady=(14, 0))
level_label = ctk.CTkLabel(level_card, text="Level 1", font=("Segoe UI Semibold", 25), text_color=COLORS["deep"])
level_label.pack(anchor="w", padx=16)
xp_label = ctk.CTkLabel(level_card, text="0 / 250 XP", font=("Segoe UI", 12), text_color=COLORS["muted"])
xp_label.pack(anchor="w", padx=16, pady=(0, 6))
xp_bar = AnimatedBar(level_card, width=226, height=14, color=COLORS["pink"])
xp_bar.pack(fill="x", padx=16, pady=(0, 14))

attendance_meter = CircularMeter(right, "Attendance", 0, COLORS["pink"], diameter=118)
attendance_meter.pack(fill="x", pady=(0, 12))

meter_pair = ctk.CTkFrame(right, fg_color="transparent")
meter_pair.pack(fill="x", pady=(0, 12))
meter_pair.grid_columnconfigure((0, 1), weight=1)
homework_meter = CircularMeter(meter_pair, "Homework", 0, COLORS["teal"], diameter=104)
homework_meter.grid(row=0, column=0, sticky="ew", padx=(0, 6))
rating_meter = CircularMeter(meter_pair, "Rating", 0, COLORS["yellow"], diameter=104)
rating_meter.grid(row=0, column=1, sticky="ew", padx=(6, 0))

attendance_actions = ctk.CTkFrame(right, fg_color=COLORS["surface"], corner_radius=22, border_width=1, border_color=COLORS["line"])
attendance_actions.pack(fill="x", pady=(0, 12))
attendance_status = ctk.CTkLabel(attendance_actions, text="Loading attendance", font=("Segoe UI Semibold", 13), text_color=COLORS["text"], wraplength=160)
attendance_status.pack(anchor="w", padx=16, pady=(14, 8))
attendance_hint = ctk.CTkLabel(attendance_actions, text="", font=("Segoe UI", 11), text_color=COLORS["muted"], wraplength=168, justify="left")
attendance_hint.pack(anchor="w", padx=16, pady=(0, 8))
mark_present_btn = ctk.CTkButton(attendance_actions, text="Mark present today", height=36, corner_radius=14, fg_color=COLORS["deep"], hover_color=COLORS["deep_hover"], command=lambda: mark_today_present())
mark_present_btn.pack(fill="x", padx=16, pady=(0, 12))
leave_menu = ctk.CTkOptionMenu(
    attendance_actions,
    values=WEEKDAY_NAMES,
    height=38,
    corner_radius=16,
    fg_color=COLORS["panel_soft"],
    button_color=COLORS["deep"],
    button_hover_color=COLORS["deep_hover"],
    text_color=COLORS["text"],
    command=lambda day_name: change_leave_day(day_name),
)
leave_menu.pack(fill="x", padx=16, pady=(0, 14))

more_btn = ctk.CTkButton(
    right,
    text="Open task board",
    height=40,
    corner_radius=16,
    fg_color=COLORS["secondary"],
    hover_color=COLORS["secondary_hover"],
    text_color=COLORS["secondary_text"],
    command=lambda: open_script("view_tasks.py"),
)
more_btn.pack(fill="x")

subject_widgets = []
event_widgets = []
task_widgets = []
week_widgets = []
project_widgets = []
mission_widgets = []
leaderboard_widgets = []
badge_widgets = []
project_dynamic_widgets = []


def clear_pool(pool):
    for widget in pool:
        widget.pack_forget()
        widget.grid_forget()


def project_label(*args, **kwargs):
    label = ctk.CTkLabel(*args, **kwargs)
    project_dynamic_widgets.append(label)
    return label


def subject_row(index):
    while len(subject_widgets) <= index:
        row = ctk.CTkFrame(teachers_card, fg_color="transparent")
        row.grid_columnconfigure(1, weight=1)
        icon = make_icon(row, "*")
        icon.grid(row=0, column=0, sticky="w", padx=(18, 10), pady=5)
        text = ctk.CTkLabel(row, text="", font=("Segoe UI", 12), text_color=COLORS["text"], anchor="w")
        text.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        resource_var = ctk.StringVar(value="Select resource")
        menu = ctk.CTkOptionMenu(
            row,
            values=["Select resource"],
            variable=resource_var,
            width=154,
            height=32,
            corner_radius=12,
            fg_color=COLORS["panel_soft"],
            button_color=COLORS["deep"],
            button_hover_color=COLORS["deep_hover"],
            text_color=COLORS["text"],
            dropdown_fg_color=COLORS["surface"],
            dropdown_text_color=COLORS["text"],
        )
        open_btn = ctk.CTkButton(
            row,
            text="Open",
            width=72,
            height=32,
            corner_radius=12,
            fg_color=COLORS["teal"],
            hover_color=COLORS["primary_hover"],
            text_color=COLORS["white"],
        )
        menu.grid(row=0, column=2, sticky="e", padx=(0, 10))
        open_btn.grid(row=0, column=3, sticky="e", padx=(0, 18))
        row.text = text
        row.resource_var = resource_var
        row.resource_menu = menu
        row.open_btn = open_btn
        row.resource_links = {}
        subject_widgets.append(row)
    return subject_widgets[index]


def event_row(index):
    while len(event_widgets) <= index:
        row = ctk.CTkFrame(events_card, fg_color="transparent")
        badge = ctk.CTkLabel(row, text="", width=54, height=54, corner_radius=18, fg_color=COLORS["teal"], text_color=COLORS["white"], font=("Segoe UI Semibold", 13))
        badge.pack(side="left", padx=(18, 10), pady=4)
        text = ctk.CTkLabel(row, text="", font=("Segoe UI", 12), text_color=COLORS["text"], justify="left", anchor="w")
        text.pack(side="left", fill="x", expand=True)
        row.badge = badge
        row.text = text
        event_widgets.append(row)
    return event_widgets[index]


def task_row(index):
    while len(task_widgets) <= index:
        row = ctk.CTkFrame(task_list, fg_color=COLORS["panel_soft"], corner_radius=18)
        day = ctk.CTkLabel(row, text="", width=46, font=("Segoe UI Semibold", 16), text_color=COLORS["muted"])
        day.pack(side="left", padx=(12, 8), pady=6)
        text = ctk.CTkLabel(row, text="", font=("Segoe UI", 12), text_color=COLORS["text"], anchor="w", justify="left")
        text.pack(side="left", fill="x", expand=True, padx=(0, 10))
        row.day = day
        row.text = text
        task_widgets.append(row)
    return task_widgets[index]


def week_chip(index):
    while len(week_widgets) <= index:
        chip = ctk.CTkFrame(project_body, width=78, height=72, corner_radius=18, fg_color=COLORS["panel_soft"])
        chip.grid_propagate(False)
        label = ctk.CTkLabel(chip, text="", font=("Segoe UI Semibold", 12), text_color=COLORS["text"])
        label.place(relx=0.5, rely=0.34, anchor="center")
        status = ctk.CTkLabel(chip, text="", font=("Segoe UI", 11), text_color=COLORS["muted"])
        status.place(relx=0.5, rely=0.66, anchor="center")
        chip.label = label
        chip.status = status
        week_widgets.append(chip)
    return week_widgets[index]


def mission_row(index):
    while len(mission_widgets) <= index:
        row = ctk.CTkFrame(project_body, fg_color=COLORS["panel_soft"], corner_radius=16)
        status = ctk.CTkLabel(row, text="", width=30, height=30, corner_radius=15, fg_color=COLORS["deep"], text_color=COLORS["white"])
        status.pack(side="left", padx=(10, 8), pady=8)
        text = ctk.CTkLabel(row, text="", font=("Segoe UI", 12), text_color=COLORS["text"], anchor="w", justify="left")
        text.pack(side="left", fill="x", expand=True)
        reward = ctk.CTkLabel(row, text="", font=("Segoe UI Semibold", 12), text_color=COLORS["pink"])
        reward.pack(side="right", padx=10)
        row.status = status
        row.text = text
        row.reward = reward
        mission_widgets.append(row)
    return mission_widgets[index]


def leaderboard_row(index):
    while len(leaderboard_widgets) <= index:
        row = ctk.CTkFrame(project_body, fg_color="transparent")
        text = ctk.CTkLabel(row, text="", font=("Segoe UI", 12), text_color=COLORS["muted"], anchor="w")
        text.pack(fill="x")
        row.text = text
        leaderboard_widgets.append(row)
    return leaderboard_widgets[index]


def badge_chip(index):
    while len(badge_widgets) <= index:
        chip = ctk.CTkLabel(project_body, text="", height=30, corner_radius=15, fg_color=COLORS["deep"], text_color=COLORS["white"], font=("Segoe UI Semibold", 11))
        badge_widgets.append(chip)
    return badge_widgets[index]


def render_loading():
    hello.configure(text=f"HELLO, {username.upper()}!")
    profile_text.configure(text=username)
    attendance_status.configure(text="Loading attendance")
    attendance_hint.configure(text="")


def refresh_dashboard():
    global load_token
    load_token += 1
    token = load_token
    render_loading()

    def worker():
        started = datetime.now()
        try:
            data = load_dashboard_snapshot(username)
            game = XPSystem(data.user.get("username") or username).game_state()
            elapsed_ms = int((datetime.now() - started).total_seconds() * 1000)
            load_queue.put(("ok", token, (data, game), elapsed_ms))
        except Exception as exc:
            load_queue.put(("error", token, exc, 0))

    # Backend work stays off the Tk thread. The UI polls with after(), which is
    # the safe Tkinter pattern for smooth startup and page refreshes.
    threading.Thread(target=worker, daemon=True).start()
    app.after(30, poll_dashboard)


def poll_dashboard():
    try:
        status, token, payload, elapsed_ms = load_queue.get_nowait()
    except queue.Empty:
        app.after(30, poll_dashboard)
        return

    if token != load_token:
        return
    if status == "error":
        messagebox.showerror("Dashboard", str(payload))
        return
    data, game = payload
    render_dashboard(data, game, elapsed_ms)


def render_dashboard(data, game, elapsed_ms=0):
    global snapshot, game_state, username
    snapshot = data
    game_state = game
    username = snapshot.user.get("username") or username
    name = user_first_name()
    hello.configure(text=f"HELLO, {name.upper()}!")
    profile_text.configure(text=f"{snapshot.user.get('name') or username}\nStudent")
    avatar.configure(text=(name[:1] or "S").upper())

    clear_pool(subject_widgets)
    for index, subject in enumerate(snapshot.subjects[:4]):
        row = subject_row(index)
        row.text.configure(text=subject)
        links = resource_links_for(subject)
        labels = [label for label, _url in links]
        row.resource_links = dict(links)
        row.resource_menu.configure(values=labels)
        row.resource_var.set(labels[0] if labels else "Select resource")
        row.open_btn.configure(command=lambda widget=row: open_selected_resource(widget))
        row.pack(fill="x", pady=7)

    clear_pool(event_widgets)
    events = snapshot.reminder_tasks[:4] or snapshot.summary["reminders"][:4]
    if not events:
        events = [{"title": "No deadline today", "subject": "Plan freely", "due_date": date.today().isoformat()}]
    for index, task in enumerate(events):
        row = event_row(index)
        row.badge.configure(text=format_date(task.get("due_date") or task.get("study_date")))
        row.text.configure(text=f"{task.get('title', 'Study session')}\n{task.get('subject') or 'Science'}")
        row.pack(fill="x", pady=7)

    render_schedule()
    render_game_header()
    render_metric_tiles()
    render_attendance()
    render_projects(elapsed_ms)
    maybe_reward_popup()


def render_metric_tiles():
    summary = snapshot.summary
    total_tile.set(summary.get("total_tasks", 0))
    completion_tile.set(f"{summary.get('completion_rate', 0)}%")
    streak_tile.set(f"{game_state.get('study_streak', 0)}d")
    consistency_tile.set(f"{game_state.get('consistency_score', 0)}%")


def render_schedule():
    clear_pool(task_widgets)
    today = date.today()
    month_rows = calendar.monthcalendar(today.year, today.month)
    compact_rows = []
    for row in month_rows[:4]:
        compact_rows.append(" ".join(f"{day:>2}" if day else "  " for day in row[:5]))
    calendar_label.configure(text=f"{today.strftime('%b %Y')}\n\nMo Tu We Th Fr\n" + "\n".join(compact_rows))
    tasks = snapshot.upcoming_tasks[:3] if snapshot else []
    if not tasks:
        tasks = [{"title": "Add your next study task", "subject": "Schedly", "due_date": today.isoformat()}]
    for index, task in enumerate(tasks):
        row = task_row(index)
        row.day.configure(text=format_date(task.get("study_date") or task.get("due_date")).split(" ")[0])
        row.text.configure(text=f"{task.get('title')}\n{task.get('subject') or 'General'}")
        row.pack(fill="x", pady=4)


def render_game_header():
    rank_label.configure(text=game_state["rank_title"])
    level_label.configure(text=f"Level {game_state['level']}")
    xp_label.configure(text=f"{game_state['current_level_xp']} / {game_state['next_level_xp']} XP")
    xp_bar.animate_to(game_state["level_progress"])


def render_attendance():
    attendance = snapshot.attendance
    attendance_meter.draw(attendance["percentage"])
    homework_meter.draw(snapshot.summary["completion_rate"])
    rating_value = min(100, max(0, 100 - (snapshot.summary.get("overdue_tasks", 0) * 10)))
    rating_meter.draw(rating_value)
    leave_menu.set(attendance["leave_day_name"])
    leave_enabled = attendance.get("leave_enabled", True)
    leave_menu.configure(state="normal" if leave_enabled else "disabled")
    if leave_enabled:
        attendance_hint.configure(text=f"Weekly leave: {attendance['leave_day_name']}. Holiday locks if attendance falls below 75%.")
    else:
        attendance_hint.configure(text="Weekly holiday is locked until attendance reaches 75% again.")

    if attendance["today_is_leave"]:
        attendance_status.configure(text=f"Today is your weekly leave day ({attendance['leave_day_name']}).")
        mark_present_btn.configure(text="Leave day", state="disabled", fg_color="#a98da3")
    elif attendance["today_status"] == "present":
        attendance_status.configure(text="Present marked for today.")
        mark_present_btn.configure(text="Marked present", state="disabled", fg_color=COLORS["green"])
    else:
        attendance_status.configure(text="Mark present today to keep attendance complete.")
        mark_present_btn.configure(text="Mark present today", state="normal", fg_color=COLORS["deep"])


def render_projects(elapsed_ms):
    for widget in list(project_dynamic_widgets):
        if widget.winfo_exists():
            widget.destroy()
    project_dynamic_widgets.clear()
    clear_pool(week_widgets)
    clear_pool(mission_widgets)
    clear_pool(leaderboard_widgets)
    clear_pool(badge_widgets)

    project_label(project_body, text=game_state["quote"], font=("Segoe UI Semibold", 13), text_color=COLORS["deep"]).grid(row=0, column=0, columnspan=7, sticky="w", padx=6, pady=(0, 8))
    for index, item in enumerate(snapshot.attendance["week"]):
        chip = week_chip(index)
        status = item["status"].title()
        color = COLORS["green"] if item["status"] == "present" else COLORS["yellow"] if item["status"] == "leave" else COLORS["card_light"]
        chip.configure(fg_color=color)
        chip.label.configure(text=item["label"])
        chip.status.configure(text=status)
        chip.grid(row=1, column=index, sticky="ew", padx=5, pady=5)

    info = ctk.CTkLabel(
        project_body,
        text=(
            f"🔥 Study streak {game_state['study_streak']} day(s)   "
            f"🎯 Task streak {game_state['task_streak']}   "
            f"Consistency {game_state['consistency_score']}%   "
            f"Refresh {elapsed_ms} ms"
        ),
        font=("Segoe UI", 12),
        text_color=COLORS["muted"],
    )
    while len(project_widgets) < 1:
        project_widgets.append(info)
    if project_widgets[0] is not info:
        project_widgets[0].destroy()
        project_widgets[0] = info
    info.grid(row=2, column=0, columnspan=7, sticky="w", padx=6, pady=(12, 0))

    project_label(project_body, text="Daily missions", font=("Segoe UI Semibold", 14), text_color=COLORS["text"]).grid(row=3, column=0, columnspan=3, sticky="w", padx=6, pady=(16, 6))
    for index, mission in enumerate(game_state["daily_missions"]):
        row = mission_row(index)
        row.status.configure(text="✓" if mission["done"] else "!")
        row.status.configure(fg_color=COLORS["green"] if mission["done"] else COLORS["deep"])
        row.text.configure(text=f"{mission['title']}\n{mission['detail']}")
        row.reward.configure(text=f"+{mission['reward']} XP")
        row.grid(row=4 + index, column=0, columnspan=3, sticky="ew", padx=6, pady=4)

    project_label(project_body, text="Weekly challenges", font=("Segoe UI Semibold", 14), text_color=COLORS["text"]).grid(row=3, column=3, columnspan=4, sticky="w", padx=12, pady=(16, 6))
    for index, challenge in enumerate(game_state["weekly_challenges"][:3]):
        row = leaderboard_row(index)
        percent = round((challenge["progress"] / max(challenge["target"], 1)) * 100)
        row.text.configure(text=f"{challenge['title']}  {challenge['progress']}/{challenge['target']}  (+{challenge['reward']} XP)  {percent}%")
        row.grid(row=4 + index, column=3, columnspan=4, sticky="ew", padx=12, pady=4)

    project_label(project_body, text="Badges", font=("Segoe UI Semibold", 14), text_color=COLORS["text"]).grid(row=7, column=0, sticky="w", padx=6, pady=(16, 6))
    badges = game_state["achievements"][:4] or [{"badge_name": "First badge soon"}]
    for index, badge in enumerate(badges):
        chip = badge_chip(index)
        chip.configure(text=f"🏅 {badge.get('badge_name')}")
        chip.grid(row=8, column=index, sticky="w", padx=5, pady=4)

    project_label(project_body, text="Leaderboard", font=("Segoe UI Semibold", 14), text_color=COLORS["text"]).grid(row=7, column=4, columnspan=3, sticky="w", padx=12, pady=(16, 6))
    for index, row_data in enumerate(game_state["leaderboard"][:3]):
        row = leaderboard_row(index + 3)
        row.text.configure(text=f"#{index + 1} {row_data['name']}  L{row_data['level']}  {row_data['total_xp']} XP")
        row.grid(row=8 + index, column=4, columnspan=3, sticky="ew", padx=12, pady=2)

    unlock = game_state.get("next_unlock")
    unlock_text = f"Next unlock: {unlock['name']} at Level {unlock['level']}" if unlock else "All current themes unlocked"
    project_label(project_body, text=unlock_text, font=("Segoe UI", 12), text_color=COLORS["muted"]).grid(row=11, column=0, columnspan=7, sticky="w", padx=6, pady=(12, 0))


def run_db_action(action, *args):
    def worker():
        try:
            action(*args)
            app.after(0, refresh_dashboard)
        except Exception as exc:
            app.after(0, lambda: messagebox.showerror("Attendance", str(exc)))

    threading.Thread(target=worker, daemon=True).start()


def mark_today_present():
    mark_present_btn.configure(text="Saving...", state="disabled")
    def save_and_reward():
        database.mark_attendance(username, date.today().isoformat(), "present")
        XPSystem(username).award_attendance(date.today().isoformat())

    run_db_action(save_and_reward)


def change_leave_day(day_name):
    if day_name not in WEEKDAY_NAMES:
        return
    if snapshot and not snapshot.attendance.get("leave_enabled", True):
        leave_menu.set(snapshot.attendance["leave_day_name"])
        attendance_hint.configure(text="Weekly holiday is locked until attendance reaches 75% again.")
        return
    leave_menu.configure(state="disabled")

    def worker():
        try:
            database.update_attendance_leave_day(username, WEEKDAY_NAMES.index(day_name))
            app.after(0, refresh_dashboard)
        except Exception as exc:
            app.after(0, lambda: messagebox.showerror("Attendance", str(exc)))
        finally:
            app.after(0, lambda: leave_menu.configure(state="normal"))

    threading.Thread(target=worker, daemon=True).start()


def maybe_reward_popup():
    global displayed_total_xp
    current_xp = int(game_state.get("total_xp", 0))
    if displayed_total_xp is None:
        displayed_total_xp = current_xp
        return
    if current_xp <= displayed_total_xp:
        displayed_total_xp = current_xp
        return
    gained = current_xp - displayed_total_xp
    displayed_total_xp = current_xp
    show_reward_popup(gained)


def show_reward_popup(points):
    popup = ctk.CTkToplevel(app)
    popup.title("Reward")
    popup.geometry("360x240")
    popup.resizable(False, False)
    popup.configure(fg_color=COLORS["shell"])
    popup.attributes("-topmost", True)
    x_pos = app.winfo_x() + max(app.winfo_width() - 400, 80)
    y_pos = app.winfo_y() + 80
    popup.geometry(f"360x240+{x_pos}+{y_pos}")
    card = ctk.CTkFrame(popup, fg_color=COLORS["card"], corner_radius=26)
    card.pack(fill="both", expand=True, padx=18, pady=18)
    ctk.CTkLabel(card, text="Quest reward!", font=("Segoe UI Semibold", 24), text_color=COLORS["deep"]).pack(pady=(22, 4))
    ctk.CTkLabel(card, text=f"+{points} XP", font=("Segoe UI Semibold", 34), text_color=COLORS["pink"]).pack()
    ctk.CTkLabel(card, text="Momentum unlocked. Keep the streak alive.", font=("Segoe UI", 12), text_color=COLORS["muted"]).pack(pady=(4, 8))
    confetti = Canvas(card, width=300, height=62, highlightthickness=0, bg=COLORS["card"])
    confetti.pack()
    pieces = []
    palette = [COLORS["pink"], COLORS["teal"], COLORS["yellow"], COLORS["green"], COLORS["deep"]]
    for index in range(24):
        x = 20 + (index * 12) % 260
        y = 8 + (index * 17) % 44
        piece = confetti.create_rectangle(x, y, x + 6, y + 10, fill=palette[index % len(palette)], outline="")
        pieces.append((piece, (index % 5) - 2, 2 + (index % 3)))

    def animate(step=0):
        for piece, dx, dy in pieces:
            confetti.move(piece, dx, dy)
        if step < 32 and popup.winfo_exists():
            popup.after(30, lambda: animate(step + 1))
        elif popup.winfo_exists():
            popup.after(900, popup.destroy)

    animate()


def open_selected_resource(row):
    label = row.resource_var.get()
    url = row.resource_links.get(label)
    if url:
        webbrowser.open(url)


refresh_dashboard()
app.mainloop()
