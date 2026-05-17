import sys

import customtkinter as ctk

import database
from gamification.xp_system import XPSystem, build_semester_map
from ui.theme import apply_window_chrome, load_theme, palette
from ui.modern import make_app_shell


def resolve_username(raw_username):
    raw_username = (raw_username or "").strip()
    if raw_username and database.get_user_by_username(raw_username):
        return raw_username
    latest_user = database.get_latest_user()
    return latest_user["username"] if latest_user else raw_username or "Student"


class SemesterMapPage:
    def __init__(self, root, username):
        self.root = root
        self.username = username
        self.colors = palette()
        self.xp = XPSystem(username)
        self.root.title("Semester Survival Map | Schedly")
        self.root.configure(fg_color=self.colors["bg"])
        self._build()
        self.refresh()

    def _build(self):
        self.shell, self.nav_rail, self.content_area = make_app_shell(self.root, self.colors, active_label="Dashboard")
        self.outer = ctk.CTkFrame(self.content_area, fg_color="transparent", border_width=0, corner_radius=0)
        self.outer.grid(row=0, column=0, rowspan=2, sticky="nsew")

        header = ctk.CTkFrame(self.outer, fg_color=self.colors["surface"], border_color=self.colors["border"], border_width=1, corner_radius=22)
        header.pack(fill="x", padx=0, pady=(0, 14))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Gamified Semester Survival Map", font=("Segoe UI Semibold", 28), text_color=self.colors["text"]).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 4))
        ctk.CTkLabel(header, text="Subjects become missions, exams become boss fights, and completed work turns into XP.", font=("Segoe UI", 14), text_color=self.colors["muted"]).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 18))
        ctk.CTkButton(header, text="Refresh", height=42, width=110, corner_radius=14, fg_color=self.colors["primary"], hover_color=self.colors["primary_hover"], command=self.refresh).grid(row=0, column=1, padx=20, pady=18)
        ctk.CTkButton(header, text="Close", height=42, width=110, corner_radius=14, fg_color=self.colors["secondary"], hover_color=self.colors["secondary_hover"], text_color=self.colors["secondary_text"], command=self.root.destroy).grid(row=1, column=1, padx=20, pady=(0, 18))

        self.stats = ctk.CTkFrame(self.outer, fg_color="transparent")
        self.stats.pack(fill="x", padx=0, pady=(0, 14))
        self.stats.grid_columnconfigure((0, 1, 2), weight=1)
        self.level_value = self._stat_card("Level", 0)
        self.xp_value = self._stat_card("XP", 1)
        self.badge_value = self._stat_card("Badges", 2)

        body = ctk.CTkFrame(self.outer, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=0, pady=(0, 0))
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        map_panel = ctk.CTkFrame(body, fg_color=self.colors["surface"], border_color=self.colors["border"], border_width=1, corner_radius=22)
        map_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ctk.CTkLabel(map_panel, text="Semester Roadmap", font=("Segoe UI Semibold", 20), text_color=self.colors["text"]).pack(anchor="w", padx=18, pady=(16, 8))
        self.map_rows = ctk.CTkScrollableFrame(map_panel, fg_color="transparent")
        self.map_rows.pack(fill="both", expand=True, padx=14, pady=(0, 16))

        side = ctk.CTkFrame(body, fg_color="transparent")
        side.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        side.grid_rowconfigure(0, weight=1)
        side.grid_rowconfigure(1, weight=1)
        side.grid_columnconfigure(0, weight=1)

        badge_panel = ctk.CTkFrame(side, fg_color=self.colors["surface"], border_color=self.colors["border"], border_width=1, corner_radius=22)
        badge_panel.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        ctk.CTkLabel(badge_panel, text="Achievement Badges", font=("Segoe UI Semibold", 20), text_color=self.colors["text"]).pack(anchor="w", padx=18, pady=(16, 8))
        self.badge_rows = ctk.CTkScrollableFrame(badge_panel, fg_color="transparent")
        self.badge_rows.pack(fill="both", expand=True, padx=14, pady=(0, 16))

        xp_panel = ctk.CTkFrame(side, fg_color=self.colors["surface"], border_color=self.colors["border"], border_width=1, corner_radius=22)
        xp_panel.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        ctk.CTkLabel(xp_panel, text="Recent XP", font=("Segoe UI Semibold", 20), text_color=self.colors["text"]).pack(anchor="w", padx=18, pady=(16, 8))
        self.xp_rows = ctk.CTkScrollableFrame(xp_panel, fg_color="transparent")
        self.xp_rows.pack(fill="both", expand=True, padx=14, pady=(0, 16))

    def _stat_card(self, title, column):
        card = ctk.CTkFrame(self.stats, fg_color=self.colors["surface"], border_color=self.colors["border"], border_width=1, corner_radius=18)
        card.grid(row=0, column=column, sticky="ew", padx=6)
        ctk.CTkLabel(card, text=title, font=("Segoe UI", 13), text_color=self.colors["muted"]).pack(anchor="w", padx=16, pady=(14, 4))
        value = ctk.CTkLabel(card, text="-", font=("Segoe UI Semibold", 24), text_color=self.colors["text"])
        value.pack(anchor="w", padx=16, pady=(0, 14))
        return value

    def refresh(self):
        self.xp.refresh_achievements()
        profile = self.xp.profile()
        achievements = database.get_achievements(self.username)
        missions = build_semester_map(self.username)

        self.level_value.configure(text=f"Level {profile['level']}")
        self.xp_value.configure(text=f"{profile['total_xp']} XP")
        self.badge_value.configure(text=str(len(achievements)))

        for container in (self.map_rows, self.badge_rows, self.xp_rows):
            for child in container.winfo_children():
                child.destroy()

        if not missions:
            self._empty(self.map_rows, "Add tasks to generate subject missions.")
        for index, mission in enumerate(missions):
            state = "CLEARED" if mission["cleared"] else ("UNLOCKED" if mission["unlocked"] else "LOCKED")
            boss = f" | Boss fights: {mission['boss_fights']}" if mission["boss_fights"] else ""
            row = ctk.CTkFrame(self.map_rows, fg_color=self.colors["panel"], border_color=self.colors["border"], border_width=1, corner_radius=16)
            row.pack(fill="x", pady=7)
            ctk.CTkLabel(row, text=f"Mission {index + 1}: {mission['subject']}", font=("Segoe UI Semibold", 16), text_color=self.colors["text"]).pack(anchor="w", padx=14, pady=(10, 2))
            ctk.CTkLabel(row, text=f"{state} | {mission['completed']}/{mission['total']} tasks complete{boss}", font=("Segoe UI", 12), text_color=self.colors["muted"]).pack(anchor="w", padx=14)
            bar = ctk.CTkProgressBar(row, height=13, progress_color=self.colors["success"] if mission["cleared"] else self.colors["primary"], fg_color=self.colors["border"])
            bar.pack(fill="x", padx=14, pady=(8, 12))
            bar.set(mission["completion_percent"] / 100)

        if not achievements:
            self._empty(self.badge_rows, "Complete tasks or build a streak to unlock badges.")
        for badge in achievements:
            self._mini_row(self.badge_rows, badge["badge_name"], badge.get("description") or "Unlocked achievement")

        if not profile["recent_events"]:
            self._empty(self.xp_rows, "Complete tasks or log study sessions to earn XP.")
        for event in profile["recent_events"]:
            self._mini_row(self.xp_rows, f"+{event['points']} XP", event["reason"])

        level_bar = ctk.CTkProgressBar(self.stats, height=12, progress_color=self.colors["primary"], fg_color=self.colors["border"])
        level_bar.grid(row=1, column=0, columnspan=3, sticky="ew", padx=6, pady=(10, 0))
        level_bar.set(profile["level_progress"])

    def _mini_row(self, parent, title, subtitle):
        row = ctk.CTkFrame(parent, fg_color=self.colors["panel"], border_color=self.colors["border"], border_width=1, corner_radius=14)
        row.pack(fill="x", pady=6)
        ctk.CTkLabel(row, text=title, font=("Segoe UI Semibold", 14), text_color=self.colors["text"]).pack(anchor="w", padx=12, pady=(9, 2))
        ctk.CTkLabel(row, text=subtitle, font=("Segoe UI", 12), text_color=self.colors["muted"], wraplength=330, justify="left").pack(anchor="w", padx=12, pady=(0, 9))

    def _empty(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=("Segoe UI", 13), text_color=self.colors["muted"], wraplength=360, justify="left").pack(anchor="w", padx=12, pady=12)


if __name__ == "__main__":
    database.connect()
    ctk.set_appearance_mode(load_theme())
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    apply_window_chrome(root)
    SemesterMapPage(root, resolve_username(sys.argv[1] if len(sys.argv) > 1 else ""))
    root.mainloop()
