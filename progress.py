if __name__ == "__main__":
    import sys
    from single_window_app import run
    run(initial_page="analytics", username=sys.argv[1] if len(sys.argv) > 1 else "")
    raise SystemExit

import os
import sys
from datetime import datetime
from tkinter import ttk

import customtkinter as ctk
# Lazy import matplotlib - only import when needed for charts
# from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
# from matplotlib.figure import Figure
from PIL import Image, UnidentifiedImageError

import database
from tk_safety import disable_unsafe_windows_titlebar_focus_restore
from theme_manager import get_theme_colors, load_theme as global_load_theme, save_theme as global_save_theme
from ui.modern import make_app_shell, page_header, style_treeview

disable_unsafe_windows_titlebar_focus_restore()

THEME_FILE = "theme.txt"

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
    "success": "#73c8bf",
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
    "success": "#8fded4",
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


def refresh_data():
    global summary
    summary = database.get_progress_summary(username)
    name_label.configure(text=f"{username}'s Progress")
    total_value.configure(text=str(summary["total_tasks"]))
    completed_value.configure(text=str(summary["completed_tasks"]))
    pending_value.configure(text=str(summary["pending_tasks"]))
    hours_value.configure(text=f"{summary['total_study_minutes']} min")
    highlight_label.configure(text=f"Completion rate: {summary['completion_rate']}% | This week: {summary['weekly_completion_rate']}%")
    top_subject = summary["subject_minutes"][0] if summary.get("subject_minutes") else ("No subject yet", 0)
    priority_counts = summary.get("priority_counts", {})
    analytics_label.configure(
        text=(
            f"Most time: {top_subject[0]} ({top_subject[1]} min) | "
            f"Delayed/overdue tasks: {summary.get('overdue_tasks', 0)} | "
            f"Priority mix: High {priority_counts.get('High', 0)}, Medium {priority_counts.get('Medium', 0)}, Low {priority_counts.get('Low', 0)}"
        )
    )
    for item in reminders_tree.get_children():
        reminders_tree.delete(item)
    for reminder in summary["reminders"]:
        reminders_tree.insert("", "end", values=(reminder["title"], reminder.get("priority", "Medium"), reminder["subject"], format_indian_date(reminder.get("due_date") or reminder.get("study_date"))))
    draw_chart()


def draw_chart():
    global chart_canvas, chart_figure
    # Lazy import matplotlib only when rendering charts
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    
    colors = palette()
    if chart_canvas is not None:
        chart_canvas.get_tk_widget().destroy()
    if chart_figure is not None:
        chart_figure.clf()
    chart_figure = Figure(figsize=(5.6, 2.7), dpi=100)
    chart_figure.patch.set_facecolor(colors["surface"])
    axis = chart_figure.add_subplot(111)
    axis.set_facecolor(colors["surface"])
    axis.bar(summary["weekly_labels"], summary["weekly_minutes"], color=colors["primary"], width=0.55)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.spines["left"].set_color(colors["surface_border"])
    axis.spines["bottom"].set_color(colors["surface_border"])
    axis.tick_params(axis="x", colors=colors["muted"], labelsize=9)
    axis.tick_params(axis="y", colors=colors["muted"], labelsize=9)
    axis.set_ylabel("Minutes", color=colors["muted"], fontsize=9)
    axis.set_title("Weekly Study Minutes", color=colors["text"], fontsize=12, pad=10)
    chart_figure.tight_layout()
    chart_canvas = FigureCanvasTkAgg(chart_figure, master=chart_frame)
    chart_canvas.draw()
    chart_canvas.get_tk_widget().pack(fill="both", expand=True)


