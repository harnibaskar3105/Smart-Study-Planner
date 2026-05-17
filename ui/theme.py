from theme_manager import get_fonts, get_theme_colors, load_theme

APP_MIN_SIZE = (1120, 720)
CARD_RADIUS = 22
PANEL_RADIUS = 28
SHELL_RADIUS = 38
BUTTON_RADIUS = 14
CONTROL_HEIGHT = 42


def palette(theme=None):
    colors = get_theme_colors()
    if theme and theme != load_theme():
        settings_mode = {"appearance_mode": theme, "theme_name": "green", "custom_accent": "#78c8c1"}
        colors = get_theme_colors(settings_mode)
    return {
        **colors,
        "border": colors["panel_border"],
    }


def fonts():
    return get_fonts()


def apply_window_chrome(window):
    window.minsize(*APP_MIN_SIZE)
    try:
        window.state("zoomed")
    except Exception:
        pass


def configure_card(widget, colors=None, surface=True):
    colors = colors or palette()
    widget.configure(
        fg_color=colors["surface" if surface else "panel"],
        border_color=colors["surface_border" if surface else "panel_border"],
        border_width=1,
        corner_radius=CARD_RADIUS,
    )


def style_button(widget, colors=None, variant="primary"):
    colors = colors or palette()
    if variant == "secondary":
        widget.configure(fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"])
    elif variant == "danger":
        widget.configure(fg_color=colors["danger"], hover_color=colors["danger_hover"], text_color="#ffffff")
    else:
        widget.configure(fg_color=colors["primary"], hover_color=colors["primary_hover"], text_color="#ffffff")


def style_entry(widget, colors=None):
    colors = colors or palette()
    widget.configure(
        fg_color=colors["entry"],
        border_color=colors["entry_border"],
        text_color=colors["text"],
        placeholder_text_color=colors["muted"],
    )
