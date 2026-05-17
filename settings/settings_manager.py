import json
import os
import shutil
from datetime import datetime


CONFIG_FILE = "config.json"
LEGACY_THEME_FILE = "theme.txt"
DB_FILE = "users.db"

DEFAULT_SETTINGS = {
    "appearance_mode": "light",
    "theme_name": "green",
    "custom_accent": "#2f9e99",
    "notifications_enabled": True,
    "study_reminders_enabled": True,
    "sound_effects_enabled": True,
    "default_study_duration": 50,
    "font_size": 14,
    "auto_save_enabled": True,
}


class SettingsManager:
    """JSON-backed global settings store with legacy theme.txt compatibility."""

    def __init__(self, path=CONFIG_FILE):
        self.path = path
        self._cache = None

    def load(self):
        if self._cache is not None:
            return dict(self._cache)
        settings = dict(DEFAULT_SETTINGS)
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as file:
                    loaded = json.load(file)
                if isinstance(loaded, dict):
                    settings.update({key: loaded[key] for key in loaded if key in DEFAULT_SETTINGS})
        except (OSError, json.JSONDecodeError):
            pass

        legacy_mode = self._read_legacy_theme()
        if legacy_mode and not os.path.exists(self.path):
            settings["appearance_mode"] = legacy_mode

        self._cache = self._normalize(settings)
        self.save(self._cache)
        return dict(self._cache)

    def save(self, settings):
        normalized = self._normalize({**DEFAULT_SETTINGS, **settings})
        with open(self.path, "w", encoding="utf-8") as file:
            json.dump(normalized, file, indent=2)
        self._write_legacy_theme(normalized["appearance_mode"])
        self._cache = normalized
        return dict(normalized)

    def update(self, **changes):
        current = self.load()
        current.update(changes)
        return self.save(current)

    def reset(self):
        return self.save(DEFAULT_SETTINGS)

    def backup_database(self, destination_dir=None):
        if not os.path.exists(DB_FILE):
            return None
        destination_dir = destination_dir or os.getcwd()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = os.path.join(destination_dir, f"users_backup_{timestamp}.db")
        shutil.copy2(DB_FILE, destination)
        return destination

    def _normalize(self, settings):
        mode = str(settings.get("appearance_mode", "light")).lower()
        settings["appearance_mode"] = mode if mode in {"light", "dark"} else "light"
        theme_name = str(settings.get("theme_name", "green")).lower()
        settings["theme_name"] = theme_name if theme_name in {"green", "blue", "custom"} else "green"
        try:
            settings["default_study_duration"] = max(5, min(240, int(settings["default_study_duration"])))
        except (TypeError, ValueError):
            settings["default_study_duration"] = DEFAULT_SETTINGS["default_study_duration"]
        try:
            settings["font_size"] = max(11, min(20, int(settings["font_size"])))
        except (TypeError, ValueError):
            settings["font_size"] = DEFAULT_SETTINGS["font_size"]
        for key in ["notifications_enabled", "study_reminders_enabled", "sound_effects_enabled", "auto_save_enabled"]:
            settings[key] = bool(settings.get(key))
        accent = str(settings.get("custom_accent") or DEFAULT_SETTINGS["custom_accent"]).strip()
        settings["custom_accent"] = accent if accent.startswith("#") and len(accent) in {4, 7} else DEFAULT_SETTINGS["custom_accent"]
        return settings

    def _read_legacy_theme(self):
        try:
            if os.path.exists(LEGACY_THEME_FILE):
                with open(LEGACY_THEME_FILE, "r", encoding="utf-8") as file:
                    value = file.read().strip().lower()
                return value if value in {"light", "dark"} else None
        except OSError:
            return None
        return None

    def _write_legacy_theme(self, mode):
        try:
            with open(LEGACY_THEME_FILE, "w", encoding="utf-8") as file:
                file.write(mode)
        except OSError:
            pass


settings_manager = SettingsManager()
