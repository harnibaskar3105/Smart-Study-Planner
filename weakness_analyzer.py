if __name__ == "__main__":
    import sys
    from single_window_app import run
    run(initial_page="analytics", username=sys.argv[1] if len(sys.argv) > 1 else "")
    raise SystemExit

import sys
from tkinter import messagebox, ttk

import customtkinter as ctk

import database
from analytics.weakness_analyzer import WeaknessAnalyzer
from gamification.xp_system import XPSystem
from ui.theme import apply_window_chrome, load_theme, palette
from ui.modern import make_app_shell, style_treeview


def resolve_username(raw_username):
    raw_username = (raw_username or "").strip()
    if raw_username and database.get_user_by_username(raw_username):
        return raw_username
    latest_user = database.get_latest_user()
    return latest_user["username"] if latest_user else raw_username or "Student"


class WeaknessAnalyzerPage:
    def __init__(self, root, username):
        self.root = root
        self.username = username
        self.colors = palette()
        self.analyzer = WeaknessAnalyzer(username)
        self.root.title("Weakness Analyzer | Schedly")
        self.root.configure(fg_color=self.colors["bg"])
        self._build()
        self.refresh()

    def _build(self):
        self.shell, self.nav_rail, self.content_area = make_app_shell(self.root, self.colors, active_label="Analytics")
        self.outer = ctk.CTkFrame(self.content_area, corner_radius=0, border_width=0, fg_color="transparent")
        self.outer.grid(row=0, column=0, rowspan=2, sticky="nsew")

        header = ctk.CTkFrame(self.outer, fg_color=self.colors["surface"], border_color=self.colors["border"], border_width=1, corner_radius=22)
        header.pack(fill="x", padx=0, pady=(0, 14))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Smart Weakness Analyzer", font=("Segoe UI Semibold", 28), text_color=self.colors["text"]).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 4))
        ctk.CTkLabel(header, text="Track understanding, weak topics, skipped work, and revision recommendations.", font=("Segoe UI", 14), text_color=self.colors["muted"]).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 18))
        ctk.CTkButton(header, text="Seed Sample Data", width=150, height=42, corner_radius=14, fg_color=self.colors["secondary"], hover_color=self.colors["secondary_hover"], text_color=self.colors["secondary_text"], command=self.seed_data).grid(row=0, column=1, padx=20, pady=18)
        ctk.CTkButton(header, text="Close", width=100, height=42, corner_radius=14, fg_color=self.colors["primary"], hover_color=self.colors["primary_hover"], command=self.root.destroy).grid(row=1, column=1, padx=20, pady=(0, 18))

        form = ctk.CTkFrame(self.outer, fg_color=self.colors["surface"], border_color=self.colors["border"], border_width=1, corner_radius=22)
        form.pack(fill="x", padx=0, pady=(0, 14))
        for index in range(6):
            form.grid_columnconfigure(index, weight=1)
        self.subject_entry = self._entry(form, "Subject", 0)
        self.topic_entry = self._entry(form, "Topic", 1)
        self.duration_entry = self._entry(form, "Minutes", 2)
        self.rating_var = ctk.StringVar(value="3")
        self.status_var = ctk.StringVar(value="completed")
        ctk.CTkLabel(form, text="Rating", text_color=self.colors["text"], font=("Segoe UI Semibold", 12)).grid(row=0, column=3, sticky="w", padx=10, pady=(14, 4))
        ctk.CTkOptionMenu(form, values=["1", "2", "3", "4", "5"], variable=self.rating_var, height=38, fg_color=self.colors["panel"], button_color=self.colors["primary"], button_hover_color=self.colors["primary_hover"], text_color=self.colors["text"]).grid(row=1, column=3, sticky="ew", padx=10, pady=(0, 14))
        ctk.CTkLabel(form, text="Status", text_color=self.colors["text"], font=("Segoe UI Semibold", 12)).grid(row=0, column=4, sticky="w", padx=10, pady=(14, 4))
        ctk.CTkOptionMenu(form, values=["completed", "partial", "skipped", "postponed"], variable=self.status_var, height=38, fg_color=self.colors["panel"], button_color=self.colors["primary"], button_hover_color=self.colors["primary_hover"], text_color=self.colors["text"]).grid(row=1, column=4, sticky="ew", padx=10, pady=(0, 14))
        ctk.CTkButton(form, text="Log Session", height=38, corner_radius=14, fg_color=self.colors["primary"], hover_color=self.colors["primary_hover"], command=self.log_session).grid(row=1, column=5, sticky="ew", padx=10, pady=(0, 14))

        stats = ctk.CTkFrame(self.outer, fg_color="transparent")
        stats.pack(fill="x", padx=0, pady=(0, 14))
        stats.grid_columnconfigure((0, 1, 2), weight=1)
        self.weakest_card = self._metric_card(stats, "Weakest Subject", 0)
        self.avoided_card = self._metric_card(stats, "Most Avoided Topic", 1)
        self.trend_card = self._metric_card(stats, "Improvement Trend", 2)

        body = ctk.CTkFrame(self.outer, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=0, pady=(0, 0))
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        summary_panel = ctk.CTkFrame(body, fg_color=self.colors["surface"], border_color=self.colors["border"], border_width=1, corner_radius=22)
        summary_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ctk.CTkLabel(summary_panel, text="Subject Performance", font=("Segoe UI Semibold", 20), text_color=self.colors["text"]).pack(anchor="w", padx=18, pady=(16, 8))
        self.subject_rows = ctk.CTkScrollableFrame(summary_panel, fg_color="transparent")
        self.subject_rows.pack(fill="both", expand=True, padx=14, pady=(0, 16))

        rec_panel = ctk.CTkFrame(body, fg_color=self.colors["surface"], border_color=self.colors["border"], border_width=1, corner_radius=22)
        rec_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        ctk.CTkLabel(rec_panel, text="Recommended Revision", font=("Segoe UI Semibold", 20), text_color=self.colors["text"]).pack(anchor="w", padx=18, pady=(16, 8))
        self.recommendation_box = ctk.CTkTextbox(rec_panel, wrap="word", fg_color=self.colors["panel"], border_color=self.colors["border"], border_width=1, text_color=self.colors["text"], height=190)
        self.recommendation_box.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkLabel(rec_panel, text="Weak Topic Priority", font=("Segoe UI Semibold", 16), text_color=self.colors["text"]).pack(anchor="w", padx=18, pady=(0, 8))
        self.topic_tree = ttk.Treeview(rec_panel, columns=("subject", "topic", "rating", "avoids", "score"), show="headings", height=8)
        for key, label, width in [("subject", "Subject", 95), ("topic", "Topic", 130), ("rating", "Rating", 65), ("avoids", "Avoids", 65), ("score", "Score", 65)]:
            self.topic_tree.heading(key, text=label)
            self.topic_tree.column(key, width=width, anchor="w")
        self.topic_tree.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        style = ttk.Style()
        style.theme_use("default")
        style_treeview(style, "Treeview", self.colors)

    def _entry(self, parent, label, column):
        ctk.CTkLabel(parent, text=label, text_color=self.colors["text"], font=("Segoe UI Semibold", 12)).grid(row=0, column=column, sticky="w", padx=10, pady=(14, 4))
        entry = ctk.CTkEntry(parent, height=38, fg_color=self.colors["panel"], border_color=self.colors["border"], text_color=self.colors["text"])
        entry.grid(row=1, column=column, sticky="ew", padx=10, pady=(0, 14))
        return entry

    def _metric_card(self, parent, title, column):
        card = ctk.CTkFrame(parent, fg_color=self.colors["surface"], border_color=self.colors["border"], border_width=1, corner_radius=18)
        card.grid(row=0, column=column, sticky="ew", padx=6)
        ctk.CTkLabel(card, text=title, font=("Segoe UI", 13), text_color=self.colors["muted"]).pack(anchor="w", padx=16, pady=(14, 4))
        value = ctk.CTkLabel(card, text="-", font=("Segoe UI Semibold", 20), text_color=self.colors["text"], wraplength=300, justify="left")
        value.pack(anchor="w", padx=16, pady=(0, 14))
        return value

    def log_session(self):
        subject = self.subject_entry.get().strip()
        topic = self.topic_entry.get().strip()
        try:
            minutes = int(self.duration_entry.get().strip())
            rating = int(self.rating_var.get())
        except ValueError:
            messagebox.showerror("Invalid Session", "Minutes and rating must be numbers.")
            return
        if not subject or not topic or minutes <= 0:
            messagebox.showerror("Invalid Session", "Add a subject, topic, and positive duration.")
            return
        database.log_study_session(self.username, minutes, subject=subject, topic=topic, understanding_rating=rating, completion_status=self.status_var.get())
        XPSystem(self.username).award_study_session(minutes)
        self.refresh()
        self.subject_entry.delete(0, "end")
        self.topic_entry.delete(0, "end")
        self.duration_entry.delete(0, "end")

    def seed_data(self):
        added = database.seed_sample_study_data(self.username)
        messagebox.showinfo("Sample Data", "Sample study data added." if added else "Existing data found, so sample data was not duplicated.")
        self.refresh()

    def refresh(self):
        data = self.analyzer.analyze()
        self.weakest_card.configure(text=data["weakest_subject"])
        self.avoided_card.configure(text=data["most_avoided_topic"])
        self.trend_card.configure(text=data["improvement_trend"])
        self.recommendation_box.configure(state="normal")
        self.recommendation_box.delete("1.0", "end")
        self.recommendation_box.insert("end", "\n\n".join(data["recommended_tasks"]))
        self.recommendation_box.configure(state="disabled")

        for child in self.subject_rows.winfo_children():
            child.destroy()
        for subject in data["subject_performance"]:
            row = ctk.CTkFrame(self.subject_rows, fg_color=self.colors["panel"], border_color=self.colors["border"], border_width=1, corner_radius=14)
            row.pack(fill="x", pady=6)
            ctk.CTkLabel(row, text=subject["subject"], font=("Segoe UI Semibold", 15), text_color=self.colors["text"]).pack(anchor="w", padx=14, pady=(10, 2))
            meta = f"Rating {subject['average_rating']}/5 | Weak sessions {subject['weak_sessions']} | Study {subject['study_minutes']} min | Tasks {subject['completed_tasks']}/{subject['total_tasks']}"
            ctk.CTkLabel(row, text=meta, font=("Segoe UI", 12), text_color=self.colors["muted"]).pack(anchor="w", padx=14)
            bar = ctk.CTkProgressBar(row, height=12, progress_color=self.colors["primary"], fg_color=self.colors["border"])
            bar.pack(fill="x", padx=14, pady=(8, 12))
            bar.set(subject["completion_rate"] / 100 if subject["completion_rate"] else 0)

        for item in self.topic_tree.get_children():
            self.topic_tree.delete(item)
        for topic in data["weak_topics"][:12]:
            self.topic_tree.insert("", "end", values=(topic["subject"], topic["topic"], topic["average_rating"], topic["avoid_count"], topic["priority_score"]))


if __name__ == "__main__":
    database.connect()
    ctk.set_appearance_mode(load_theme())
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    apply_window_chrome(root)
    WeaknessAnalyzerPage(root, resolve_username(sys.argv[1] if len(sys.argv) > 1 else ""))
    root.mainloop()