def apply_theme():
    colors = palette()
    app.configure(fg_color=colors["bg"])
    root_frame.configure(fg_color=colors["bg"])
    app_shell.configure(fg_color=colors["panel"], border_color=colors["panel_border"])
    nav_rail.configure(fg_color=colors["sidebar"], border_color=colors["sidebar_border"])
    outer.configure(fg_color="transparent")
    header.configure(fg_color=colors["header"], border_color=colors["header_border"])
    for frame in [stats_grid, chart_panel, reminders_panel]:
        frame.configure(fg_color=colors["surface"], border_color=colors["surface_border"])
    for label in [heading, subtitle, name_label, highlight_label, analytics_label, total_title, completed_title, pending_title, hours_title, chart_title, reminders_title]:
        label.configure(text_color=colors["text"])
    subtitle.configure(text_color=colors["muted"])
    highlight_label.configure(text_color=colors["success"])
    close_btn.configure(fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"])
    refresh_btn.configure(fg_color=colors["primary"], hover_color=colors["primary_hover"], text_color="#ffffff")
    theme_btn.configure(
        image=sun_icon if current_theme == "dark" else moon_icon,
        fg_color=colors["panel"],
        hover_color=colors["surface"],
        border_color=colors["panel_border"],
        text_color=colors["secondary_text"],
    )
    style_treeview(style, "Progress.Treeview", colors)


username = resolve_username(sys.argv[1] if len(sys.argv) > 1 else "")
current_theme = load_theme()
ctk.set_appearance_mode(current_theme)
ctk.set_default_color_theme("blue")
summary = {}
chart_canvas = None
chart_figure = None

app = ctk.CTk()
app.title("Progress | Schedly")
app.minsize(1020, 680)
try:
    app.attributes("-alpha", 0.0)
except Exception:
    pass

sun_icon = load_image("sun.png", (20, 20))
moon_icon = load_image("moon.png", (20, 20))

root_frame = ctk.CTkFrame(app, fg_color="transparent")
root_frame.pack(fill="both", expand=True)

app_shell, nav_rail, content_area = make_app_shell(root_frame, palette(), active_label="Progress")

outer = ctk.CTkFrame(content_area, corner_radius=0, border_width=0, fg_color="transparent")
outer.grid(row=1, column=0, sticky="nsew")
outer.grid_columnconfigure(0, weight=1)
outer.grid_rowconfigure(5, weight=1)

header = ctk.CTkFrame(content_area, corner_radius=24, border_width=1)
header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
header.grid_columnconfigure(0, weight=1)
heading = ctk.CTkLabel(header, text="Progress Analytics", font=("Segoe UI Semibold", 28))
heading.grid(row=0, column=0, sticky="w", padx=22, pady=(18, 0))
subtitle = ctk.CTkLabel(header, text="A modern performance view for task completion, study minutes, reminders, and weekly momentum.", font=("Segoe UI", 14), wraplength=760, justify="left")
subtitle.grid(row=1, column=0, sticky="w", padx=22, pady=(6, 18))

def toggle_theme():
    global current_theme
    current_theme = "dark" if current_theme == "light" else "light"
    ctk.set_appearance_mode(current_theme)
    global_save_theme(current_theme)
    apply_theme()
    refresh_data()

theme_btn = ctk.CTkButton(header, text="", width=42, height=42, corner_radius=16, border_width=1, command=toggle_theme)
theme_btn.grid(row=0, column=1, rowspan=2, sticky="e", padx=22)

controls = ctk.CTkFrame(outer, fg_color="transparent")
controls.pack(fill="x", padx=0, pady=(0, 14))
refresh_btn = ctk.CTkButton(controls, text="Refresh", height=42, corner_radius=14, command=refresh_data)
refresh_btn.pack(side="left")
close_btn = ctk.CTkButton(controls, text="Close", height=42, corner_radius=14, command=app.destroy)
close_btn.pack(side="right")

name_label = ctk.CTkLabel(outer, text="", font=("Segoe UI Semibold", 20))
name_label.pack(anchor="w", padx=2, pady=(0, 14))

stats_grid = ctk.CTkFrame(outer, corner_radius=24, border_width=1)
stats_grid.pack(fill="x", padx=0, pady=(0, 16))
for idx in range(4):
    stats_grid.grid_columnconfigure(idx, weight=1)

total_title = ctk.CTkLabel(stats_grid, text="Total Tasks", font=("Segoe UI", 13))
total_title.grid(row=0, column=0, sticky="w", padx=18, pady=(18, 6))
total_value = ctk.CTkLabel(stats_grid, text="0", font=("Segoe UI Semibold", 26))
total_value.grid(row=1, column=0, sticky="w", padx=18, pady=(0, 18))
completed_title = ctk.CTkLabel(stats_grid, text="Completed", font=("Segoe UI", 13))
completed_title.grid(row=0, column=1, sticky="w", padx=18, pady=(18, 6))
completed_value = ctk.CTkLabel(stats_grid, text="0", font=("Segoe UI Semibold", 26))
completed_value.grid(row=1, column=1, sticky="w", padx=18, pady=(0, 18))
pending_title = ctk.CTkLabel(stats_grid, text="Pending", font=("Segoe UI", 13))
pending_title.grid(row=0, column=2, sticky="w", padx=18, pady=(18, 6))
pending_value = ctk.CTkLabel(stats_grid, text="0", font=("Segoe UI Semibold", 26))
pending_value.grid(row=1, column=2, sticky="w", padx=18, pady=(0, 18))
hours_title = ctk.CTkLabel(stats_grid, text="Study Minutes", font=("Segoe UI", 13))
hours_title.grid(row=0, column=3, sticky="w", padx=18, pady=(18, 6))
hours_value = ctk.CTkLabel(stats_grid, text="0 hr", font=("Segoe UI Semibold", 26))
hours_value.grid(row=1, column=3, sticky="w", padx=18, pady=(0, 18))

highlight_label = ctk.CTkLabel(outer, text="", font=("Segoe UI Semibold", 14))
highlight_label.pack(anchor="w", padx=2, pady=(0, 12))
analytics_label = ctk.CTkLabel(outer, text="", font=("Segoe UI", 13), wraplength=900, justify="left")
analytics_label.pack(anchor="w", padx=2, pady=(0, 16))

content = ctk.CTkFrame(outer, fg_color="transparent")
content.pack(fill="both", expand=True, padx=0, pady=(0, 0))
content.grid_columnconfigure(0, weight=3)
content.grid_columnconfigure(1, weight=2)
content.grid_rowconfigure(0, weight=1)

chart_panel = ctk.CTkFrame(content, corner_radius=24, border_width=1)
chart_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
chart_title = ctk.CTkLabel(chart_panel, text="Progress Insights", font=("Segoe UI Semibold", 20))
chart_title.pack(anchor="w", padx=20, pady=(18, 10))
chart_frame = ctk.CTkFrame(chart_panel, fg_color="transparent")
chart_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

reminders_panel = ctk.CTkFrame(content, corner_radius=24, border_width=1)
reminders_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
reminders_title = ctk.CTkLabel(reminders_panel, text="Upcoming Tasks", font=("Segoe UI Semibold", 20))
reminders_title.pack(anchor="w", padx=20, pady=(18, 10))

style = ttk.Style()
style.theme_use("default")
style.configure("Progress.Treeview", rowheight=34, font=("Segoe UI", 11))
style.configure("Progress.Treeview.Heading", font=("Segoe UI Semibold", 11))

reminders_tree = ttk.Treeview(reminders_panel, columns=("title", "priority", "subject", "date"), show="headings", style="Progress.Treeview")
for key, label, width in [("title", "Title", 170), ("priority", "Priority", 80), ("subject", "Subject", 110), ("date", "Date", 90)]:
    reminders_tree.heading(key, text=label)
    reminders_tree.column(key, width=width, anchor="w")
reminders_tree.pack(fill="both", expand=True, padx=20, pady=(0, 20))

apply_theme()
refresh_data()
app.after(100, refresh_data)
app.after(80, lambda: reveal_window(app))
app.mainloop()
