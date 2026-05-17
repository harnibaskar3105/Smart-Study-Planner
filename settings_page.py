if __name__ == "__main__":
    import sys
    from single_window_app import run
    run(initial_page="settings", username=sys.argv[1] if len(sys.argv) > 1 else "")
    raise SystemExit

import sys
import shutil
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

import database
from dashboard_model import WEEKDAY_NAMES, load_dashboard_snapshot
from settings.settings_manager import settings_manager
from theme_manager import apply_theme, get_fonts, get_theme_colors, load_theme, start_theme_monitor
from ui.theme import apply_window_chrome
from ui.modern import make_app_shell

INSTRUCTIONS_PDF = Path(__file__).resolve().parent / "instructions.pdf"


def resolve_username(raw_username):
    raw_username = (raw_username or "").strip()
    if raw_username and database.get_user_by_username(raw_username):
        return raw_username
    latest_user = database.get_latest_user()
    return latest_user["username"] if latest_user else raw_username or "Student"


class SettingsPage:
    def __init__(self, root, username):
        self.root = root
        self.username = username
        self.settings = settings_manager.load()
        self.attendance = load_dashboard_snapshot(username).attendance
        self.colors = get_theme_colors(self.settings)
        self.fonts = get_fonts(self.settings)
        self.root.title("Settings | Schedly")
        self.root.configure(fg_color=self.colors["bg"])
        self._build()
        start_theme_monitor(self.root, on_change=lambda _settings: self.refresh_theme())

    def _build(self):
        self.shell, self.nav_rail, self.content_area = make_app_shell(self.root, self.colors, active_label="Settings")
        self.outer = ctk.CTkFrame(self.content_area, corner_radius=0, border_width=0, fg_color="transparent")
        self.outer.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.outer.grid_columnconfigure(0, weight=1)
        self.outer.grid_rowconfigure(1, weight=1)
        self.input_labels = []
        self.entries = []
        self.option_menus = []
        self.switches = []
        self.panel_subtitles = []

        header = ctk.CTkFrame(self.outer, corner_radius=24, border_width=1)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.grid_columnconfigure(0, weight=1)
        self.header = header
        self.title = ctk.CTkLabel(header, text="Settings Hub", font=self.fonts["title"])
        self.title.grid(row=0, column=0, sticky="w", padx=22, pady=(18, 4))
        self.subtitle = ctk.CTkLabel(
            header,
            text="Tune appearance, reminders, attendance rules, backups, and progress state from one clean control center.",
            font=self.fonts["body"],
            wraplength=780,
            justify="left",
        )
        self.subtitle.grid(row=1, column=0, sticky="w", padx=22, pady=(0, 18))
        self.close_btn = ctk.CTkButton(header, text="Close", width=120, height=44, corner_radius=16, command=self.root.destroy)
        self.close_btn.grid(row=0, column=1, rowspan=2, padx=22)

        self.body = ctk.CTkScrollableFrame(
            self.outer,
            fg_color="transparent",
            border_width=0,
            corner_radius=0,
            scrollbar_button_color=self.colors["deep"],
            scrollbar_button_hover_color=self.colors["deep_hover"],
            scrollbar_fg_color=self.colors["panel"],
        )
        self.body.grid(row=1, column=0, sticky="nsew")
        self.body.grid_columnconfigure((0, 1), weight=1, uniform="settings_columns")

        self.appearance_panel = self._panel(self.body, "Theme Manager", "Keep the app visually aligned with your study style.", 0, 0)
        self.behavior_panel = self._panel(self.body, "Study Behavior", "Control reminders, defaults, and weekly leave rules.", 0, 1)
        self.data_panel = self._panel(self.body, "Data & Maintenance", "Export data or reset local settings when needed.", 1, 0, columnspan=2)

        self.mode_var = ctk.StringVar(value=self.settings["appearance_mode"])
        self.theme_var = ctk.StringVar(value=self.settings["theme_name"])
        self.accent_var = ctk.StringVar(value=self.settings["custom_accent"])
        self._option(self.appearance_panel, "Appearance mode", ["light", "dark"], self.mode_var, self.save_theme)
        self._option(self.appearance_panel, "Accent theme", ["green", "blue", "custom"], self.theme_var, self.save_theme)
        self.custom_accent_label, self.custom_accent_entry = self._labeled_entry(self.appearance_panel, "Custom accent hex", self.accent_var)
        self.apply_theme_btn = ctk.CTkButton(self.appearance_panel, text="Apply Theme", height=44, corner_radius=16, command=self.save_theme)
        self.apply_theme_btn.pack(fill="x", padx=18, pady=(6, 18))

        self.notifications_var = ctk.BooleanVar(value=self.settings["notifications_enabled"])
        self.reminders_var = ctk.BooleanVar(value=self.settings["study_reminders_enabled"])
        self.sound_var = ctk.BooleanVar(value=self.settings["sound_effects_enabled"])
        self.autosave_var = ctk.BooleanVar(value=self.settings["auto_save_enabled"])
        self.duration_var = ctk.StringVar(value=str(self.settings["default_study_duration"]))
        self.font_size_var = ctk.StringVar(value=str(self.settings["font_size"]))
        self.leave_var = ctk.StringVar(value=self.attendance["leave_day_name"])

        for text, variable in [
            ("Notifications", self.notifications_var),
            ("Study reminders", self.reminders_var),
            ("Sound effects", self.sound_var),
            ("Auto-save", self.autosave_var),
        ]:
            switch = ctk.CTkSwitch(self.behavior_panel, text=text, variable=variable, command=self.save_behavior, height=28)
            switch.pack(anchor="w", padx=18, pady=7)
            self.switches.append(switch)
        self.duration_label, self.duration_entry = self._labeled_entry(self.behavior_panel, "Default study duration", self.duration_var)
        self.font_size_label, self.font_size_entry = self._labeled_entry(self.behavior_panel, "Font size", self.font_size_var)
        self.leave_menu = self._option(self.behavior_panel, "Weekly leave / holiday", WEEKDAY_NAMES, self.leave_var, self.save_attendance)
        self.attendance_note = ctk.CTkLabel(self.behavior_panel, text="", font=self.fonts["small"], wraplength=360, justify="left")
        self.attendance_note.pack(anchor="w", padx=18, pady=(0, 12))
        self.save_behavior_btn = ctk.CTkButton(self.behavior_panel, text="Save Behavior", height=44, corner_radius=16, command=self.save_behavior)
        self.save_behavior_btn.pack(fill="x", padx=18, pady=(6, 18))

        row = ctk.CTkFrame(self.data_panel, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(8, 16))
        row.grid_columnconfigure((0, 1, 2), weight=1)
        self.backup_btn = ctk.CTkButton(row, text="Backup / Export Data", height=46, corner_radius=16, command=self.backup_data)
        self.backup_btn.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.reset_settings_btn = ctk.CTkButton(row, text="Reset Settings", height=46, corner_radius=16, command=self.reset_settings)
        self.reset_settings_btn.grid(row=0, column=1, sticky="ew", padx=8)
        self.reset_progress_btn = ctk.CTkButton(row, text="Reset Progress", height=46, corner_radius=16, command=self.reset_progress)
        self.reset_progress_btn.grid(row=0, column=2, sticky="ew", padx=(8, 0))
        self.instructions_btn = ctk.CTkButton(row, text="Instructions", height=46, corner_radius=16, command=self.download_instructions)
        self.instructions_btn.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(12, 0))

        self.status_label = ctk.CTkLabel(self.data_panel, text="Settings are saved automatically to config.json.", font=self.fonts["body"])
        self.status_label.pack(anchor="w", padx=18, pady=(0, 18))
        self.refresh_theme()

    def _panel(self, parent, title, subtitle, row, column, columnspan=1):
        panel = ctk.CTkFrame(parent, corner_radius=22, border_width=1)
        panel.grid(row=row, column=column, columnspan=columnspan, sticky="nsew", padx=8, pady=8)
        label = ctk.CTkLabel(panel, text=title, font=self.fonts["section"])
        label.pack(anchor="w", padx=18, pady=(18, 4))
        subtitle_label = ctk.CTkLabel(panel, text=subtitle, font=self.fonts["small"], wraplength=520, justify="left")
        subtitle_label.pack(anchor="w", padx=18, pady=(0, 14))
        panel.title_label = label
        panel.subtitle_label = subtitle_label
        self.panel_subtitles.append(subtitle_label)
        return panel

    def _option(self, parent, label, values, variable, command):
        label_widget = ctk.CTkLabel(parent, text=label, font=self.fonts["body_semibold"])
        label_widget.pack(anchor="w", padx=18, pady=(4, 6))
        self.input_labels.append(label_widget)
        menu = ctk.CTkOptionMenu(
            parent,
            values=values,
            variable=variable,
            command=lambda _value: command(),
            height=44,
            corner_radius=16,
            fg_color=self.colors["entry"],
            button_color=self.colors["primary"],
            button_hover_color=self.colors["primary_hover"],
            text_color=self.colors["text"],
            dropdown_fg_color=self.colors["panel"],
            dropdown_hover_color=self.colors["surface"],
            dropdown_text_color=self.colors["text"],
        )
        menu.pack(fill="x", padx=18, pady=(0, 14))
        self.option_menus.append(menu)
        return menu

    def _labeled_entry(self, parent, label, variable):
        label_widget = ctk.CTkLabel(parent, text=label, font=self.fonts["body_semibold"])
        label_widget.pack(anchor="w", padx=18, pady=(4, 6))
        self.input_labels.append(label_widget)
        entry = ctk.CTkEntry(
            parent,
            textvariable=variable,
            height=44,
            corner_radius=16,
            fg_color=self.colors["entry"],
            border_color=self.colors["entry_border"],
            text_color=self.colors["text"],
        )
        entry.pack(fill="x", padx=18, pady=(0, 14))
        self.entries.append(entry)
        return label_widget, entry

    def save_theme(self):
        apply_theme(self.mode_var.get(), self.theme_var.get(), self.accent_var.get() if self.theme_var.get() == "custom" else None)
        self.settings = settings_manager.load()
        self.refresh_theme()
        self.status_label.configure(text="Theme saved and applied globally.")

    def save_behavior(self):
        try:
            duration = int(self.duration_var.get())
            font_size = int(self.font_size_var.get())
        except ValueError:
            messagebox.showerror("Invalid Settings", "Duration and font size must be whole numbers.")
            return
        self.settings = settings_manager.update(
            notifications_enabled=self.notifications_var.get(),
            study_reminders_enabled=self.reminders_var.get(),
            sound_effects_enabled=self.sound_var.get(),
            auto_save_enabled=self.autosave_var.get(),
            default_study_duration=duration,
            font_size=font_size,
        )
        self.refresh_theme()
        self.status_label.configure(text="Behavior settings saved.")

    def save_attendance(self):
        self.attendance = load_dashboard_snapshot(self.username).attendance
        if not self.attendance.get("leave_enabled", True):
            self.leave_var.set(self.attendance["leave_day_name"])
            self.status_label.configure(text="Weekly holiday is locked until attendance reaches 75%.")
            self.refresh_theme()
            return
        database.update_attendance_leave_day(self.username, WEEKDAY_NAMES.index(self.leave_var.get()))
        self.attendance = load_dashboard_snapshot(self.username).attendance
        self.status_label.configure(text=f"Weekly holiday set to {self.leave_var.get()}.")
        self.refresh_theme()

    def backup_data(self):
        directory = filedialog.askdirectory(title="Choose backup folder")
        if not directory:
            return
        backup_path = settings_manager.backup_database(directory)
        self.status_label.configure(text=f"Backup created: {backup_path}" if backup_path else "No database file found to back up.")

    def download_instructions(self):
        if not INSTRUCTIONS_PDF.exists():
            messagebox.showerror("Instructions Missing", "The instructions PDF could not be found.")
            return
        destination = filedialog.asksaveasfilename(
            title="Download Instructions",
            defaultextension=".pdf",
            initialfile="instructions.pdf",
            filetypes=[("PDF files", "*.pdf")],
        )
        if not destination:
            return
        try:
            shutil.copyfile(INSTRUCTIONS_PDF, destination)
        except OSError as error:
            messagebox.showerror("Download Failed", f"Could not save instructions PDF:\n{error}")
            return
        self.status_label.configure(text=f"Instructions downloaded: {destination}")

    def reset_settings(self):
        if not messagebox.askyesno("Reset Settings", "Reset app settings to defaults?"):
            return
        self.settings = settings_manager.reset()
        self.mode_var.set(self.settings["appearance_mode"])
        self.theme_var.set(self.settings["theme_name"])
        self.accent_var.set(self.settings["custom_accent"])
        self.refresh_theme()

    def reset_progress(self):
        if not messagebox.askyesno("Reset Progress", "Clear study sessions, XP, badges, and completion progress?"):
            return
        database.reset_user_progress(self.username)
        self.status_label.configure(text="Progress reset for this user.")

    def refresh_theme(self):
        self.settings = settings_manager.load()
        self.attendance = load_dashboard_snapshot(self.username).attendance
        self.colors = get_theme_colors(self.settings)
        self.fonts = get_fonts(self.settings)
        self.root.configure(fg_color=self.colors["bg"])
        self.shell.configure(fg_color=self.colors["panel"], border_color=self.colors["panel_border"])
        self.nav_rail.configure(fg_color=self.colors["sidebar"], border_color=self.colors["sidebar_border"])
        self.body.configure(
            fg_color="transparent",
            scrollbar_button_color=self.colors["deep"],
            scrollbar_button_hover_color=self.colors["deep_hover"],
            scrollbar_fg_color=self.colors["panel"],
        )
        self.header.configure(fg_color=self.colors["surface"], border_color=self.colors["surface_border"])
        self.update_custom_accent_visibility()
        for frame in [self.outer, self.appearance_panel, self.behavior_panel, self.data_panel]:
            if frame is self.outer:
                frame.configure(fg_color="transparent")
            else:
                frame.configure(fg_color=self.colors["surface"], border_color=self.colors["surface_border"])
        for label in [self.title, self.subtitle, self.appearance_panel.title_label, self.behavior_panel.title_label, self.data_panel.title_label, self.status_label, self.attendance_note, *self.input_labels, *self.panel_subtitles]:
            label.configure(text_color=self.colors["text"], font=self.fonts["section"] if label in [self.appearance_panel.title_label, self.behavior_panel.title_label, self.data_panel.title_label] else self.fonts["body"])
        self.title.configure(font=self.fonts["title"])
        self.subtitle.configure(text_color=self.colors["muted"])
        for subtitle in self.panel_subtitles:
            subtitle.configure(text_color=self.colors["muted"], font=self.fonts["small"])
        for entry in self.entries:
            entry.configure(fg_color=self.colors["entry"], border_color=self.colors["entry_border"], text_color=self.colors["text"], placeholder_text_color=self.colors["muted"])
        for menu in self.option_menus:
            menu.configure(
                fg_color=self.colors["entry"],
                button_color=self.colors["primary"],
                button_hover_color=self.colors["primary_hover"],
                text_color=self.colors["text"],
                dropdown_fg_color=self.colors["panel"],
                dropdown_hover_color=self.colors["surface"],
                dropdown_text_color=self.colors["text"],
            )
        for switch in self.switches:
            switch.configure(
                text_color=self.colors["text"],
                progress_color=self.colors["primary"],
                button_color=self.colors["entry"],
                button_hover_color=self.colors["card_light"],
                fg_color=self.colors["secondary"],
            )
        self.attendance_note.configure(
            text=(
                f"Current attendance: {self.attendance['percentage']}%. Holiday changes unlock at 75%."
                if not self.attendance.get("leave_enabled", True)
                else f"Current attendance: {self.attendance['percentage']}%. Holiday locks below 75%."
            ),
            text_color=self.colors["danger"] if not self.attendance.get("leave_enabled", True) else self.colors["muted"],
            font=self.fonts["small"],
        )
        self.leave_var.set(self.attendance["leave_day_name"])
        self.leave_menu.configure(
            state="normal" if self.attendance.get("leave_enabled", True) else "disabled",
            fg_color=self.colors["entry"],
            button_color=self.colors["primary"],
            button_hover_color=self.colors["primary_hover"],
            text_color=self.colors["text"],
            dropdown_fg_color=self.colors["panel"],
            dropdown_hover_color=self.colors["surface"],
            dropdown_text_color=self.colors["text"],
        )
        for button in [self.close_btn, self.backup_btn, self.instructions_btn, self.apply_theme_btn, self.save_behavior_btn]:
            button.configure(fg_color=self.colors["primary"], hover_color=self.colors["primary_hover"], text_color="#ffffff")
        for button in [self.reset_settings_btn]:
            button.configure(fg_color=self.colors["secondary"], hover_color=self.colors["secondary_hover"], text_color=self.colors["secondary_text"])
        self.reset_progress_btn.configure(fg_color=self.colors["danger"], hover_color=self.colors["danger_hover"], text_color="#ffffff")

    def update_custom_accent_visibility(self):
        is_custom = self.theme_var.get() == "custom"
        if is_custom:
            if not self.custom_accent_label.winfo_ismapped():
                self.custom_accent_label.pack(anchor="w", padx=18, pady=(4, 6), before=self.apply_theme_btn)
                self.custom_accent_entry.pack(fill="x", padx=18, pady=(0, 14), before=self.apply_theme_btn)
            return
        self.custom_accent_label.pack_forget()
        self.custom_accent_entry.pack_forget()


if __name__ == "__main__":
    database.connect()
    ctk.set_appearance_mode(load_theme())
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    apply_window_chrome(root)
    SettingsPage(root, resolve_username(sys.argv[1] if len(sys.argv) > 1 else ""))
    root.mainloop()
