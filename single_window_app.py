import calendar
import json
import os
import re
import shutil
import subprocess
import sys
import webbrowser
from datetime import date, datetime
from pathlib import Path
from tkinter import Canvas, colorchooser, filedialog, messagebox, ttk

import customtkinter as ctk

import ai_review
import database
import study_timetable
from analytics.weakness_analyzer import WeaknessAnalyzer
from dashboard_model import WEEKDAY_NAMES, load_dashboard_snapshot
from gamification.xp_system import XPSystem
from settings.settings_manager import settings_manager
from theme_manager import apply_theme, get_fonts, get_theme_colors, load_theme, save_theme
from tk_safety import disable_unsafe_windows_titlebar_focus_restore
from ui.modern import style_treeview


APP_WIDTH = 1280
APP_HEIGHT = 800
INSTRUCTIONS_PDF = Path(__file__).resolve().parent / "instructions.pdf"

NAV_ITEMS = [
    ("Dashboard", "dashboard"),
    ("Add Task", "add_task"),
    ("Progress", "progress"),
    ("Tasks", "tasks"),
    ("Analytics", "analytics"),
    ("Settings", "settings"),
]

NAV_ICONS = {
    "dashboard": "⌂",
    "add_task": "+",
    "progress": "◎",
    "tasks": "☷",
    "analytics": "◆",
    "settings": "⚙",
    "logout": "↩",
}

RESOURCE_MAP = {
    "Science": [("Khan Academy", "https://www.khanacademy.org/science"), ("Crash Course", "https://thecrashcourse.com/")],
    "Technology": [("freeCodeCamp", "https://www.freecodecamp.org/"), ("CS50", "https://cs50.harvard.edu/")],
    "Commerce": [("Investopedia", "https://www.investopedia.com/"), ("edX Finance", "https://www.edx.org/learn/finance")],
    "Humanities": [("OpenLearn", "https://www.open.edu/openlearn/history-the-arts"), ("BBC History", "https://www.bbc.co.uk/history")],
    "Languages": [("Duolingo", "https://www.duolingo.com/"), ("Memrise", "https://www.memrise.com/")],
}


def sync_global_preferences(preferences):
    settings_manager.save(preferences)


def fmt_date(value):
    if not value:
        return "-"
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %b %Y")
    except ValueError:
        return value


def _task_date_parse_display(value):
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    return None


def _task_date_to_storage(value):
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _count_words(text):
    if not text:
        return 0
    return len(re.findall(r"\w+", text, flags=re.UNICODE))


def _document_word_count(path):
    ext = os.path.splitext(path or "")[1].lower()
    try:
        if ext == ".pdf":
            from PyPDF2 import PdfReader

            reader = PdfReader(path)
            blob = "\n".join((page.extract_text() or "") for page in reader.pages)
            return _count_words(blob)
        if ext == ".docx":
            from docx import Document

            doc = Document(path)
            blob = "\n".join(p.text for p in doc.paragraphs)
            return _count_words(blob)
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            return _count_words(handle.read())
    except Exception:
        return 0


