import customtkinter as ctk
from PIL import Image, UnidentifiedImageError

from settings.settings_manager import settings_manager
from tk_safety import disable_unsafe_windows_titlebar_focus_restore


disable_unsafe_windows_titlebar_focus_restore()

ACCENTS = {
    "green": {
        "primary": "#2f9e99",
        "primary_hover": "#258782",
        "success": "#3aa76d",
        "accent": "#d45f7f",
        "warning": "#d89a35",
    },
    "blue": {
        "primary": "#4c7ed9",
        "primary_hover": "#3d68ba",
        "success": "#2f9e99",
        "accent": "#d45f7f",
        "warning": "#d89a35",
    },
}

BASE_LIGHT = {
    "bg": "#eee7df",
    "bg_soft": "#f5f0ea",
    "backdrop": "#f8f3ee",
    "backdrop_border": "#e2d7cf",
    "accent_line": "#2f9e99",
    "panel": "#fffaf5",
    "panel_border": "#e4d8cf",
    "surface": "#f3e8df",
    "surface_border": "#dccdc4",
    "text": "#2e2530",
    "muted": "#6f6470",
    "secondary": "#eadfd8",
    "secondary_hover": "#dfd0c8",
    "secondary_text": "#3e3340",
    "badge_bg": "#e7dad4",
    "badge_text": "#6d5364",
    "link": "#247f79",
    "link_hover": "#1e6c67",
    "entry": "#fffdf9",
    "entry_border": "#d6c8bf",
    "header": "#fffaf5",
    "header_border": "#e4d8cf",
    "sidebar": "#ebe1d9",
    "sidebar_border": "#ddcec5",
    "sidebar_hover": "#dfd4cd",
    "sidebar_active": "#fffaf5",
    "sidebar_active_border": "#e5d7cf",
    "sidebar_icon": "#f6eee8",
    "sidebar_icon_active": "#2f9e99",
    "tile": "#fffdf9",
    "tile_hover": "#f6eee8",
    "danger": "#c84d6d",
    "danger_hover": "#ad3f5d",
    "card": "#f3e8df",
    "card_light": "#fffdf9",
    "deep": "#6d5364",
    "deep_hover": "#5b4555",
    "pink": "#d45f7f",
    "teal": "#2f9e99",
    "yellow": "#d89a35",
    "green": "#3aa76d",
    "white": "#ffffff",
}

BASE_DARK = {
    "bg": "#17131c",
    "bg_soft": "#201a26",
    "backdrop": "#201a26",
    "backdrop_border": "#3a303f",
    "accent_line": "#58c7c1",
    "panel": "#211b27",
    "panel_border": "#3a3040",
    "surface": "#2c2433",
    "surface_border": "#45394c",
    "text": "#fbf7fd",
    "muted": "#c7bacd",
    "secondary": "#3a3042",
    "secondary_hover": "#473b50",
    "secondary_text": "#f0e8f4",
    "badge_bg": "#3d3145",
    "badge_text": "#e9dced",
    "link": "#80ddd8",
    "link_hover": "#a2ebe7",
    "entry": "#342b3c",
    "entry_border": "#5a4a62",
    "header": "#26202d",
    "header_border": "#433749",
    "sidebar": "#201a26",
    "sidebar_border": "#3b3142",
    "sidebar_hover": "#342b3c",
    "sidebar_active": "#2c2433",
    "sidebar_active_border": "#4a3d52",
    "sidebar_icon": "#342b3c",
    "sidebar_icon_active": "#58c7c1",
    "tile": "#332a3b",
    "tile_hover": "#3f3447",
    "danger": "#f07a98",
    "danger_hover": "#dd6686",
    "card": "#342b3c",
    "card_light": "#44394c",
    "deep": "#c5a8bd",
    "deep_hover": "#d6bdd0",
    "pink": "#f07a98",
    "teal": "#58c7c1",
    "yellow": "#f1bd62",
    "green": "#7fd39a",
    "white": "#ffffff",
}


def _placeholder_icon():
    return ctk.CTkImage(Image.new("RGBA", (22, 22), (0, 0, 0, 0)), size=(22, 22))


