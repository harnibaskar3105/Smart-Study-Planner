import os
import subprocess
import sys

import customtkinter as ctk


NAV_ITEMS = [
    ("⌂", "Dashboard", "dashboard.py"),
    ("+", "Add Task", "add_task.py"),
    ("☷", "Tasks", "view_tasks.py"),
    ("◉", "Progress", "progress.py"),
    ("◆", "Analytics", "weakness_analyzer.py"),
    ("⚙", "Settings", "settings_page.py"),
]


def _nav_row(parent, colors, icon, label, command, selected=False):
    idle = colors["sidebar_active"] if selected else "transparent"
    hover = colors["sidebar_active"] if selected else colors["sidebar_hover"]
    text_color = colors["deep"] if selected else colors["text"]
    icon_bg = colors["sidebar_icon_active"] if selected else colors["sidebar_icon"]
    icon_color = colors["white"] if selected else colors["deep"]

    row = ctk.CTkFrame(
        parent,
        height=42,
        corner_radius=15,
        fg_color=idle,
        border_width=1 if selected else 0,
        border_color=colors.get("sidebar_active_border", colors["sidebar_border"]),
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
        fg_color=icon_bg,
        text_color=icon_color,
        font=("Segoe UI Semibold", 13),
    )
    icon_label.pack(side="left", padx=(10, 10), pady=7)

    text_label = ctk.CTkLabel(
        row,
        text=label,
        font=("Segoe UI Semibold", 12 if selected else 11),
        text_color=text_color,
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


def make_app_shell(parent, colors, active_label="", width=214):
    parent.configure(fg_color=colors["bg"])
    shell = ctk.CTkFrame(parent, fg_color=colors["panel"], corner_radius=30, border_width=1, border_color=colors["panel_border"])
    shell.pack(fill="both", expand=True, padx=22, pady=22)
    shell.grid_columnconfigure(0, weight=0)
    shell.grid_columnconfigure(1, weight=1)
    shell.grid_rowconfigure(0, weight=1)

    rail = ctk.CTkFrame(shell, width=width, fg_color=colors["sidebar"], corner_radius=28, border_width=1, border_color=colors["sidebar_border"])
    rail.grid(row=0, column=0, sticky="nsew", padx=(14, 0), pady=14)
    rail.grid_propagate(False)

    content = ctk.CTkFrame(shell, fg_color="transparent")
    content.grid(row=0, column=1, sticky="nsew", padx=18, pady=14)
    content.grid_columnconfigure(0, weight=1)
    content.grid_rowconfigure(1, weight=1)

    ctk.CTkLabel(rail, text="Schedly", font=("Segoe UI Semibold", 24), text_color=colors["text"]).pack(anchor="w", padx=22, pady=(24, 4))
    ctk.CTkLabel(rail, text="Study planner", font=("Segoe UI", 12), text_color=colors["muted"]).pack(anchor="w", padx=22, pady=(0, 16))

    username = (sys.argv[1] if len(sys.argv) > 1 else "Student").strip() or "Student"
    profile = ctk.CTkFrame(
        rail,
        fg_color=colors["sidebar_active"],
        corner_radius=20,
        border_width=1,
        border_color=colors.get("sidebar_active_border", colors["sidebar_border"]),
    )
    profile.pack(fill="x", padx=12, pady=(0, 16))
    ctk.CTkLabel(
        profile,
        text=(username[:1] or "S").upper(),
        width=40,
        height=40,
        corner_radius=20,
        fg_color=colors["yellow"],
        text_color=colors["text"],
        font=("Segoe UI Semibold", 17),
    ).pack(side="left", padx=(12, 10), pady=12)
    ctk.CTkLabel(profile, text=f"{username}\nStudent", font=("Segoe UI", 12), text_color=colors["muted"], justify="left").pack(side="left", fill="x", expand=True, pady=12)

    def launch(script):
        if not script or not os.path.exists(script):
            return
        username_arg = sys.argv[1] if len(sys.argv) > 1 else ""
        args = [sys.executable, script]
        if username_arg and script != "login.py":
            args.append(username_arg)
        subprocess.Popen(args)

    nav_group = ctk.CTkFrame(rail, fg_color="transparent")
    nav_group.pack(fill="x")
    for icon, label, script in NAV_ITEMS:
        selected = label.lower() == active_label.lower()
        _nav_row(nav_group, colors, icon, label, lambda path=script: launch(path), selected)

    ctk.CTkFrame(rail, fg_color="transparent").pack(fill="both", expand=True)
    _nav_row(rail, colors, "↩", "Log out", lambda: launch("login.py"), False)
    ctk.CTkFrame(rail, height=14, fg_color="transparent").pack()
    return shell, rail, content


def page_header(parent, colors, title, subtitle, actions=None):
    header = ctk.CTkFrame(parent, fg_color=colors["surface"], corner_radius=24, border_width=1, border_color=colors["surface_border"])
    header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
    header.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(header, text=title, font=("Segoe UI Semibold", 28), text_color=colors["text"]).grid(row=0, column=0, sticky="w", padx=22, pady=(18, 2))
    ctk.CTkLabel(header, text=subtitle, font=("Segoe UI", 13), text_color=colors["muted"], wraplength=780, justify="left").grid(row=1, column=0, sticky="w", padx=22, pady=(4, 18))
    if actions:
        action_box = ctk.CTkFrame(header, fg_color="transparent")
        action_box.grid(row=0, column=1, rowspan=2, sticky="e", padx=18, pady=18)
        for widget in actions:
            widget.pack(side="left", padx=5)
    return header


def stat_card(parent, colors, title, value, accent=None):
    accent = accent or colors["primary"]
    card = ctk.CTkFrame(parent, fg_color=colors["surface"], corner_radius=20, border_width=1, border_color=colors["surface_border"])
    ctk.CTkLabel(card, text=title, font=("Segoe UI", 12), text_color=colors["muted"]).pack(anchor="w", padx=16, pady=(14, 3))
    ctk.CTkLabel(card, text=value, font=("Segoe UI Semibold", 23), text_color=colors["text"]).pack(anchor="w", padx=16)
    ctk.CTkFrame(card, height=4, corner_radius=999, fg_color=accent).pack(fill="x", padx=16, pady=(12, 14))
    return card


def style_treeview(style, name, colors, rowheight=36):
    style.configure(name, rowheight=rowheight, font=("Segoe UI", 11), background=colors["surface"], fieldbackground=colors["surface"], foreground=colors["text"], bordercolor=colors["surface_border"])
    style.configure(f"{name}.Heading", font=("Segoe UI Semibold", 11), background=colors["secondary"], foreground=colors["secondary_text"], bordercolor=colors["surface_border"])
    style.map(name, background=[("selected", colors["secondary"])], foreground=[("selected", colors["secondary_text"])])
