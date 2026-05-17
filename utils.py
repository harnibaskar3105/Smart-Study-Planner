"""
Optimized utility module for StudyPlanner
Provides caching, threading, and performance improvements
"""
import threading
import subprocess
import sys
import os
from functools import lru_cache
from PIL import Image, UnidentifiedImageError
import customtkinter as ctk


# ========== THEME COLORS ==========
LIGHT = {
    "bg": "#f7f2fb",
    "bg_soft": "#efe4f7",
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
    "badge_bg": "#ebe0f7",
    "badge_text": "#765b99",
    "link": "#4ca8a0",
    "link_hover": "#3c9189",
    "entry": "#fcf9ff",
    "entry_border": "#d8cde5",
    "header": "#f7f1fb",
    "header_border": "#dfd4ea",
    "sidebar": "#f8f2fb",
    "sidebar_border": "#dfd4ea",
    "sidebar_hover": "#efe4f7",
    "tile": "#fcf9ff",
    "tile_hover": "#f3ecfa",
    "danger": "#d98da8",
    "danger_hover": "#c77394",
    "success": "#73c8bf",
}

DARK = {
    "bg": "#161120",
    "bg_soft": "#221a31",
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
    "badge_bg": "#3a2b50",
    "badge_text": "#d7c6ef",
    "link": "#9be1da",
    "link_hover": "#b6ece7",
    "entry": "#251c36",
    "entry_border": "#4a3b61",
    "header": "#1c152b",
    "header_border": "#342946",
    "sidebar": "#1d1830",
    "sidebar_border": "#342946",
    "sidebar_hover": "#332745",
    "tile": "#2a203c",
    "tile_hover": "#37294b",
    "danger": "#a86f86",
    "danger_hover": "#965f76",
    "success": "#8fded4",
}

THEME_FILE = "theme.txt"
_image_cache = {}
_current_theme = None


# ========== THEME UTILITIES ==========
def load_theme():
    """Load theme from file (cached)"""
    global _current_theme
    if _current_theme is not None:
        return _current_theme
    if os.path.exists(THEME_FILE):
        with open(THEME_FILE, "r", encoding="utf-8") as f:
            _current_theme = f.read().strip() or "light"
    else:
        _current_theme = "light"
    return _current_theme


def save_theme(theme):
    """Save theme to file"""
    global _current_theme
    _current_theme = theme
    with open(THEME_FILE, "w", encoding="utf-8") as f:
        f.write(theme)


def palette(theme=None):
    """Get color palette for theme"""
    if theme is None:
        theme = load_theme()
    return LIGHT if theme == "light" else DARK


def get_theme_aware_fg_color(light_color, dark_color):
    """Get color based on current theme"""
    return light_color if load_theme() == "light" else dark_color


# ========== IMAGE CACHING ==========
@lru_cache(maxsize=32)
def load_image(path, size=(22, 22)):
    """Load and cache image (with error handling)"""
    try:
        img = ctk.CTkImage(Image.open(path), size=size)
        return img
    except (FileNotFoundError, UnidentifiedImageError, OSError):
        return create_placeholder(size)


def create_placeholder(size=(22, 22)):
    """Create transparent placeholder image"""
    try:
        return ctk.CTkImage(Image.new("RGBA", size, (0, 0, 0, 0)), size=size)
    except Exception:
        return None


# ========== THREADING UTILITIES ==========
class ThreadedTask:
    """Wrapper for running tasks in background threads"""

    def __init__(self, target, args=(), kwargs=None, on_complete=None, on_error=None):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}
        self.on_complete = on_complete
        self.on_error = on_error
        self.result = None
        self.error = None
        self.thread = None

    def run_async(self):
        """Run task in background thread"""
        self.thread = threading.Thread(target=self._execute, daemon=True)
        self.thread.start()
        return self

    def _execute(self):
        """Execute task and handle callbacks"""
        try:
            self.result = self.target(*self.args, **self.kwargs)
            if self.on_complete:
                self.on_complete(self.result)
        except Exception as e:
            self.error = e
            if self.on_error:
                self.on_error(e)

    def wait(self, timeout=None):
        """Wait for thread to complete"""
        if self.thread:
            self.thread.join(timeout)
        return self.result


def run_async(target, args=(), kwargs=None, on_complete=None, on_error=None):
    """Convenience function to run task asynchronously"""
    task = ThreadedTask(target, args, kwargs, on_complete, on_error)
    return task.run_async()


# ========== SUBPROCESS UTILITIES ==========
def run_subprocess_async(script_name, args=None, on_complete=None, on_error=None):
    """Run subprocess non-blocking in background"""
    def _run():
        try:
            cmd = [sys.executable, script_name]
            if args:
                cmd.extend(args if isinstance(args, list) else [args])
            subprocess.Popen(cmd)
            return True
        except Exception as e:
            if on_error:
                on_error(e)
            return False

    task = ThreadedTask(_run, on_complete=on_complete, on_error=on_error)
    task.run_async()


# ========== WINDOW UTILITIES ==========
def maximize_window(window):
    """Maximize window efficiently"""
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
    """Show window with fade effect"""
    maximize_window(window)
    try:
        window.attributes("-alpha", 1.0)
    except Exception:
        pass


def set_window_invisible(window):
    """Hide window initially"""
    try:
        window.attributes("-alpha", 0.0)
    except Exception:
        pass


# ========== DATA CACHE ==========
class DataCache:
    """Simple thread-safe cache for frequently accessed data"""

    def __init__(self, ttl=300):
        self.cache = {}
        self.ttl = ttl
        self.timestamps = {}
        self.lock = threading.Lock()

    def get(self, key):
        """Get cached value if not expired"""
        with self.lock:
            if key in self.cache:
                import time
                if time.time() - self.timestamps[key] < self.ttl:
                    return self.cache[key]
                else:
                    del self.cache[key]
                    del self.timestamps[key]
        return None

    def set(self, key, value):
        """Store value in cache"""
        import time
        with self.lock:
            self.cache[key] = value
            self.timestamps[key] = time.time()

    def clear(self):
        """Clear all cache"""
        with self.lock:
            self.cache.clear()
            self.timestamps.clear()


# Initialize global cache
data_cache = DataCache(ttl=300)


# ========== STYLE HELPERS ==========
def style_entry(entry, colors):
    """Apply theme colors to entry widget"""
    entry.configure(
        fg_color=colors.get("entry", "#ffffff"),
        border_color=colors.get("entry_border", "#cccccc"),
        text_color=colors.get("text", "#000000"),
        placeholder_text_color=colors.get("muted", "#999999"),
    )


def style_button(button, colors, is_primary=True):
    """Apply theme colors to button widget"""
    if is_primary:
        button.configure(
            fg_color=colors.get("primary", "#4a7d7c"),
            hover_color=colors.get("primary_hover", "#3a6d6c"),
            text_color="#ffffff",
        )
    else:
        button.configure(
            fg_color=colors.get("secondary", "#e0e0e0"),
            hover_color=colors.get("secondary_hover", "#d0d0d0"),
            text_color=colors.get("secondary_text", "#333333"),
        )