class SingleWindowApp(ctk.CTk):
    def __init__(self, initial_page="login", username=""):
        super().__init__()
        disable_unsafe_windows_titlebar_focus_restore()
        database.connect()

        self.current_theme = load_theme()
        ctk.set_appearance_mode(self.current_theme)
        ctk.set_default_color_theme("blue")

        self.colors = get_theme_colors()
        self.username = (username or "").strip()
        self.preferences = database.get_user_preferences(self.username) if self.username else settings_manager.load()
        self.current_theme = self.preferences["appearance_mode"]
        ctk.set_appearance_mode(self.current_theme)
        self.colors = get_theme_colors(self.preferences)
        if self.username:
            sync_global_preferences(self.preferences)
        self.current_page = None
        self.task_filter = ""
        self.nav_buttons = {}

        self.title("Schedly")
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        self.minsize(1120, 720)
        self.configure(fg_color=self.colors["bg"])
        try:
            self.attributes("-alpha", 0.0)
        except Exception:
            pass

        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True)

        self.auth_frame = None
        self.shell = None
        self.sidebar = None
        self.content = None
        self.transition_mask = None

        if self.username:
            self.build_shell()
            self.show_page(initial_page if initial_page in {page for _, page in NAV_ITEMS} else "dashboard", animate=False)
        elif initial_page == "register":
            self.show_register()
        else:
            self.show_login()
        self.after(40, self.reveal_startup)

    def reveal_startup(self):
        self.maximize_window()
        try:
            self.attributes("-alpha", 1.0)
        except Exception:
            pass

    def maximize_window(self):
        try:
            self.state("zoomed")
        except Exception:
            try:
                width = self.winfo_screenwidth()
                height = self.winfo_screenheight()
                self.geometry(f"{width}x{height}+0+0")
            except Exception:
                self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")

    def show_info(self, title, message):
        return messagebox.showinfo(title, message, parent=self)

    def show_warning(self, title, message):
        return messagebox.showwarning(title, message, parent=self)

    def show_error(self, title, message):
        return messagebox.showerror(title, message, parent=self)

    def ask_yes_no(self, title, message):
        return messagebox.askyesno(title, message, parent=self)

    def set_theme(self, mode):
        target_page = self.current_page
        if self.username:
            self.preferences = database.update_user_preferences(self.username, appearance_mode=mode)
        else:
            save_theme(mode)
            self.preferences = settings_manager.load()
        sync_global_preferences(self.preferences)
        self.current_theme = self.preferences["appearance_mode"]
        ctk.set_appearance_mode(self.current_theme)
        self.colors = get_theme_colors(self.preferences)
        self.configure(fg_color=self.colors["bg"])
        if self.current_page in {"login", "register"}:
            self.show_register() if self.current_page == "register" else self.show_login()
        else:
            self.build_shell()
            self.show_page(target_page or "dashboard", animate=False)

    def load_user_preferences(self):
        self.preferences = database.get_user_preferences(self.username) if self.username else settings_manager.load()
        self.current_theme = self.preferences["appearance_mode"]
        ctk.set_appearance_mode(self.current_theme)
        self.colors = get_theme_colors(self.preferences)
        if self.username:
            sync_global_preferences(self.preferences)

    def clear_root(self):
        self.unbind("<Return>")
        for child in self.container.winfo_children():
            child.destroy()
        self.auth_frame = None
        self.shell = None
        self.sidebar = None
        self.content = None

    def show_login(self):
        self.current_page = "login"
        self.clear_root()
        colors = self.colors
        self.auth_frame = ctk.CTkFrame(self.container, fg_color=colors["bg"])
        self.auth_frame.pack(fill="both", expand=True)

        outer = ctk.CTkFrame(self.auth_frame, fg_color=colors["bg_soft"], corner_radius=0)
        outer.pack(fill="both", expand=True)
        stage = ctk.CTkFrame(outer, corner_radius=36, fg_color=colors["panel"], border_width=1, border_color=colors["panel_border"])
        stage.pack(fill="both", expand=True, padx=54, pady=44)
        stage.grid_columnconfigure(0, weight=12)
        stage.grid_columnconfigure(1, weight=8)
        stage.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(stage, fg_color=colors["surface"], corner_radius=30, border_width=1, border_color=colors["surface_border"])
        left.grid(row=0, column=0, sticky="nsew", padx=(28, 14), pady=28)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure((0, 2), weight=1)
        left.grid_rowconfigure(1, weight=0)
        ctk.CTkLabel(left, text="+", font=("Segoe UI Semibold", 28), text_color=colors["primary"]).place(relx=0.14, rely=0.18, anchor="center")
        ctk.CTkLabel(left, text="*", font=("Segoe UI Semibold", 24), text_color=colors["deep"]).place(relx=0.86, rely=0.24, anchor="center")
        ctk.CTkLabel(left, text="/", font=("Segoe UI Semibold", 30), text_color=colors["muted"]).place(relx=0.2, rely=0.82, anchor="center")
        ctk.CTkLabel(left, text="#", font=("Segoe UI Semibold", 20), text_color=colors["primary"]).place(relx=0.76, rely=0.14, anchor="center")
        ctk.CTkLabel(left, text="@", font=("Segoe UI Semibold", 18), text_color=colors["muted"]).place(relx=0.11, rely=0.68, anchor="center")
        ctk.CTkLabel(left, text="x", font=("Segoe UI Semibold", 18), text_color=colors["deep"]).place(relx=0.82, rely=0.76, anchor="center")
        ctk.CTkLabel(left, text="o", font=("Segoe UI Semibold", 20), text_color=colors["primary"]).place(relx=0.9, rely=0.58, anchor="center")
        ctk.CTkLabel(left, text="::", font=("Segoe UI Semibold", 18), text_color=colors["muted"]).place(relx=0.28, rely=0.25, anchor="center")
        accent_line = ctk.CTkFrame(left, width=120, height=6, corner_radius=999, fg_color=colors["primary"])
        accent_line.place(relx=0.5, rely=0.32, anchor="center")
        brand_panel = ctk.CTkFrame(left, fg_color="transparent")
        brand_panel.grid(row=1, column=0, sticky="", padx=56, pady=36)
        ctk.CTkLabel(brand_panel, text="Schedly", font=("Segoe UI Semibold", 72), text_color=colors["text"]).pack(anchor="center")
        ctk.CTkLabel(
            brand_panel,
            text="A calm, organized study planner for academic life.",
            font=("Segoe UI", 20),
            text_color=colors["muted"],
            wraplength=520,
            justify="center",
        ).pack(anchor="center", pady=(14, 28))
        ctk.CTkFrame(brand_panel, width=260, height=1, fg_color=colors["surface_border"]).pack(anchor="center", pady=(0, 22))
        ctk.CTkLabel(
            brand_panel,
            text="Simple planning. Clear focus. Less clutter.",
            font=("Segoe UI Semibold", 13),
            text_color=colors["deep"],
        ).pack(anchor="center")
        card = ctk.CTkFrame(stage, corner_radius=30, fg_color=colors["surface"], border_width=1, border_color=colors["surface_border"])
        card.grid(row=0, column=1, sticky="nsew", padx=(14, 28), pady=28)
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure((0, 2), weight=1)

        form = ctk.CTkFrame(card, fg_color="transparent")
        form.grid(row=1, column=0, sticky="ew", padx=46)
        form.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(form, text="Welcome back", font=("Segoe UI Semibold", 34), text_color=colors["text"]).grid(row=0, column=0, sticky="w", pady=(0, 8))
        ctk.CTkLabel(form, text="Sign in to continue your study flow.", font=("Segoe UI", 14), text_color=colors["muted"]).grid(row=1, column=0, sticky="w", pady=(0, 30))
        self.form_label(form, "Username or email", get_fonts(self.preferences)).grid(row=2, column=0, sticky="w", pady=(0, 6))
        username_entry = self.auth_entry(form, "Username or email", "@")
        username_entry.grid(row=3, column=0, sticky="ew", pady=(0, 14))
        self.form_label(form, "Password", get_fonts(self.preferences)).grid(row=4, column=0, sticky="w", pady=(0, 6))
        password_entry = self.auth_entry(form, "Password", "#", show="*")
        password_entry.grid(row=5, column=0, sticky="ew", pady=(0, 14))
        utility_row = ctk.CTkFrame(form, fg_color="transparent")
        utility_row.grid(row=6, column=0, sticky="ew", pady=(0, 24))
        remember_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(utility_row, text="Remember me", variable=remember_var, width=22, height=22, corner_radius=7, border_width=2, text_color=colors["muted"], fg_color=colors["primary"], hover_color=colors["primary_hover"]).pack(side="left")
        forgot = ctk.CTkLabel(utility_row, text="Forgot password?", font=("Segoe UI Semibold", 12), text_color=colors["link"], cursor="hand2")
        forgot.pack(side="right")
        forgot.bind("<Button-1>", lambda _event: self.show_info("Password Help", "Password reset is not configured for this local app. Create a new account or ask your app admin to reset access."))
        error = ctk.CTkLabel(form, text="", font=("Segoe UI Semibold", 12), text_color=colors["danger"], wraplength=380)
        error.grid(row=7, column=0, sticky="w", pady=(0, 8))

        def submit(_event=None):
            username = username_entry.get().strip()
            password = password_entry.get()
            user = database.login_user(username, password)
            if not user:
                error.configure(text="Invalid credentials. Check your username/email and password.")
                return
            self.username = user["username"]
            self.load_user_preferences()
            self.build_shell()
            self.show_page("dashboard", animate=False)

        self.button(form, "Login", submit, height=48).grid(row=8, column=0, sticky="ew", pady=(4, 12))
        self.button(form, "Create account", self.show_register, variant="secondary", height=48).grid(row=9, column=0, sticky="ew", pady=(0, 22))
        ctk.CTkLabel(form, text="One window. Your data stays local.", font=("Segoe UI", 11), text_color=colors["muted"]).grid(row=10, column=0, sticky="ew")
        self.bind("<Return>", submit)
        username_entry.focus()

    def show_register(self):
        self.current_page = "register"
        self.clear_root()
        colors = self.colors
        frame = ctk.CTkFrame(self.container, fg_color=colors["bg"])
        frame.pack(fill="both", expand=True)
        card = ctk.CTkFrame(frame, width=520, corner_radius=30, fg_color=colors["panel"], border_width=1, border_color=colors["panel_border"])
        card.place(relx=0.5, rely=0.52, anchor="center")
        card.configure(height=720)
        card.pack_propagate(False)

        ctk.CTkLabel(card, text="Create your account", font=("Segoe UI Semibold", 28), text_color=colors["text"]).pack(pady=(38, 8))
        ctk.CTkLabel(card, text="Registration stays in this app window.", font=("Segoe UI", 13), text_color=colors["muted"]).pack(pady=(0, 24))
        fonts = get_fonts(self.preferences)

        def labeled_auth_field(label, placeholder, show=None):
            self.form_label(card, label, fonts).pack(anchor="w", padx=56, pady=(0, 6))
            field = self.entry(card, placeholder, show=show)
            field.pack(fill="x", padx=56, pady=(0, 12))
            return field

        name_entry = labeled_auth_field("Full name", "Full name")
        email_entry = labeled_auth_field("Email", "Email")
        username_entry = labeled_auth_field("Username", "Username")
        password_entry = labeled_auth_field("Password", "Password", show="*")
        confirm_entry = labeled_auth_field("Confirm password", "Confirm password", show="*")
        status = ctk.CTkLabel(card, text="", font=("Segoe UI Semibold", 12), text_color=colors["danger"], wraplength=360)
        status.pack(pady=(0, 12))

        def submit():
            name = name_entry.get().strip()
            email = email_entry.get().strip()
            username = username_entry.get().strip()
            password = password_entry.get()
            confirm = confirm_entry.get()
            if not all([name, email, username, password, confirm]):
                status.configure(text="All fields are required.")
                return
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                status.configure(text="Enter a valid email address.")
                return
            if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
                status.configure(text="Username must be 3-32 letters, numbers, dots, dashes, or underscores.")
                return
            if len(password) < 8:
                status.configure(text="Password must be at least 8 characters.")
                return
            if password != confirm:
                status.configure(text="Passwords do not match.")
                return
            if not database.register_user(name, email, username, password):
                status.configure(text="Username or email already exists.")
                return
            self.username = username
            database.update_user_preferences(username, **database.DEFAULT_USER_PREFERENCES)
            self.load_user_preferences()
            self.build_shell()
            self.show_page("dashboard", animate=False)

        self.button(card, "Register", submit).pack(fill="x", padx=56, pady=(4, 12))
        self.button(card, "Back to login", self.show_login, variant="secondary").pack(fill="x", padx=56)
        self.bind("<Return>", lambda _event: submit())
        name_entry.focus()

    def build_shell(self):
        self.clear_root()
        colors = self.colors
        self.current_page = None
        self.nav_buttons = {}
        self.shell = ctk.CTkFrame(self.container, corner_radius=32, fg_color=colors["panel"], border_width=1, border_color=colors["panel_border"])
        self.shell.pack(fill="both", expand=True, padx=22, pady=22)
        self.shell.grid_columnconfigure(0, weight=0)
        self.shell.grid_columnconfigure(1, weight=1)
        self.shell.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self.shell, width=214, corner_radius=28, fg_color=colors["sidebar"], border_width=1, border_color=colors["sidebar_border"])
        self.sidebar.grid(row=0, column=0, sticky="nsw", padx=(14, 0), pady=14)
        self.sidebar.grid_propagate(False)

        ctk.CTkLabel(self.sidebar, text="Schedly", font=("Segoe UI Semibold", 24), text_color=colors["text"]).pack(anchor="w", padx=22, pady=(24, 4))
        ctk.CTkLabel(self.sidebar, text="Study planner", font=("Segoe UI", 12), text_color=colors["muted"]).pack(anchor="w", padx=22, pady=(0, 16))
        profile = ctk.CTkFrame(self.sidebar, fg_color=colors["sidebar_active"], corner_radius=20, border_width=1, border_color=colors["sidebar_active_border"])
        profile.pack(fill="x", padx=12, pady=(0, 16))
        ctk.CTkLabel(profile, text=(self.username[:1] or "S").upper(), width=40, height=40, corner_radius=20, fg_color=colors["yellow"], text_color=colors["text"], font=("Segoe UI Semibold", 17)).pack(side="left", padx=(12, 10), pady=12)
        ctk.CTkLabel(profile, text=f"{self.username}\nStudent", font=("Segoe UI", 12), text_color=colors["muted"], justify="left").pack(side="left", pady=12)

        nav = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        nav.pack(fill="x")
        for label, page in NAV_ITEMS:
            self.nav_buttons[page] = self.nav_row(nav, label, page)
        ctk.CTkFrame(self.sidebar, fg_color="transparent").pack(fill="both", expand=True)
        self.nav_row(self.sidebar, "Log out", "logout", command=self.logout).pack_configure(pady=(3, 16))

        self.content = ctk.CTkFrame(self.shell, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew", padx=18, pady=14)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

    def nav_row(self, parent, label, page, command=None):
        colors = self.colors
        row = ctk.CTkFrame(parent, height=42, corner_radius=15, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=3)
        row.pack_propagate(False)
        row.configure(cursor="hand2")
        icon_text = NAV_ICONS.get(page, label[:1].upper())
        icon = ctk.CTkLabel(row, text=icon_text, width=28, height=28, corner_radius=10, fg_color=colors["sidebar_icon"], text_color=colors["deep"], font=("Segoe UI Semibold", 13))
        icon.pack(side="left", padx=(10, 10), pady=7)
        text = ctk.CTkLabel(row, text=label, font=("Segoe UI Semibold", 11), text_color=colors["text"], anchor="w")
        text.pack(side="left", fill="x", expand=True)
        row._icon = icon
        row._text = text
        row._page = page

        def go(_event=None):
            (command or (lambda: self.show_page(page)))()

        def enter(_event=None):
            if self.current_page != page:
                row.configure(fg_color=colors["sidebar_hover"])

        def leave(_event=None):
            if self.current_page != page:
                row.configure(fg_color="transparent")

        for widget in (row, icon, text):
            widget.bind("<Button-1>", go)
            widget.bind("<Enter>", enter)
            widget.bind("<Leave>", leave)
        return row

    def update_nav(self):
        for page, row in self.nav_buttons.items():
            active = page == self.current_page
            row.configure(
                fg_color=self.colors["sidebar_active"] if active else "transparent",
                border_width=1 if active else 0,
                border_color=self.colors["sidebar_active_border"],
            )
            row._icon.configure(
                fg_color=self.colors["sidebar_icon_active"] if active else self.colors["sidebar_icon"],
                text_color=self.colors["white"] if active else self.colors["deep"],
            )
            row._text.configure(text_color=self.colors["deep"] if active else self.colors["text"], font=("Segoe UI Semibold", 12 if active else 11))

    def show_page(self, page, animate=True, force=False):
        if not force and page == self.current_page and self.content and self.content.winfo_children():
            return
        self.current_page = page
        self.update_nav()
        for child in self.content.winfo_children():
            child.destroy()
        builders = {
            "dashboard": self.page_dashboard,
            "add_task": self.page_add_task,
            "progress": self.page_attendance,
            "tasks": self.page_tasks,
            "attendance": self.page_attendance,
            "analytics": self.page_analytics,
            "settings": self.page_settings,
        }
        builders.get(page, self.page_dashboard)()
        if animate:
            self.transition()

    def transition(self):
        mask = ctk.CTkFrame(self.content, fg_color=self.colors["panel"])
        mask.place(relx=0, rely=0, relwidth=1, relheight=1)
        steps = [0.78, 0.54, 0.32, 0.16, 0]

        def step(index=0):
            if index >= len(steps) or not mask.winfo_exists():
                if mask.winfo_exists():
                    mask.destroy()
                return
            mask.place_configure(relx=steps[index])
            self.after(22, lambda: step(index + 1))

        step()

    def page_frame(self, title, subtitle):
        fonts = get_fonts(self.preferences)
        frame = ctk.CTkScrollableFrame(
            self.content,
            fg_color="transparent",
            border_width=0,
            corner_radius=0,
            scrollbar_button_color=self.colors["deep"],
            scrollbar_button_hover_color=self.colors["deep_hover"],
            scrollbar_fg_color=self.colors["panel"],
        )
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        header = ctk.CTkFrame(frame, fg_color=self.colors["surface"], corner_radius=24, border_width=1, border_color=self.colors["surface_border"])
        header.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(header, text=title, font=fonts["title"], text_color=self.colors["text"]).pack(anchor="w", padx=22, pady=(18, 2))
        ctk.CTkLabel(header, text=subtitle, font=fonts["small"], text_color=self.colors["muted"], wraplength=820, justify="left").pack(anchor="w", padx=22, pady=(4, 18))
        return frame

    def page_dashboard(self):
        fonts = get_fonts(self.preferences)
        frame = ctk.CTkScrollableFrame(
            self.content,
            fg_color="transparent",
            border_width=0,
            corner_radius=0,
            scrollbar_button_color=self.colors["deep"],
            scrollbar_button_hover_color=self.colors["deep_hover"],
            scrollbar_fg_color=self.colors["panel"],
        )
        frame.grid(row=0, column=0, sticky="nsew")
        snapshot = load_dashboard_snapshot(self.username)
        game = XPSystem(self.username).game_state()
        summary = snapshot.summary
        attendance_data = snapshot.attendance

        top = ctk.CTkFrame(frame, fg_color="transparent")
        top.pack(fill="x", pady=(0, 12))
        top.grid_columnconfigure(0, weight=1)
        display_name = snapshot.user.get("name") or self.username or "Student"
        ctk.CTkLabel(top, text=f"HELLO, {display_name.split()[0].upper()}!", font=fonts["title"], text_color=self.colors["text"]).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(top, text="Search", font=fonts["small"], text_color=self.colors["muted"]).grid(row=0, column=1, sticky="sw", padx=(16, 10), pady=(0, 4))
        search = ctk.CTkEntry(
            top,
            placeholder_text="Search tasks, subjects, goals",
            width=280,
            height=40,
            corner_radius=16,
            fg_color=self.colors["entry"],
            border_color=self.colors["entry_border"],
            text_color=self.colors["text"],
            placeholder_text_color=self.colors["muted"],
        )
        search.grid(row=1, column=1, sticky="e", padx=(16, 10))

        def run_search(_event=None):
            self.task_filter = search.get().strip()
            self.show_page("tasks")

        search.bind("<Return>", run_search)
        self.button(top, "Search", run_search, height=40).grid(row=1, column=2, sticky="e", padx=(0, 10))
        self.button(top, "Today", lambda: self.show_page("tasks"), height=40).grid(row=1, column=3, sticky="e")

        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=2)
        body.grid_columnconfigure(1, weight=2)
        body.grid_columnconfigure(2, weight=0)
        body.grid_rowconfigure(2, weight=1, minsize=340)
        body.grid_rowconfigure(3, weight=0)

        focus = ctk.CTkFrame(body, fg_color=self.colors["deep"], corner_radius=24, border_width=1, border_color=self.colors["surface_border"])
        focus.grid(row=0, column=0, columnspan=2, sticky="ew", padx=(0, 12), pady=(0, 12))
        focus.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(focus, text="Focus cockpit", font=fonts["body_semibold"], text_color=self.colors["white"]).grid(row=0, column=0, sticky="w", padx=22, pady=(18, 2))
        ctk.CTkLabel(focus, text="Plan today, protect attendance, and keep your streak moving.", font=fonts["section"], text_color=self.colors["white"], wraplength=700, justify="left").grid(row=1, column=0, sticky="w", padx=22, pady=(0, 18))

        grid = ctk.CTkFrame(body, fg_color="transparent")
        grid.grid(row=1, column=0, columnspan=2, sticky="ew", padx=(0, 12), pady=(0, 12))
        for col in range(4):
            grid.grid_columnconfigure(col, weight=1, uniform="stats")
        stats = [
            ("Tasks", summary["total_tasks"], self.colors["primary"]),
            ("Complete", f"{summary['completion_rate']}%", self.colors["green"]),
            ("Streak", f"{game['study_streak']}d", self.colors["yellow"]),
            ("Consistency", f"{game['consistency_score']}%", self.colors["pink"]),
        ]
        for col, (title, value, accent) in enumerate(stats):
            self.stat_card(grid, title, value, accent).grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 7, 0 if col == 3 else 7))

        subjects = self.panel(body, "Linked Subjects")
        subjects.grid(row=2, column=0, sticky="nsew", padx=(0, 8), pady=(0, 12))
        subjects.grid_propagate(False)
        for subject in snapshot.subjects[:4]:
            row = ctk.CTkFrame(subjects, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=9)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text="*", width=34, height=34, corner_radius=12, fg_color=self.colors["deep"], text_color=self.colors["white"], font=fonts["body_semibold"]).grid(row=0, column=0, sticky="w", padx=(0, 10))
            ctk.CTkLabel(row, text=subject, font=fonts["small"], text_color=self.colors["text"], anchor="w").grid(row=0, column=1, sticky="ew", padx=(0, 10))
            links = RESOURCE_MAP.get(subject, RESOURCE_MAP["Science"])
            labels = [label for label, _url in links]
            link_var = ctk.StringVar(value=labels[0])
            resource_menu = ctk.CTkOptionMenu(
                row,
                values=labels,
                variable=link_var,
                width=152,
                height=34,
                corner_radius=12,
                fg_color=self.colors["entry"],
                button_color=self.colors["deep"],
                button_hover_color=self.colors["deep_hover"],
                text_color=self.colors["text"],
                dropdown_fg_color=self.colors["surface"],
                dropdown_text_color=self.colors["text"],
            )
            resource_menu.grid(row=0, column=2, sticky="e", padx=(0, 10))
            self.button(row, "Open", lambda var=link_var, resource_links=dict(links): webbrowser.open(resource_links[var.get()]), height=34).grid(row=0, column=3, sticky="e")

        events = self.panel(body, "Upcoming Events")
        events.grid(row=2, column=1, sticky="nsew", padx=(8, 12), pady=(0, 12))
        events.grid_propagate(False)
        upcoming = snapshot.reminder_tasks[:4] or snapshot.summary["reminders"][:4] or [{"title": "No deadline today", "subject": "Plan freely", "due_date": date.today().isoformat()}]
        for task in upcoming:
            row = ctk.CTkFrame(events, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=9)
            ctk.CTkLabel(row, text=fmt_date(task.get("due_date") or task.get("study_date")).replace(" 2026", ""), width=82, height=56, corner_radius=18, fg_color=self.colors["teal"], text_color=self.colors["white"], font=fonts["small"]).pack(side="left", padx=(0, 12))
            ctk.CTkLabel(row, text=f"{task.get('title', 'Study session')}\n{task.get('subject') or 'General'}", font=fonts["small"], text_color=self.colors["text"], justify="left", anchor="w").pack(side="left", fill="x", expand=True)

        projects = self.panel(body, "My projects")
        projects.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=(0, 12))
        projects_body = ctk.CTkFrame(projects, fg_color="transparent")
        projects_body.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        for column in range(7):
            projects_body.grid_columnconfigure(column, weight=1)
        ctk.CTkLabel(projects_body, text=game["quote"], font=fonts["body_semibold"], text_color=self.colors["deep"], anchor="w").grid(row=0, column=0, columnspan=7, sticky="ew", padx=6, pady=(0, 16))
        for index, item in enumerate(snapshot.attendance["week"]):
            chip = ctk.CTkFrame(projects_body, width=78, height=68, corner_radius=18, fg_color=self.status_color(item["status"]))
            chip.grid(row=1, column=index, sticky="ew", padx=6, pady=(0, 16))
            chip.grid_propagate(False)
            text_color = self.colors["white"] if item["status"] == "present" else self.colors["text"]
            ctk.CTkLabel(chip, text=item["label"], font=("Segoe UI Semibold", 12), text_color=text_color).place(relx=0.5, rely=0.36, anchor="center")
            ctk.CTkLabel(chip, text=item["status"].title(), font=("Segoe UI", 10), text_color=text_color).place(relx=0.5, rely=0.68, anchor="center")
        project_meta = f"Study streak {game['study_streak']} day(s)    Task streak {game['task_streak']}    Consistency {game['consistency_score']}%"
        ctk.CTkLabel(projects_body, text=project_meta, font=fonts["small"], text_color=self.colors["muted"], anchor="w").grid(row=2, column=0, columnspan=7, sticky="ew", padx=6)

        side = ctk.CTkFrame(body, fg_color="transparent")
        side.grid(row=0, column=2, rowspan=5, sticky="nsew")
        side.configure(width=286)
        side.grid_propagate(False)
        level = self.panel(side, game["rank_title"])
        level.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(level, text=f"Level {game['level']}", font=("Segoe UI Semibold", 26), text_color=self.colors["deep"]).pack(anchor="w", padx=18, pady=(2, 2))
        ctk.CTkLabel(level, text=f"{game['current_level_xp']} / {game['next_level_xp']} XP", font=("Segoe UI", 12), text_color=self.colors["muted"]).pack(anchor="w", padx=18)
        xp_bar = ctk.CTkProgressBar(level, height=14, progress_color=self.colors["pink"], fg_color=self.colors["secondary"])
        xp_bar.pack(fill="x", padx=18, pady=(10, 18))
        xp_bar.set(game["level_progress"])

        self.circular_meter(side, "Attendance", snapshot.attendance["percentage"], self.colors["pink"], diameter=112).pack(fill="x", pady=(0, 12))
        meters = ctk.CTkFrame(side, fg_color="transparent")
        meters.pack(fill="x", pady=(0, 12))
        meters.grid_columnconfigure((0, 1), weight=1)
        self.circular_meter(meters, "Homework", summary["completion_rate"], self.colors["teal"], diameter=92).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        rating_value = min(100, max(0, 100 - (summary.get("overdue_tasks", 0) * 10)))
        self.circular_meter(meters, "Rating", rating_value, self.colors["yellow"], diameter=92).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        attendance = ctk.CTkFrame(side, fg_color=self.colors["surface"], corner_radius=22, border_width=1, border_color=self.colors["surface_border"])
        attendance.pack(fill="x", pady=(0, 12))
        leave_enabled = attendance_data.get("leave_enabled", True)
        if attendance_data["today_is_leave"]:
            status_text = f"Today is your weekly leave day ({attendance_data['leave_day_name']})."
            button_text = "Leave day"
            button_state = "disabled"
            button_color = self.colors["secondary"]
        elif attendance_data["today_status"] == "present":
            status_text = "Present marked for today."
            button_text = "Marked present"
            button_state = "disabled"
            button_color = self.colors["green"]
        else:
            status_text = "Mark present today to keep attendance complete."
            button_text = "Mark present today"
            button_state = "normal"
            button_color = self.colors["deep"]
        hint_text = (
            f"Weekly leave: {attendance_data['leave_day_name']}. Holiday locks if attendance falls below 75%."
            if leave_enabled
            else "Weekly holiday is locked until attendance reaches 75% again."
        )
        ctk.CTkLabel(attendance, text=status_text, font=fonts["body_semibold"], text_color=self.colors["text"], wraplength=230, justify="left").pack(anchor="w", padx=18, pady=(16, 8))
        ctk.CTkLabel(attendance, text=hint_text, font=fonts["small"], text_color=self.colors["muted"], wraplength=230, justify="left").pack(anchor="w", padx=18, pady=(0, 10))
        mark_btn = ctk.CTkButton(attendance, text=button_text, height=38, corner_radius=16, fg_color=button_color, hover_color=self.colors["deep_hover"], text_color=self.colors["white"], state=button_state, font=fonts["body_semibold"], command=lambda: self.mark_present_and_refresh("dashboard"))
        mark_btn.pack(fill="x", padx=18, pady=(0, 14))
        leave_var = ctk.StringVar(value=attendance_data["leave_day_name"])
        leave_menu = ctk.CTkOptionMenu(
            attendance,
            values=WEEKDAY_NAMES,
            variable=leave_var,
            height=40,
            corner_radius=16,
            fg_color=self.colors["entry"],
            button_color=self.colors["deep"],
            button_hover_color=self.colors["deep_hover"],
            text_color=self.colors["text"],
            dropdown_fg_color=self.colors["surface"],
            dropdown_text_color=self.colors["text"],
            state="normal" if leave_enabled else "disabled",
            command=lambda day: self.change_leave_from_dashboard(day),
        )
        leave_menu.pack(fill="x", padx=18, pady=(0, 16))
        self.button(side, "Open task board", lambda: self.show_page("tasks"), variant="secondary", height=40).pack(fill="x")

    def circular_meter(self, parent, title, value, accent, diameter=100):
        fonts = get_fonts(self.preferences)
        value = max(0, min(100, int(value or 0)))
        card_height = max(150, diameter + 58)
        card = ctk.CTkFrame(parent, height=card_height, fg_color=self.colors["surface"], corner_radius=20, border_width=1, border_color=self.colors["surface_border"])
        card.pack_propagate(False)
        ctk.CTkLabel(card, text=title, font=fonts["body_semibold"], text_color=self.colors["text"]).pack(anchor="w", padx=16, pady=(14, 4))
        box = ctk.CTkFrame(card, width=diameter, height=diameter, fg_color="transparent")
        box.pack(anchor="center", pady=(0, 12))
        box.pack_propagate(False)
        canvas = Canvas(box, width=diameter, height=diameter, highlightthickness=0, bd=0, bg=self.colors["surface"])
        canvas.place(relx=0.5, rely=0.5, anchor="center")
        pad = max(10, diameter // 8)
        width = max(8, diameter // 11)
        canvas.create_oval(pad, pad, diameter - pad, diameter - pad, outline=self.colors["surface_border"], width=width)
        canvas.create_arc(pad, pad, diameter - pad, diameter - pad, start=90, extent=-(value * 3.6), outline=accent, width=width, style="arc")
        ctk.CTkLabel(card, text=f"{value}%", font=fonts["section"], text_color=self.colors["text"]).place(in_=box, relx=0.5, rely=0.5, anchor="center")
        return card

    def pick_date_for_entry(self, entry):
        colors = self.colors
        fonts = get_fonts(self.preferences)
        modal = ctk.CTkToplevel(self)
        modal.title("Choose date")
        modal.geometry("420x460")
        modal.resizable(False, False)
        modal.transient(self)
        modal.grab_set()
        modal.configure(fg_color=colors["bg"])

        frame = ctk.CTkFrame(modal, fg_color=colors["surface"], border_color=colors["surface_border"], border_width=1, corner_radius=20)
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        current = datetime.today().replace(day=1)
        raw = entry.get().strip()
        if raw:
            for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
                try:
                    current = datetime.strptime(raw, fmt).replace(day=1)
                    break
                except ValueError:
                    pass

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 8))
        month_label = ctk.CTkLabel(header, text="", font=fonts["body_semibold"], text_color=colors["text"])
        month_label.pack(side="left")
        nav = ctk.CTkFrame(header, fg_color="transparent")
        nav.pack(side="right")
        grid_frame = ctk.CTkFrame(frame, fg_color="transparent")
        grid_frame.pack(fill="both", expand=True, padx=16, pady=(4, 8))

        def select_day(day):
            entry.delete(0, "end")
            entry.insert(0, datetime(current.year, current.month, day).strftime("%d-%m-%Y"))
            modal.destroy()

        def render():
            nonlocal current
            for child in grid_frame.winfo_children():
                child.destroy()
            month_label.configure(text=current.strftime("%B %Y"))
            for col, name in enumerate(["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]):
                ctk.CTkLabel(grid_frame, text=name, text_color=colors["muted"], font=fonts["small"]).grid(row=0, column=col, padx=4, pady=(0, 8))
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
                        fg_color=colors["tile"],
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

    def tasks_open_calendar_month(self):
        colors = self.colors
        fonts = get_fonts(self.preferences)
        modal = ctk.CTkToplevel(self)
        modal.title("Calendar")
        modal.geometry("980x720")
        modal.configure(fg_color=colors["bg"])
        modal.grab_set()

        current = datetime.today().replace(day=1)
        panel = ctk.CTkFrame(modal, corner_radius=24, border_width=1, fg_color=colors["surface"], border_color=colors["surface_border"])
        panel.pack(fill="both", expand=True, padx=20, pady=20)

        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(18, 12))
        month_label = ctk.CTkLabel(header, text="", font=fonts["section"], text_color=colors["text"])
        month_label.pack(side="left")
        nav = ctk.CTkFrame(header, fg_color="transparent")
        nav.pack(side="right")
        grid = ctk.CTkFrame(panel, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=20, pady=(0, 18))

        def tasks_for_day(day):
            iso_day = datetime(current.year, current.month, day).strftime("%Y-%m-%d")
            return [
                task
                for task in database.get_tasks_for_username(self.username)
                if task.get("study_date") == iso_day or task.get("due_date") == iso_day
            ]

        def render_cal():
            for child in grid.winfo_children():
                child.destroy()
            month_label.configure(text=current.strftime("%B %Y"))
            for col, name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
                ctk.CTkLabel(grid, text=name, font=fonts["body_semibold"], text_color=colors["muted"]).grid(row=0, column=col, sticky="ew", padx=4, pady=(0, 8))
                grid.grid_columnconfigure(col, weight=1, uniform="calendar")
            for row_index, week in enumerate(calendar.monthcalendar(current.year, current.month), start=1):
                grid.grid_rowconfigure(row_index, weight=1, uniform="calendar")
                for col_index, day in enumerate(week):
                    cell = ctk.CTkFrame(grid, corner_radius=12, border_width=1, fg_color=colors["tile"], border_color=colors["surface_border"])
                    cell.grid(row=row_index, column=col_index, sticky="nsew", padx=4, pady=4)
                    if day == 0:
                        continue
                    ctk.CTkLabel(cell, text=str(day), font=fonts["body_semibold"], text_color=colors["text"]).pack(anchor="nw", padx=8, pady=(6, 2))
                    for task in tasks_for_day(day)[:3]:
                        prefix = "D" if task.get("due_date") == datetime(current.year, current.month, day).strftime("%Y-%m-%d") else "S"
                        text = f"{prefix}: {task.get('priority', 'Medium')[0]} - {task['title']}"
                        ctk.CTkLabel(cell, text=text, font=fonts["small"], text_color=colors["muted"], wraplength=110, justify="left").pack(anchor="w", padx=8, pady=(0, 2))

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
            render_cal()

        ctk.CTkButton(nav, text="<", width=42, height=36, corner_radius=12, fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"], command=lambda: shift(-1)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(nav, text=">", width=42, height=36, corner_radius=12, fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"], command=lambda: shift(1)).pack(side="left")
        ctk.CTkButton(panel, text="Close", height=40, corner_radius=14, fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"], command=modal.destroy).pack(anchor="e", padx=20, pady=(0, 18))
        render_cal()

    def tasks_launch_ai_quiz_window(self):
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "view_tasks.py")
        try:
            subprocess.Popen([sys.executable, script, self.username], close_fds=os.name != "nt")
        except OSError:
            self.show_error("AI Quiz", "Could not open the Tasks window.")

    def parse_task_quiz(self, text):
        raw = (text or "").strip()
        if not raw:
            return []
        if raw.startswith("{"):
            try:
                payload = json.loads(raw)
            except (TypeError, ValueError):
                payload = {}
            items = []
            for item in payload.get("quiz", []):
                question = (item.get("question") or "").strip()
                answer = (item.get("answer") or "").strip()
                if question and answer:
                    items.append(
                        {
                            "question": question,
                            "answer": answer,
                            "type": (item.get("type") or "short_answer").strip().lower(),
                            "options": [option.strip() for option in item.get("options") or [] if option and option.strip()],
                            "helper": (item.get("helper") or "").strip(),
                        }
                    )
            if items:
                return items

        items = []
        for block in raw.split("\n\n"):
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            answer = next((line.replace("Answer:", "", 1).strip() for line in lines[1:] if line.startswith("Answer:")), "")
            if lines and answer:
                items.append({"question": lines[0], "answer": answer, "type": "short_answer", "options": [], "helper": ""})
        return items

    def task_quiz_needs_refresh(self, text):
        raw = (text or "").strip()
        if not raw or not raw.startswith("{"):
            return True
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return True
        return int(payload.get("version") or 0) < ai_review.QUIZ_FORMAT_VERSION or len(payload.get("quiz") or []) < 8

    def ensure_task_quiz(self, task_id, task):
        if not self.task_quiz_needs_refresh(task.get("quiz")):
            return task, "Saved AI quiz"
        flashcards, quiz, source = ai_review.generate_review_pack(task)
        database.save_task_review_materials(task_id, flashcards, quiz)
        refreshed = database.get_task_by_id(task_id) or task
        source_label = "OpenAI AI quiz" if source == "openai" else "Local AI quiz"
        return refreshed, source_label

    def show_completion_quiz(self, task_id, task, source_label="AI quiz"):
        task = task or database.get_task_by_id(task_id)
        if not task:
            self.show_error("AI Quiz", "Could not load this task.")
            return

        task, source_label = self.ensure_task_quiz(task_id, task)
        quiz_items = self.parse_task_quiz(task.get("quiz"))
        if not quiz_items:
            self.show_error("AI Quiz", "Could not prepare a quiz for this task.")
            return

        colors = self.colors
        fonts = get_fonts(self.preferences)
        modal = ctk.CTkToplevel(self)
        modal.title("Complete AI Quiz")
        modal.geometry("960x720")
        modal.configure(fg_color=colors["bg"])
        modal.grab_set()

        panel = ctk.CTkFrame(modal, corner_radius=24, border_width=1, fg_color=colors["surface"], border_color=colors["surface_border"])
        panel.pack(fill="both", expand=True, padx=20, pady=20)
        ctk.CTkLabel(panel, text=f"AI Quiz: {task.get('title') or 'Task'}", font=fonts["section"], text_color=colors["text"]).pack(anchor="w", padx=22, pady=(18, 6))
        ctk.CTkLabel(panel, text=f"{source_label}. Reveal every answer before the task can be marked completed.", font=fonts["small"], text_color=colors["muted"]).pack(anchor="w", padx=22, pady=(0, 12))

        progress = ctk.CTkLabel(panel, text=f"Answered 0 of {len(quiz_items)}", font=fonts["body_semibold"], text_color=colors["primary"])
        progress.pack(anchor="w", padx=22, pady=(0, 10))

        quiz_body = ctk.CTkScrollableFrame(panel, fg_color=colors["tile"], corner_radius=18)
        quiz_body.pack(fill="both", expand=True, padx=22, pady=(0, 16))
        answered = set()

        actions = ctk.CTkFrame(panel, fg_color="transparent")
        actions.pack(fill="x", padx=22, pady=(0, 18))
        complete_btn = ctk.CTkButton(actions, text="Mark Completed", height=42, corner_radius=14, fg_color=colors["primary"], hover_color=colors["primary_hover"], text_color=colors["white"], state="disabled")
        complete_btn.pack(side="left")
        ctk.CTkButton(actions, text="Cancel", height=42, corner_radius=14, fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"], command=modal.destroy).pack(side="right")

        def update_progress(index):
            answered.add(index)
            progress.configure(text=f"Answered {len(answered)} of {len(quiz_items)}")
            if len(answered) >= len(quiz_items):
                complete_btn.configure(state="normal")

        for index, item in enumerate(quiz_items, start=1):
            card = ctk.CTkFrame(quiz_body, corner_radius=18, border_width=1, fg_color=colors["surface"], border_color=colors["surface_border"])
            card.pack(fill="x", padx=10, pady=10)
            ctk.CTkLabel(card, text=f"Question {index}", font=fonts["body_semibold"], text_color=colors["primary"]).pack(anchor="w", padx=16, pady=(14, 6))
            ctk.CTkLabel(card, text=item["question"], font=fonts["body_semibold"], text_color=colors["text"], wraplength=760, justify="left").pack(anchor="w", padx=16, pady=(0, 10))
            for option in item.get("options") or []:
                ctk.CTkLabel(card, text=f"- {option}", font=fonts["small"], text_color=colors["text"], wraplength=740, justify="left").pack(anchor="w", padx=24, pady=(0, 4))
            answer = ctk.CTkLabel(card, text=f"Answer: {item['answer']}", font=fonts["small"], text_color=colors["text"], wraplength=760, justify="left")

            def reveal_answer(idx=index, answer_label=answer, card_widget=card, button=None):
                answer_label.pack(anchor="w", padx=16, pady=(0, 14))
                update_progress(idx)
                if button is not None:
                    button.configure(text="Answered", state="disabled")

            button = ctk.CTkButton(card, text="Reveal Answer", width=140, height=36, corner_radius=12, fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"])
            button.configure(command=lambda idx=index, label=answer, btn=button: reveal_answer(idx, label, card, btn))
            button.pack(anchor="w", padx=16, pady=(0, 14))

        def finish_completion():
            if not database.mark_task_status(task_id, "completed"):
                self.show_error("Completion Failed", "Could not mark this task completed. Please try again.")
                return
            XPSystem(self.username).award_task_completion(task_id)
            modal.destroy()
            self.show_page("tasks", animate=False, force=True)
            self.show_info("Completed", "Task marked completed after the AI quiz.")

        complete_btn.configure(command=finish_completion)

    def page_add_task(self):
        frame = self.page_frame("Add Task", "Attach notes, generate a timetable, and save the task.")
        fonts = get_fonts(self.preferences)
        box = ctk.CTkFrame(frame, fg_color=self.colors["surface"], corner_radius=22, border_width=1, border_color=self.colors["surface_border"])
        box.pack(fill="both", expand=True, pady=(0, 12))
        ctk.CTkLabel(
            box,
            text="Add Task & timetable",
            font=fonts["section"],
            text_color=self.colors["text"],
        ).pack(anchor="w", padx=22, pady=(20, 8))
        ctk.CTkLabel(
            box,
            text="Attach notes or paste notes text, generate the study timetable, then save the task with its plan.",
            font=fonts["small"],
            text_color=self.colors["muted"],
            wraplength=560,
            justify="left",
        ).pack(anchor="w", padx=22, pady=(0, 18))

        workspace = ctk.CTkFrame(box, fg_color="transparent")
        workspace.pack(fill="both", expand=True, padx=22, pady=(0, 18))
        workspace.grid_columnconfigure(0, weight=2, minsize=340)
        workspace.grid_columnconfigure(1, weight=3, minsize=420)
        workspace.grid_rowconfigure(0, weight=1)

        quick = ctk.CTkFrame(
            workspace,
            fg_color=self.colors["tile"],
            corner_radius=18,
            border_width=1,
            border_color=self.colors["surface_border"],
        )
        quick.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        quick.grid_columnconfigure((0, 1), weight=1)
        notes_path_var = ctk.StringVar(value="")
        current_plan = {"value": None}

        def invalidate_timetable():
            current_plan["value"] = None
            for item in timetable_tree.get_children():
                timetable_tree.delete(item)
            timetable_summary.configure(
                text="Inputs changed. Click Generate AI Timetable to create the schedule.",
                text_color=self.colors["muted"],
            )

        timetable_panel = ctk.CTkFrame(workspace, fg_color=self.colors["tile"], corner_radius=18, border_width=1, border_color=self.colors["surface_border"])
        timetable_panel.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        timetable_panel.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(timetable_panel, text="Suggested Study Timetable", font=fonts["section"], text_color=self.colors["text"]).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 4))
        timetable_summary = ctk.CTkLabel(
            timetable_panel,
            text="Attach notes or paste notes text, choose dates, then generate the timetable.",
            font=fonts["small"],
            text_color=self.colors["muted"],
            wraplength=620,
            justify="left",
            anchor="w",
        )
        timetable_summary.grid(row=1, column=0, sticky="new", padx=16, pady=(0, 8))

        table_holder = ctk.CTkFrame(timetable_panel, fg_color="transparent")
        table_holder.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 14))
        timetable_panel.grid_rowconfigure(2, weight=1)
        style_treeview(ttk.Style(), "AddTask.Timetable.Treeview", self.colors, rowheight=30)
        timetable_tree = ttk.Treeview(
            table_holder,
            columns=("day", "date", "unit", "task", "pages", "hours"),
            show="headings",
            style="AddTask.Timetable.Treeview",
            height=13,
        )
        for col, label, width, stretch in [
            ("day", "Day", 46, False),
            ("date", "Date", 96, False),
            ("unit", "Unit", 72, False),
            ("task", "Task", 170, True),
            ("pages", "Pages", 90, False),
            ("hours", "Hours", 62, False),
        ]:
            timetable_tree.heading(col, text=label)
            timetable_tree.column(col, width=width, anchor="w", stretch=stretch)
        timetable_scroll = ttk.Scrollbar(table_holder, orient="vertical", command=timetable_tree.yview)
        timetable_tree.configure(yscrollcommand=timetable_scroll.set)
        timetable_tree.pack(side="left", fill="both", expand=True)
        timetable_scroll.pack(side="right", fill="y")

        def labeled_entry(parent, label, placeholder, row, column, padx):
            self.form_label(parent, label, fonts).grid(row=row, column=column, sticky="w", padx=padx, pady=(0, 6))
            entry = self.entry(parent, placeholder)
            entry.grid(row=row + 1, column=column, sticky="ew", padx=padx, pady=(0, 12))
            entry.bind("<KeyRelease>", lambda _event: invalidate_timetable(), add="+")
            return entry

        def labeled_date_entry(label, row, column, padx):
            self.form_label(quick, label, fonts).grid(row=row, column=column, sticky="w", padx=padx, pady=(0, 6))
            date_row = ctk.CTkFrame(quick, fg_color="transparent")
            date_row.grid(row=row + 1, column=column, sticky="ew", padx=padx, pady=(0, 12))
            date_row.grid_columnconfigure(0, weight=1)
            entry = self.entry(date_row, "DD-MM-YYYY")
            entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
            entry.bind("<KeyRelease>", lambda _event: invalidate_timetable(), add="+")

            def choose_date():
                self.pick_date_for_entry(entry)
                invalidate_timetable()

            self.button(date_row, "Choose", choose_date, variant="secondary", height=46).grid(row=0, column=1)
            return entry

        ctk.CTkLabel(quick, text="Task Inputs", font=fonts["body_semibold"], text_color=self.colors["text"]).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 12))
        title_entry = labeled_entry(quick, "Task title", "Example: Revise chapter 4", 1, 0, (16, 16))
        study_date_entry = labeled_date_entry("Study date", 3, 0, (16, 8))
        due_date_entry = labeled_date_entry("Due date", 3, 1, (8, 16))
        computed_hours = {"value": round(self.preferences.get("default_study_duration", 50) / 60, 2)}
        priority_var = ctk.StringVar(value="Medium")
        self.form_label(quick, "Priority", fonts).grid(row=5, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 6))
        ctk.CTkOptionMenu(quick, values=["High", "Medium", "Low"], variable=priority_var, height=46, corner_radius=16, fg_color=self.colors["entry"], button_color=self.colors["primary"], text_color=self.colors["text"]).grid(row=6, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 12))

        self.form_label(quick, "Attached notes document", fonts).grid(row=7, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 6))
        attach_row = ctk.CTkFrame(quick, fg_color="transparent")
        attach_row.grid(row=8, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 12))
        attach_row.grid_columnconfigure(0, weight=1)
        attachment_label = ctk.CTkLabel(
            attach_row,
            text="No document attached",
            height=42,
            corner_radius=14,
            fg_color=self.colors["entry"],
            text_color=self.colors["muted"],
            anchor="w",
            padx=14,
        )
        attachment_label.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        def attach_notes_document():
            path = filedialog.askopenfilename(
                title="Attach notes document",
                parent=self,
                filetypes=[
                    ("Documents", "*.pdf *.docx *.txt *.md *.csv"),
                    ("PDF", "*.pdf"),
                    ("Word", "*.docx"),
                    ("Text", "*.txt *.md *.csv"),
                    ("All files", "*.*"),
                ],
            )
            if not path:
                return
            notes_path_var.set(path)
            words = _document_word_count(path)
            filename = os.path.basename(path)
            meta = f"{filename} ({words} words)" if words else filename
            attachment_label.configure(text=meta, text_color=self.colors["text"])
            invalidate_timetable()

        def clear_notes_document():
            notes_path_var.set("")
            attachment_label.configure(text="No document attached", text_color=self.colors["muted"])
            invalidate_timetable()

        self.button(attach_row, "Attach", attach_notes_document, variant="secondary", height=42).grid(row=0, column=1, padx=(0, 8))
        self.button(attach_row, "Remove", clear_notes_document, variant="danger", height=42).grid(row=0, column=2, padx=(0, 8))

        self.form_label(quick, "Notes text", fonts).grid(row=9, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 6))
        notes_box = ctk.CTkTextbox(quick, height=96, corner_radius=16, border_width=1, fg_color=self.colors["entry"], border_color=self.colors["entry_border"], text_color=self.colors["text"])
        notes_box.grid(row=10, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 10))
        notes_box.bind("<KeyRelease>", lambda _event: invalidate_timetable(), add="+")
        self.button(quick, "Generate AI Timetable", lambda: generate_timetable_from_notes(), height=44).grid(row=11, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 10))
        status = ctk.CTkLabel(quick, text="", font=fonts["small"], text_color=self.colors["danger"])
        status.grid(row=12, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 14))

        def clear_timetable():
            for item in timetable_tree.get_children():
                timetable_tree.delete(item)

        def apply_timetable_plan(plan):
            current_plan["value"] = dict(plan)
            clear_timetable()
            timetable_summary.configure(text=plan.get("summary", ""), text_color=self.colors["primary"])
            for session in plan.get("sessions") or []:
                timetable_tree.insert(
                    "",
                    "end",
                    values=(
                        session.get("day_index"),
                        session.get("date"),
                        session.get("unit"),
                        session.get("task"),
                        session.get("pages"),
                        f"{float(session.get('hours', 0)):.1f}",
                    ),
                )
            total_hours = round(sum(float(session.get("hours", 0)) for session in plan.get("sessions") or []), 2)
            if total_hours:
                computed_hours["value"] = total_hours
            status.configure(text=f"Generated {len(plan.get('sessions') or [])} timetable session(s).", text_color=self.colors["primary"])

        def generate_timetable_from_notes():
            title = title_entry.get().strip() or "Study"
            subject = "General"
            study_date = _task_date_to_storage(study_date_entry.get())
            due_date = _task_date_to_storage(due_date_entry.get())
            if not study_date or not due_date:
                status.configure(text="Set valid study and due dates before generating.", text_color=self.colors["danger"])
                return
            start = datetime.strptime(study_date, "%Y-%m-%d").date()
            end = datetime.strptime(due_date, "%Y-%m-%d").date()
            path = notes_path_var.get().strip()
            notes_text = notes_box.get("1.0", "end").strip()
            if path and os.path.isfile(path):
                plan = study_timetable.generate_timetable(path, start, end, title, subject)
            elif notes_text:
                plan = study_timetable.generate_timetable_from_text(notes_text, start, end, title, subject)
            else:
                status.configure(text="Attach notes or paste notes text before generating.", text_color=self.colors["danger"])
                return
            if plan.get("error"):
                status.configure(text=plan["error"], text_color=self.colors["danger"])
                return
            apply_timetable_plan(plan)

        def save_quick_task():
            title = title_entry.get().strip()
            if not title:
                status.configure(text="Title is required.", text_color=self.colors["danger"])
                return
            study_date = _task_date_to_storage(study_date_entry.get())
            due_date = _task_date_to_storage(due_date_entry.get())
            if study_date_entry.get().strip() and not study_date:
                status.configure(text="Study date must be DD-MM-YYYY.", text_color=self.colors["danger"])
                return
            if due_date_entry.get().strip() and not due_date:
                status.configure(text="Due date must be DD-MM-YYYY.", text_color=self.colors["danger"])
                return
            if not current_plan["value"]:
                status.configure(text="Click Generate AI Timetable before saving the task.", text_color=self.colors["danger"])
                return
            hours = float(computed_hours["value"] or 1)
            ok = database.create_task_for_username(
                self.username,
                title,
                subject="General",
                due_date=due_date,
                study_date=study_date,
                study_hours=hours,
                notes=notes_box.get("1.0", "end").strip(),
                notes_path=notes_path_var.get().strip() or None,
                study_plan=study_timetable.plan_to_json(current_plan["value"]) if current_plan["value"] else "",
                priority=priority_var.get(),
            )
            if not ok:
                status.configure(text="Could not save the task. Check the entered values.", text_color=self.colors["danger"])
                return
            self.task_filter = title
            self.show_page("tasks", animate=False)

        def launch_add():
            script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "add_task.py")
            try:
                subprocess.Popen([sys.executable, script, self.username], close_fds=os.name != "nt")
            except OSError:
                self.show_error("Task Editor", "Could not launch the full task editor.")

        actions = ctk.CTkFrame(box, fg_color="transparent")
        actions.pack(fill="x", padx=22, pady=(0, 22))
        actions.grid_columnconfigure((0, 1), weight=1)
        self.button(actions, "Save Task", save_quick_task, height=44).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.button(actions, "Open Full Editor", launch_add, variant="secondary", height=44).grid(row=0, column=1, sticky="ew", padx=(8, 0))

    def page_tasks(self):
        frame = self.page_frame("Tasks", "Select a task, then edit details, timetable, or status.")
        fonts = get_fonts(self.preferences)

        hint = ctk.CTkFrame(frame, fg_color=self.colors["surface"], corner_radius=18, border_width=1, border_color=self.colors["surface_border"])
        hint.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            hint,
            text="New tasks and timetables are created from Add Task. Select a task here to edit, review, or complete it.",
            font=fonts["small"],
            text_color=self.colors["muted"],
            wraplength=720,
            justify="left",
        ).pack(anchor="w", padx=18, pady=14)

        table_panel = self.panel(frame, "Task Board")
        table_panel.pack(fill="both", expand=True)
        filter_row = ctk.CTkFrame(table_panel, fg_color="transparent")
        filter_row.pack(fill="x", padx=18, pady=(0, 8))
        filter_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(filter_row, text="Task filter", font=fonts["small"], text_color=self.colors["muted"]).grid(row=0, column=0, sticky="w", pady=(0, 6))
        filter_entry = self.entry(filter_row, "Filter by title, priority, or status")
        filter_entry.insert(0, self.task_filter)
        filter_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8))

        def apply_filter(_event=None):
            self.task_filter = filter_entry.get().strip()
            self.show_page("tasks", animate=False, force=True)

        def clear_filter():
            self.task_filter = ""
            self.show_page("tasks", animate=False, force=True)

        filter_entry.bind("<Return>", apply_filter)
        self.button(filter_row, "Apply", apply_filter, height=42).grid(row=1, column=1, padx=(0, 8))
        self.button(filter_row, "Clear", clear_filter, variant="secondary", height=42).grid(row=1, column=2)

        def note_preview(task):
            n = (task.get("notes") or "").strip().replace("\n", " ")
            if len(n) > 40:
                return n[:37] + "..."
            return n or "-"

        toolbar = ctk.CTkFrame(table_panel, fg_color="transparent")
        toolbar.pack(fill="x", padx=18, pady=(0, 8))

        tree_holder = ctk.CTkFrame(table_panel, fg_color="transparent")
        tree_holder.pack(fill="both", expand=True, padx=18, pady=(0, 12))

        tree = ttk.Treeview(
            tree_holder,
            columns=("title", "start", "due", "notes", "priority", "status"),
            show="headings",
            height=11,
        )
        for col, label, width in [
            ("title", "Title", 240),
            ("start", "Start", 100),
            ("due", "Due", 100),
            ("notes", "Notes", 190),
            ("priority", "Priority", 80),
            ("status", "Status", 90),
        ]:
            tree.heading(col, text=label)
            tree.column(col, width=width, anchor="w")
        scroll = ttk.Scrollbar(tree_holder, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        tasks = database.get_tasks_for_username(self.username)
        query = (self.task_filter or "").lower()
        if query:
            tasks = [
                task
                for task in tasks
                if query in " ".join(
                    str(task.get(field) or "")
                    for field in ("title", "priority", "status", "notes")
                ).lower()
            ]
        for task in tasks:
            tree.insert(
                "",
                "end",
                iid=str(task["id"]),
                values=(
                    task["title"],
                    fmt_date(task.get("study_date")),
                    fmt_date(task.get("due_date")),
                    note_preview(task),
                    task.get("priority") or "Medium",
                    (task.get("status") or "pending").title(),
                ),
            )

        def selected_id():
            selection = tree.selection() or ((tree.focus(),) if tree.focus() else ())
            task_id = selection[0] if selection else None
            if not task_id:
                self.show_warning("Tasks", "Select a task in the board first.")
                return None
            try:
                return int(task_id)
            except (TypeError, ValueError):
                self.show_warning("Tasks", "Select a valid task row first.")
                return None

        def select_tree_row(event):
            row_id = tree.identify_row(event.y)
            if row_id:
                tree.selection_set(row_id)
                tree.focus(row_id)

        def tasks_edit_selected():
            task_id = selected_id()
            if task_id is None:
                return
            task = database.get_task_by_id(task_id)
            if not task:
                return
            colors = self.colors
            modal = ctk.CTkToplevel(self)
            modal.title("Edit Task")
            modal.geometry("640x560")
            modal.configure(fg_color=colors["bg"])
            modal.grab_set()
            panel = ctk.CTkFrame(modal, corner_radius=22, border_width=1, fg_color=colors["surface"], border_color=colors["surface_border"])
            panel.pack(fill="both", expand=True, padx=18, pady=18)

            ctk.CTkLabel(panel, text="Edit Task", font=fonts["section"], text_color=colors["text"]).pack(anchor="w", padx=18, pady=(16, 8))
            body = ctk.CTkScrollableFrame(panel, fg_color="transparent")
            body.pack(fill="both", expand=True, padx=18, pady=(0, 12))

            self.form_label(body, "Task title", fonts).pack(anchor="w", pady=(0, 6))
            te = self.entry(body, "Title")
            te.insert(0, task.get("title") or "")
            te.pack(fill="x", pady=(0, 10))

            row_sd = ctk.CTkFrame(body, fg_color="transparent")
            row_sd.pack(fill="x", pady=(0, 10))
            row_sd.grid_columnconfigure(0, weight=1)
            self.form_label(row_sd, "Study date", fonts).grid(row=0, column=0, sticky="w", pady=(0, 6))
            sde = self.entry(row_sd, "Start DD-MM-YYYY")
            sde.insert(0, _task_date_parse_display(task.get("study_date")) or "")
            sde.grid(row=1, column=0, sticky="ew", padx=(0, 8))
            ctk.CTkButton(row_sd, text="Choose", width=80, height=46, corner_radius=14, fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"], command=lambda: self.pick_date_for_entry(sde)).grid(row=1, column=1)

            row_dd = ctk.CTkFrame(body, fg_color="transparent")
            row_dd.pack(fill="x", pady=(0, 10))
            row_dd.grid_columnconfigure(0, weight=1)
            self.form_label(row_dd, "Due date", fonts).grid(row=0, column=0, sticky="w", pady=(0, 6))
            dde = self.entry(row_dd, "Due DD-MM-YYYY")
            dde.insert(0, _task_date_parse_display(task.get("due_date")) or "")
            dde.grid(row=1, column=0, sticky="ew", padx=(0, 8))
            ctk.CTkButton(row_dd, text="Choose", width=80, height=46, corner_radius=14, fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"], command=lambda: self.pick_date_for_entry(dde)).grid(row=1, column=1)

            self.form_label(body, "Study hours", fonts).pack(anchor="w", pady=(0, 6))
            he = self.entry(body, "Study hours")
            he.insert(0, str(task.get("study_hours") or 1))
            he.pack(fill="x", pady=(0, 10))
            pvar = ctk.StringVar(value=task.get("priority") or "Medium")
            ctk.CTkOptionMenu(body, values=["High", "Medium", "Low"], variable=pvar, height=42, fg_color=colors["entry"], button_color=colors["primary"], text_color=colors["text"]).pack(fill="x", pady=(0, 10))
            stvar = ctk.StringVar(value=task.get("status") or "pending")
            ctk.CTkOptionMenu(body, values=["pending"], variable=stvar, height=42, fg_color=colors["entry"], button_color=colors["primary"], text_color=colors["text"]).pack(fill="x", pady=(0, 10))

            ctk.CTkLabel(body, text="Notes", font=fonts["small"], text_color=colors["muted"]).pack(anchor="w")
            nb = ctk.CTkTextbox(body, height=100, fg_color=colors["entry"], border_color=colors["entry_border"], text_color=colors["text"])
            nb.pack(fill="x", pady=(4, 10))
            nb.insert("1.0", task.get("notes") or "")

            def save_edit():
                t = te.get().strip()
                if not t:
                    self.show_warning("Task", "Title is required.")
                    return
                if dde.get().strip() and not _task_date_to_storage(dde.get()):
                    self.show_warning("Task", "Invalid due date.")
                    return
                if sde.get().strip() and not _task_date_to_storage(sde.get()):
                    self.show_warning("Task", "Invalid start date.")
                    return
                try:
                    hrs = float(he.get().strip() or 1)
                except ValueError:
                    self.show_warning("Task", "Study hours must be numeric.")
                    return
                saved = database.update_task(
                    task_id,
                    title=t,
                    subject=task.get("subject") or "General",
                    due_date=_task_date_to_storage(dde.get()),
                    study_date=_task_date_to_storage(sde.get()),
                    study_hours=hrs,
                    status=stvar.get(),
                    notes=nb.get("1.0", "end").strip(),
                    notes_path=task.get("notes_path"),
                    study_plan=(task.get("study_plan") or "").strip(),
                    priority=pvar.get(),
                    reminder_lead_minutes=int(task.get("reminder_lead_minutes") or 30),
                )
                if not saved:
                    self.show_error("Save Failed", "Could not update this task. Check the values and try again.")
                    return
                modal.destroy()
                self.show_page("tasks", animate=False, force=True)

            actions = ctk.CTkFrame(panel, fg_color="transparent")
            actions.pack(fill="x", padx=18, pady=(0, 16))
            actions.grid_columnconfigure((0, 1), weight=1)
            ctk.CTkButton(actions, text="Save", height=42, corner_radius=14, fg_color=colors["primary"], hover_color=colors["primary_hover"], text_color=colors["white"], command=save_edit).grid(row=0, column=0, sticky="ew", padx=(0, 8))
            ctk.CTkButton(actions, text="Cancel", height=42, corner_radius=14, fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"], command=modal.destroy).grid(row=0, column=1, sticky="ew", padx=(8, 0))

        def delete_selected():
            task_id = selected_id()
            if task_id is None:
                return
            if self.ask_yes_no("Delete task", "Delete the selected task?"):
                database.delete_task(task_id)
                self.show_page("tasks", animate=False, force=True)

        def complete_selected():
            task_id = selected_id()
            if task_id is None:
                return
            task = database.get_task_by_id(task_id)
            if not task:
                self.show_error("Tasks", "Could not load this task.")
                return
            if task.get("status") == "completed":
                self.show_info("Tasks", "This task is already completed.")
                return
            self.show_completion_quiz(task_id, task)

        def pending_selected():
            task_id = selected_id()
            if task_id is None:
                return
            database.mark_task_status(task_id, "pending")
            self.show_page("tasks", animate=False, force=True)

        def edit_timetable():
            task_id = selected_id()
            if task_id is None:
                return
            script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "add_task.py")
            try:
                subprocess.Popen(
                    [sys.executable, script, self.username, "--edit", str(task_id)],
                    close_fds=os.name != "nt",
                )
            except OSError:
                self.show_error("Task Editor", "Could not open the task editor.")

        self.button(toolbar, "Edit task", edit_timetable, variant="secondary", height=40).pack(side="left", padx=(0, 8))
        self.button(toolbar, "Mark Completed", complete_selected, height=40).pack(side="left", padx=(0, 8))
        self.button(toolbar, "Mark Pending", pending_selected, variant="danger", height=40).pack(side="left", padx=(0, 8))
        self.button(toolbar, "Delete task", delete_selected, variant="danger", height=40).pack(side="left", padx=(0, 8))
        tree.bind("<ButtonRelease-1>", select_tree_row)
        tree.bind("<Double-1>", lambda event: (select_tree_row(event), edit_timetable()))

    def page_attendance(self):
        frame = self.page_frame("Attendance", "Track today and review this week's attendance from the same workspace.")
        snapshot = load_dashboard_snapshot(self.username)
        attendance = snapshot.attendance
        top = ctk.CTkFrame(frame, fg_color="transparent")
        top.pack(fill="x", pady=(0, 14))
        self.stat_card(top, "Current Week", f"{attendance['percentage']}%", self.colors["pink"]).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.stat_card(top, "Present Days", f"{attendance['present_this_week']} / {attendance['required_this_week']}", self.colors["green"]).pack(side="left", fill="x", expand=True, padx=8)
        self.stat_card(top, "Leave Day", attendance["leave_day_name"], self.colors["yellow"]).pack(side="left", fill="x", expand=True, padx=(8, 0))
        week = self.panel(frame, "This Week")
        week.pack(fill="x", pady=(0, 14))
        for item in attendance["week"]:
            color = self.colors["green"] if item["status"] == "present" else self.colors["yellow"] if item["status"] == "leave" else self.colors["secondary"]
            ctk.CTkLabel(week, text=f"{item['label']}  {fmt_date(item['date'])}  -  {item['status'].title()}", height=36, corner_radius=14, fg_color=color, text_color=self.colors["white"] if item["status"] == "present" else self.colors["text"], font=("Segoe UI Semibold", 12)).pack(fill="x", padx=18, pady=4)
        controls = ctk.CTkFrame(frame, fg_color=self.colors["surface"], corner_radius=22, border_width=1, border_color=self.colors["surface_border"])
        controls.pack(fill="x")
        self.button(controls, "Mark present today", lambda: self.mark_present_and_refresh("attendance")).pack(side="left", padx=18, pady=18)
        leave_var = ctk.StringVar(value=attendance["leave_day_name"])
        menu = ctk.CTkOptionMenu(controls, values=WEEKDAY_NAMES, variable=leave_var, fg_color=self.colors["entry"], button_color=self.colors["primary"], command=lambda day: self.change_leave(day))
        menu.pack(side="left", padx=10, pady=18)

    def page_analytics(self):
        fonts = get_fonts(self.preferences)
        frame = self.page_frame("Analytics", "Track progress, log study sessions, and review weakness recommendations in the main app.")
        summary = database.get_progress_summary(self.username)
        weakness = WeaknessAnalyzer(self.username).analyze()
        form = ctk.CTkFrame(frame, fg_color=self.colors["surface"], corner_radius=22, border_width=1, border_color=self.colors["surface_border"])
        form.pack(fill="x", pady=(0, 14))
        for col in range(5):
            form.grid_columnconfigure(col, weight=1)
        self.form_label(form, "Topic", fonts).grid(row=0, column=0, sticky="w", padx=(18, 6), pady=(16, 6))
        self.form_label(form, "Minutes", fonts).grid(row=0, column=1, sticky="w", padx=6, pady=(16, 6))
        self.form_label(form, "Rating", fonts).grid(row=0, column=2, sticky="w", padx=6, pady=(16, 6))
        self.form_label(form, "Completion status", fonts).grid(row=0, column=3, sticky="w", padx=6, pady=(16, 6))
        topic_entry = self.entry(form, "Topic")
        minutes_entry = self.entry(form, "Minutes")
        rating_var = ctk.StringVar(value="3")
        status_var = ctk.StringVar(value="completed")
        topic_entry.grid(row=1, column=0, sticky="ew", padx=(18, 6), pady=(0, 18))
        minutes_entry.grid(row=1, column=1, sticky="ew", padx=6, pady=(0, 18))
        ctk.CTkOptionMenu(form, values=["1", "2", "3", "4", "5"], variable=rating_var, height=42, fg_color=self.colors["entry"], button_color=self.colors["primary"], text_color=self.colors["text"]).grid(row=1, column=2, sticky="ew", padx=6, pady=(0, 18))
        ctk.CTkOptionMenu(form, values=["completed", "partial", "skipped", "postponed"], variable=status_var, height=42, fg_color=self.colors["entry"], button_color=self.colors["primary"], text_color=self.colors["text"]).grid(row=1, column=3, sticky="ew", padx=6, pady=(0, 18))

        def log_session():
            topic = topic_entry.get().strip()
            try:
                minutes = int(minutes_entry.get().strip())
                rating = int(rating_var.get())
            except ValueError:
                self.show_error("Invalid Session", "Minutes and rating must be numbers.")
                return
            if not topic or minutes <= 0:
                self.show_error("Invalid Session", "Add a topic and positive duration.")
                return
            database.log_study_session(self.username, minutes, subject="General", topic=topic, understanding_rating=rating, completion_status=status_var.get())
            XPSystem(self.username).award_study_session(minutes)
            self.show_page("analytics", animate=False)

        self.button(form, "Log Session", log_session).grid(row=1, column=4, sticky="ew", padx=(6, 18), pady=(0, 18))

        grid = ctk.CTkFrame(frame, fg_color="transparent")
        grid.pack(fill="x", pady=(0, 14))
        for title, value, accent in [
            ("Completion Rate", f"{summary['completion_rate']}%", self.colors["green"]),
            ("Weekly Completion", f"{summary['weekly_completion_rate']}%", self.colors["primary"]),
            ("Study Minutes", summary["total_study_minutes"], self.colors["yellow"]),
            ("Weakest Subject", weakness["weakest_subject"], self.colors["danger"]),
        ]:
            self.stat_card(grid, title, value, accent).pack(side="left", fill="x", expand=True, padx=6)

        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(1, weight=1)

        chart = self.panel(body, "Weekly Study Minutes")
        chart.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 14))
        max_minutes = max(summary["weekly_minutes"] or [1]) or 1
        for label, minutes in zip(summary["weekly_labels"], summary["weekly_minutes"]):
            row = ctk.CTkFrame(chart, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=6)
            ctk.CTkLabel(row, text=label, width=42, text_color=self.colors["text"]).pack(side="left")
            bar = ctk.CTkProgressBar(row, height=14, progress_color=self.colors["primary"], fg_color=self.colors["secondary"])
            bar.pack(side="left", fill="x", expand=True, padx=10)
            bar.set(minutes / max_minutes)
            ctk.CTkLabel(row, text=f"{minutes} min", width=70, text_color=self.colors["muted"]).pack(side="right")

        recs = self.panel(body, "Recommended Revision")
        recs.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 14))
        ctk.CTkLabel(recs, text=weakness["improvement_trend"], font=("Segoe UI Semibold", 13), text_color=self.colors["deep"], wraplength=420, justify="left").pack(anchor="w", padx=18, pady=(0, 8))
        for item in weakness["recommended_tasks"][:5]:
            ctk.CTkLabel(recs, text=item, font=("Segoe UI", 12), text_color=self.colors["text"], wraplength=420, justify="left").pack(anchor="w", padx=18, pady=4)
        self.button(recs, "Seed Sample Data", self.seed_sample_and_refresh, variant="secondary").pack(anchor="w", padx=18, pady=(12, 18))

        subjects = self.panel(body, "Subject Performance")
        subjects.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        for subject in weakness["subject_performance"][:8]:
            row = ctk.CTkFrame(subjects, fg_color=self.colors["tile"], corner_radius=14)
            row.pack(fill="x", padx=18, pady=5)
            ctk.CTkLabel(row, text=subject["subject"], font=("Segoe UI Semibold", 13), text_color=self.colors["text"]).pack(anchor="w", padx=14, pady=(8, 1))
            meta = f"Rating {subject['average_rating']}/5 | Weak {subject['weak_sessions']} | Study {subject['study_minutes']} min | Tasks {subject['completed_tasks']}/{subject['total_tasks']}"
            ctk.CTkLabel(row, text=meta, font=("Segoe UI", 11), text_color=self.colors["muted"]).pack(anchor="w", padx=14, pady=(0, 8))

        topics = self.panel(body, "Weak Topic Priority")
        topics.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
        tree = ttk.Treeview(topics, columns=("subject", "topic", "rating", "avoids", "priority"), show="headings", height=7)
        for column, label, width in [("subject", "Subject", 110), ("topic", "Topic", 160), ("rating", "Rating", 60), ("avoids", "Avoids", 60), ("priority", "Priority", 70)]:
            tree.heading(column, text=label)
            tree.column(column, width=width, anchor="w")
        tree.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        for topic in weakness["weak_topics"][:12]:
            tree.insert("", "end", values=(topic["subject"], topic["topic"], topic["average_rating"], topic["avoid_count"], topic["priority_score"]))

    def page_settings(self):
        settings = database.get_user_preferences(self.username)
        self.preferences = settings
        fonts = get_fonts(settings)
        frame = self.page_frame("Settings", "Tune appearance, reminders, attendance rules, backups, and progress state from one control center.")
        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure((0, 1), weight=1, uniform="settings")

        appearance = self.panel(body, "Theme Manager")
        appearance.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 14))
        behavior = self.panel(body, "Study Behavior")
        behavior.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=(0, 14))
        attendance_panel = self.panel(body, "Attendance Rules")
        attendance_panel.grid(row=1, column=0, sticky="nsew", padx=(0, 10), pady=(0, 14))
        data_panel = self.panel(body, "Data and Maintenance")
        data_panel.grid(row=1, column=1, sticky="nsew", padx=(10, 0), pady=(0, 14))

        mode_var = ctk.StringVar(value=settings["appearance_mode"])
        theme_var = ctk.StringVar(value=settings["theme_name"])
        accent_var = ctk.StringVar(value=settings["custom_accent"])
        self.form_label(appearance, "Appearance mode", fonts).pack(anchor="w", padx=18, pady=(0, 6))
        ctk.CTkOptionMenu(appearance, values=["light", "dark"], variable=mode_var, height=42, corner_radius=16, fg_color=self.colors["entry"], button_color=self.colors["primary"], text_color=self.colors["text"]).pack(fill="x", padx=18, pady=(0, 14))
        self.form_label(appearance, "Accent theme", fonts).pack(anchor="w", padx=18, pady=(0, 6))
        ctk.CTkOptionMenu(appearance, values=["green", "blue", "custom"], variable=theme_var, height=42, corner_radius=16, fg_color=self.colors["entry"], button_color=self.colors["primary"], text_color=self.colors["text"]).pack(fill="x", padx=18, pady=(0, 14))
        accent_row = ctk.CTkFrame(appearance, fg_color="transparent")
        accent_row.pack(fill="x", padx=18, pady=(0, 14))
        self.form_label(accent_row, "Custom accent hex", fonts).pack(anchor="w", pady=(0, 6))
        accent_entry = self.entry(accent_row, "Custom accent hex")
        accent_entry.insert(0, accent_var.get())
        accent_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def pick_color():
            picked = colorchooser.askcolor(color=accent_entry.get() or self.colors["primary"], title="Choose custom accent", parent=self)
            if picked and picked[1]:
                accent_entry.delete(0, "end")
                accent_entry.insert(0, picked[1])
                theme_var.set("custom")

        self.button(accent_row, "Pick Color", pick_color, variant="secondary").pack(side="right")
        status = ctk.CTkLabel(data_panel, text="Settings are saved to config.json.", font=fonts["body"], text_color=self.colors["muted"], anchor="w")

        def save_theme_settings():
            accent = accent_entry.get().strip()
            self.preferences = database.update_user_preferences(
                self.username,
                appearance_mode=mode_var.get(),
                theme_name=theme_var.get(),
                custom_accent=accent if theme_var.get() == "custom" else settings["custom_accent"],
            )
            self.current_theme = self.preferences["appearance_mode"]
            self.colors = get_theme_colors(self.preferences)
            sync_global_preferences(self.preferences)
            ctk.set_appearance_mode(self.current_theme)
            self.configure(fg_color=self.colors["bg"])
            self.build_shell()
            self.show_page("settings", animate=False)

        self.button(appearance, "Apply Theme", save_theme_settings).pack(fill="x", padx=18, pady=(0, 18))

        notifications_var = ctk.BooleanVar(value=settings["notifications_enabled"])
        reminders_var = ctk.BooleanVar(value=settings["study_reminders_enabled"])
        sound_var = ctk.BooleanVar(value=settings["sound_effects_enabled"])
        autosave_var = ctk.BooleanVar(value=settings["auto_save_enabled"])
        for text, variable in [
            ("Notifications", notifications_var),
            ("Study reminders", reminders_var),
            ("Sound effects", sound_var),
            ("Auto-save", autosave_var),
        ]:
            ctk.CTkSwitch(
                behavior,
                text=text,
                variable=variable,
                height=28,
                text_color=self.colors["text"],
                progress_color=self.colors["primary"],
                fg_color=self.colors["secondary"],
            ).pack(anchor="w", padx=18, pady=7)

        duration_var = ctk.IntVar(value=int(settings["default_study_duration"]))
        font_var = ctk.IntVar(value=int(settings["font_size"]))
        duration_entry = self.settings_entry(behavior, "Default study duration", str(settings["default_study_duration"]), fonts)
        duration_slider = ctk.CTkSlider(behavior, from_=5, to=240, number_of_steps=47, variable=duration_var, progress_color=self.colors["primary"], button_color=self.colors["primary"], button_hover_color=self.colors["primary_hover"])
        duration_slider.pack(fill="x", padx=18, pady=(0, 14))
        font_entry = self.settings_entry(behavior, "Font size", str(settings["font_size"]), fonts)
        font_slider = ctk.CTkSlider(behavior, from_=11, to=20, number_of_steps=9, variable=font_var, progress_color=self.colors["primary"], button_color=self.colors["primary"], button_hover_color=self.colors["primary_hover"])
        font_slider.pack(fill="x", padx=18, pady=(0, 14))

        def sync_duration(_value):
            duration_entry.delete(0, "end")
            duration_entry.insert(0, str(int(duration_var.get())))

        def sync_font(_value):
            font_entry.delete(0, "end")
            font_entry.insert(0, str(int(font_var.get())))

        duration_slider.configure(command=sync_duration)
        font_slider.configure(command=sync_font)

        attendance = load_dashboard_snapshot(self.username).attendance
        leave_var = ctk.StringVar(value=attendance["leave_day_name"])
        self.form_label(attendance_panel, "Weekly leave / holiday", fonts).pack(anchor="w", padx=18, pady=(0, 6))
        leave_menu = ctk.CTkOptionMenu(
            attendance_panel,
            values=WEEKDAY_NAMES,
            variable=leave_var,
            height=42,
            corner_radius=16,
            fg_color=self.colors["entry"],
            button_color=self.colors["primary"],
            text_color=self.colors["text"],
            state="normal" if attendance.get("leave_enabled", True) else "disabled",
        )
        leave_menu.pack(fill="x", padx=18, pady=(0, 8))
        ctk.CTkLabel(
            attendance_panel,
            text=(
                f"Current attendance: {attendance['percentage']}%. Holiday changes unlock at 75%."
                if not attendance.get("leave_enabled", True)
                else f"Current attendance: {attendance['percentage']}%. Holiday locks below 75%."
            ),
            font=fonts["small"],
            text_color=self.colors["danger"] if not attendance.get("leave_enabled", True) else self.colors["muted"],
            wraplength=360,
            justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 12))
        self.stat_card(attendance_panel, "Present This Week", f"{attendance['present_this_week']} / {attendance['required_this_week']}", self.colors["green"]).pack(fill="x", padx=18, pady=(0, 18))

        def save_behavior_settings():
            try:
                duration = int(duration_entry.get())
                font_size = int(font_entry.get())
            except ValueError:
                self.show_error("Invalid Settings", "Duration and font size must be whole numbers.")
                return
            self.preferences = database.update_user_preferences(
                self.username,
                notifications_enabled=notifications_var.get(),
                study_reminders_enabled=reminders_var.get(),
                sound_effects_enabled=sound_var.get(),
                auto_save_enabled=autosave_var.get(),
                default_study_duration=duration,
                font_size=font_size,
            )
            if attendance.get("leave_enabled", True):
                database.update_attendance_leave_day(self.username, WEEKDAY_NAMES.index(leave_var.get()))
            self.current_theme = self.preferences["appearance_mode"]
            self.colors = get_theme_colors(self.preferences)
            sync_global_preferences(self.preferences)
            status.configure(text="Behavior and attendance settings saved for this account.")
            self.current_page = None
            self.show_page("settings", animate=False)

        self.button(behavior, "Save Behavior", save_behavior_settings).pack(fill="x", padx=18, pady=(4, 18))
        self.button(attendance_panel, "Save Attendance Rule", save_behavior_settings).pack(fill="x", padx=18, pady=(0, 18))

        actions = ctk.CTkFrame(data_panel, fg_color="transparent")
        actions.pack(fill="x", padx=18, pady=(0, 14))
        actions.grid_columnconfigure((0, 1, 2), weight=1)

        def backup_data():
            directory = filedialog.askdirectory(title="Choose backup folder", parent=self)
            if not directory:
                return
            backup_path = settings_manager.backup_database(directory)
            status.configure(text=f"Backup created: {backup_path}" if backup_path else "No database file found to back up.")

        def download_instructions():
            if not INSTRUCTIONS_PDF.exists():
                self.show_error("Instructions Missing", "The instructions PDF could not be found.")
                return
            destination = filedialog.asksaveasfilename(
                title="Download Instructions",
                parent=self,
                defaultextension=".pdf",
                initialfile="instructions.pdf",
                filetypes=[("PDF files", "*.pdf")],
            )
            if not destination:
                return
            try:
                shutil.copyfile(INSTRUCTIONS_PDF, destination)
            except OSError as error:
                self.show_error("Download Failed", f"Could not save instructions PDF:\n{error}")
                return
            status.configure(text=f"Instructions downloaded: {destination}")

        def reset_settings():
            if not self.ask_yes_no("Reset Settings", "Reset app settings to defaults?"):
                return
            self.preferences = database.reset_user_preferences(self.username)
            self.current_theme = self.preferences["appearance_mode"]
            self.colors = get_theme_colors(self.preferences)
            sync_global_preferences(self.preferences)
            ctk.set_appearance_mode(self.current_theme)
            self.build_shell()
            self.show_page("settings", animate=False)

        def reset_progress():
            if not self.ask_yes_no("Reset Progress", "Clear study sessions, XP, badges, and completion progress?"):
                return
            database.reset_user_progress(self.username)
            status.configure(text="Progress reset for this user.")

        self.button(actions, "Backup / Export Data", backup_data).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.button(actions, "Reset Settings", reset_settings, variant="secondary").grid(row=0, column=1, sticky="ew", padx=8)
        self.button(actions, "Reset Progress", reset_progress, variant="danger").grid(row=0, column=2, sticky="ew", padx=(8, 0))
        self.button(actions, "Instructions", download_instructions).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        status.configure(text="Settings are saved per user account.")
        status.pack(anchor="w", padx=18, pady=(0, 18))

    def mark_present_and_refresh(self, page):
        database.mark_attendance(self.username, date.today().isoformat(), "present")
        XPSystem(self.username).award_attendance(date.today().isoformat())
        self.show_page(page, animate=False)

    def change_leave(self, day):
        database.update_attendance_leave_day(self.username, WEEKDAY_NAMES.index(day))
        self.show_page("attendance", animate=False)

    def change_leave_from_dashboard(self, day):
        database.update_attendance_leave_day(self.username, WEEKDAY_NAMES.index(day))
        self.show_page("dashboard", animate=False)

    def seed_sample_and_refresh(self):
        added = database.seed_sample_study_data(self.username)
        self.show_info("Sample Data", "Sample study data added." if added else "Existing data found, so sample data was not duplicated.")
        self.show_page("analytics", animate=False)

    def status_color(self, status):
        if status == "present":
            return self.colors["green"]
        if status == "leave":
            return self.colors["yellow"]
        return self.colors["tile"]

    def dashboard_section(self, parent, title, row, column, columnspan):
        ctk.CTkLabel(parent, text=title, font=("Segoe UI Semibold", 14), text_color=self.colors["text"]).grid(row=row, column=column, columnspan=columnspan, sticky="w", padx=(0 if column == 0 else 8, 0), pady=(12, 6))

    def info_row(self, parent, text, meta="", done=False):
        row = ctk.CTkFrame(parent, fg_color=self.colors["tile"], corner_radius=16)
        status = ctk.CTkLabel(row, text="Done" if done else "Open", width=46, height=26, corner_radius=13, fg_color=self.colors["green"] if done else self.colors["deep"], text_color=self.colors["white"], font=("Segoe UI Semibold", 10))
        status.pack(side="left", padx=(10, 8), pady=8)
        ctk.CTkLabel(row, text=text, font=("Segoe UI", 12), text_color=self.colors["text"], anchor="w", justify="left").pack(side="left", fill="x", expand=True)
        if meta:
            ctk.CTkLabel(row, text=meta, font=("Segoe UI Semibold", 11), text_color=self.colors["pink"]).pack(side="right", padx=10)
        return row

    def metric_mini(self, parent, title, value, accent):
        card = ctk.CTkFrame(parent, fg_color=self.colors["surface"], corner_radius=20, border_width=1, border_color=self.colors["surface_border"])
        ctk.CTkLabel(card, text=title, font=("Segoe UI Semibold", 12), text_color=self.colors["text"]).pack(anchor="w", padx=16, pady=(14, 4))
        ctk.CTkLabel(card, text=value, font=("Segoe UI Semibold", 24), text_color=accent).pack(anchor="w", padx=16)
        ctk.CTkFrame(card, height=4, corner_radius=999, fg_color=accent).pack(fill="x", padx=16, pady=(12, 14))
        return card

    def form_label(self, parent, text, fonts=None):
        fonts = fonts or get_fonts(settings_manager.load())
        return ctk.CTkLabel(parent, text=text, font=fonts["body_semibold"], text_color=self.colors["text"])

    def settings_entry(self, parent, label, value, fonts=None):
        self.form_label(parent, label, fonts).pack(anchor="w", padx=18, pady=(0, 6))
        entry = self.entry(parent, label)
        entry.insert(0, value)
        entry.pack(fill="x", padx=18, pady=(0, 14))
        return entry

    def logout(self):
        self.username = ""
        self.show_login()

    def panel(self, parent, title):
        fonts = get_fonts(self.preferences)
        panel = ctk.CTkFrame(parent, fg_color=self.colors["surface"], corner_radius=22, border_width=1, border_color=self.colors["surface_border"])
        ctk.CTkLabel(panel, text=title, font=fonts["body_semibold"], text_color=self.colors["text"]).pack(anchor="w", padx=18, pady=(16, 10))
        return panel

    def stat_card(self, parent, title, value, accent):
        fonts = get_fonts(self.preferences)
        card = ctk.CTkFrame(parent, fg_color=self.colors["surface"], corner_radius=20, border_width=1, border_color=self.colors["surface_border"])
        ctk.CTkLabel(card, text=str(value), font=fonts["section"], text_color=self.colors["text"]).pack(anchor="w", padx=18, pady=(16, 2))
        ctk.CTkLabel(card, text=title, font=fonts["small"], text_color=self.colors["muted"]).pack(anchor="w", padx=18)
        ctk.CTkFrame(card, height=4, corner_radius=999, fg_color=accent).pack(fill="x", padx=18, pady=(12, 16))
        return card

    def task_chip(self, parent, task):
        fonts = get_fonts(self.preferences)
        chip = ctk.CTkFrame(parent, fg_color=self.colors["tile"], corner_radius=16)
        ctk.CTkLabel(chip, text=task["title"], font=fonts["body_semibold"], text_color=self.colors["text"]).pack(anchor="w", padx=14, pady=(10, 1))
        ctk.CTkLabel(chip, text=f"{task.get('subject') or 'General'} - {fmt_date(task.get('due_date') or task.get('study_date'))}", font=fonts["small"], text_color=self.colors["muted"]).pack(anchor="w", padx=14, pady=(0, 10))
        return chip

    def entry(self, parent, placeholder, show=None):
        entry = ctk.CTkEntry(
            parent,
            height=46,
            corner_radius=16,
            border_width=1,
            placeholder_text=placeholder,
            show=show,
            fg_color=self.colors["entry"],
            border_color=self.colors["entry_border"],
            text_color=self.colors["text"],
            placeholder_text_color=self.colors["muted"],
        )
        entry.bind("<FocusIn>", lambda _event: entry.configure(border_color=self.colors["primary"], border_width=2))
        entry.bind("<FocusOut>", lambda _event: entry.configure(border_color=self.colors["entry_border"], border_width=1))
        return entry

    def auth_entry(self, parent, placeholder, icon, show=None):
        box = ctk.CTkFrame(parent, height=58, corner_radius=18, fg_color=self.colors["entry"], border_width=1, border_color=self.colors["entry_border"])
        box.grid_propagate(False)
        box.grid_rowconfigure(0, weight=1)
        box.grid_columnconfigure(1, weight=1)
        icon_label = ctk.CTkLabel(
            box,
            text=icon,
            width=34,
            height=34,
            corner_radius=12,
            fg_color=self.colors["secondary"],
            text_color=self.colors["deep"],
            font=("Segoe UI Semibold", 15),
        )
        icon_label.grid(row=0, column=0, sticky="w", padx=(12, 10))
        entry = ctk.CTkEntry(
            box,
            height=50,
            border_width=0,
            corner_radius=14,
            placeholder_text=placeholder,
            show=show,
            fg_color="transparent",
            text_color=self.colors["text"],
            placeholder_text_color=self.colors["muted"],
        )
        entry.grid(row=0, column=1, sticky="ew", padx=(0, 16), pady=4)

        def focus_in(_event):
            box.configure(border_color=self.colors["primary"], border_width=2)

        def focus_out(_event):
            box.configure(border_color=self.colors["entry_border"], border_width=1)

        entry.bind("<FocusIn>", focus_in)
        entry.bind("<FocusOut>", focus_out)
        box.get = entry.get
        box.focus = entry.focus
        box.delete = entry.delete
        box.insert = entry.insert
        return box

    def button(self, parent, text, command, variant="primary", height=42):
        fonts = get_fonts(self.preferences)
        if variant == "secondary":
            fg, hover, text_color = self.colors["secondary"], self.colors["secondary_hover"], self.colors["secondary_text"]
        elif variant == "danger":
            fg, hover, text_color = self.colors["danger"], self.colors["danger_hover"], self.colors["white"]
        else:
            fg, hover, text_color = self.colors["primary"], self.colors["primary_hover"], self.colors["white"]
        return ctk.CTkButton(parent, text=text, height=height, corner_radius=16, fg_color=fg, hover_color=hover, text_color=text_color, font=fonts["body_semibold"], command=command)


def run(initial_page="login", username=""):
    app = SingleWindowApp(initial_page=initial_page, username=username)
    app.mainloop()


if __name__ == "__main__":
    run()