def _shade(hex_color, amount=-22):
    value = hex_color.lstrip("#")
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    try:
        channels = [max(0, min(255, int(value[index:index + 2], 16) + amount)) for index in (0, 2, 4)]
    except ValueError:
        return "#61b8b0"
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def load_settings():
    return settings_manager.load()


def load_theme():
    return settings_manager.load()["appearance_mode"]


def save_theme(theme):
    settings_manager.update(appearance_mode=theme)


def get_theme_colors(settings=None):
    settings = settings or settings_manager.load()
    colors = dict(BASE_DARK if settings["appearance_mode"] == "dark" else BASE_LIGHT)
    if settings["theme_name"] == "custom":
        accent = settings["custom_accent"]
        colors.update({"primary": accent, "primary_hover": _shade(accent), "success": accent})
    else:
        colors.update(ACCENTS.get(settings["theme_name"], ACCENTS["green"]))
    return colors


def get_fonts(settings=None):
    settings = settings or settings_manager.load()
    size = int(settings.get("font_size", 14))
    return {
        "body": ("Segoe UI", size),
        "body_semibold": ("Segoe UI Semibold", size),
        "small": ("Segoe UI", max(size - 2, 10)),
        "title": ("Segoe UI Semibold", size + 12),
        "section": ("Segoe UI Semibold", size + 6),
        "display": ("Segoe UI Semibold", size + 18),
    }


def apply_theme(theme=None, theme_name=None, custom_accent=None):
    changes = {}
    if theme:
        changes["appearance_mode"] = theme
    if theme_name:
        changes["theme_name"] = theme_name
    if custom_accent:
        changes["custom_accent"] = custom_accent
        changes["theme_name"] = "custom"
    settings = settings_manager.update(**changes) if changes else settings_manager.load()
    ctk.set_appearance_mode(settings["appearance_mode"])
    return get_theme_colors(settings)


def toggle_theme(current_theme=None):
    mode = current_theme or load_theme()
    next_mode = "dark" if mode == "light" else "light"
    apply_theme(next_mode)
    return next_mode


def style_button(widget, variant="primary"):
    colors = get_theme_colors()
    if variant == "secondary":
        widget.configure(fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"])
    elif variant == "danger":
        widget.configure(fg_color=colors["danger"], hover_color=colors["danger_hover"], text_color="#ffffff")
    else:
        widget.configure(fg_color=colors["primary"], hover_color=colors["primary_hover"], text_color="#ffffff")


def style_frame(widget, surface=False):
    colors = get_theme_colors()
    widget.configure(
        fg_color=colors["surface" if surface else "panel"],
        border_color=colors["surface_border" if surface else "panel_border"],
    )


def start_theme_monitor(app, check_interval_ms=1000, on_change=None):
    state = {"settings": settings_manager.load()}

    def check_theme_change():
        try:
            settings_manager._cache = None
            new_settings = settings_manager.load()
            if new_settings != state["settings"]:
                state["settings"] = new_settings
                ctk.set_appearance_mode(new_settings["appearance_mode"])
                if on_change:
                    on_change(new_settings)
        except Exception:
            pass
        if app.winfo_exists():
            app.after(check_interval_ms, check_theme_change)

    app.after(check_interval_ms, check_theme_change)


def load_icons():
    try:
        light_icon = ctk.CTkImage(Image.open("sun.png"), size=(22, 22))
        dark_icon = ctk.CTkImage(Image.open("moon.png"), size=(22, 22))
    except (FileNotFoundError, UnidentifiedImageError, OSError):
        return _placeholder_icon(), _placeholder_icon()
    return light_icon, dark_icon


def create_theme_button(parent, app):
    current_theme = load_theme()
    light_icon, dark_icon = load_icons()

    def switch():
        nonlocal current_theme
        current_theme = toggle_theme(current_theme)
        btn.configure(image=light_icon if current_theme == "dark" else dark_icon)

    btn = ctk.CTkButton(
        parent,
        text="",
        image=dark_icon if current_theme == "light" else light_icon,
        width=40,
        height=40,
        fg_color="transparent",
        command=switch,
    )
    return btn
