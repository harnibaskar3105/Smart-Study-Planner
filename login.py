if __name__ == "__main__":
    from single_window_app import run
    run(initial_page="login")
    raise SystemExit

import customtkinter as ctk
import subprocess
from PIL import Image, UnidentifiedImageError
import database
from tkinter import messagebox
import os
import sys
from tk_safety import disable_unsafe_windows_titlebar_focus_restore
from theme_manager import get_theme_colors, load_theme as global_load_theme, save_theme as global_save_theme, start_theme_monitor

disable_unsafe_windows_titlebar_focus_restore()

# ---------- Theme System ----------
THEME_FILE = "theme.txt"

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
}


def load_theme():
    return global_load_theme()


def save_theme(theme):
    global_save_theme(theme)


# ---------- App ----------
app = ctk.CTk()
app.title("Login | Schedly")

app.minsize(1100, 700)
try:
    app.attributes("-alpha", 0.0)
except Exception:
    pass

# Load theme
current_theme = load_theme()
ctk.set_appearance_mode(current_theme)
ctk.set_default_color_theme("blue")
start_theme_monitor(app)


# ---------- Load Icons ----------
def load_image(path, size):
    try:
        return ctk.CTkImage(Image.open(path), size=size)
    except (FileNotFoundError, UnidentifiedImageError):
        return None


def maximize_window(window):
    if not window.winfo_exists():
        return
    try:
        window.state("zoomed")
    except Exception:
        width = window.winfo_screenwidth()
        height = window.winfo_screenheight()
        window.geometry(f"{width}x{height}+0+0")


def reveal_window(window):
    maximize_window(window)
    try:
        window.attributes("-alpha", 1.0)
    except Exception:
        pass


eye_open_img = load_image("open eye.png", (18, 18))
eye_closed_img = load_image("close eye.png", (18, 18))
eye_open_img_dark = load_image("open eye white.png", (18, 18))
eye_closed_img_dark = load_image("close eye white.png", (18, 18))
sun_icon = load_image("sun.png", (22, 22))
moon_icon = load_image("moon.png", (22, 22))

password_visible = False


# ---------- Functions ----------
def palette(theme=None):
    return get_theme_colors()


def style_entry(entry, colors):
    entry.configure(
        fg_color=colors["entry"],
        border_color=colors["entry_border"],
        text_color=colors["text"],
        placeholder_text_color=colors["muted"],
    )


def current_eye_icon():
    is_dark = current_theme == "dark"
    if password_visible:
        return eye_closed_img_dark if is_dark and eye_closed_img_dark else eye_closed_img
    return eye_open_img_dark if is_dark and eye_open_img_dark else eye_open_img


def toggle_password():
    global password_visible
    if password_visible:
        password_entry.configure(show="*")
        password_visible = False
    else:
        password_entry.configure(show="")
        password_visible = True
    eye_btn.configure(image=current_eye_icon())


def apply_theme(theme):
    global current_theme
    ctk.set_appearance_mode(theme)
    save_theme(theme)
    current_theme = theme
    colors = palette(theme)

    app.configure(fg_color=colors["bg"])
    bg_frame.configure(fg_color=colors["bg"])
    stage_panel.configure(fg_color=colors["backdrop"], border_color=colors["backdrop_border"])
    stage_accent.configure(fg_color=colors["accent_line"])
    header.configure(fg_color=colors["header"], border_color=colors["header_border"])
    brand_label.configure(text_color=colors["text"])
    badge_label.configure(fg_color=colors["badge_bg"], text_color=colors["badge_text"])
    hero_title.configure(text_color=colors["text"])
    hero_subtitle.configure(text_color=colors["muted"])
    insight_card.configure(fg_color=colors["surface"], border_color=colors["surface_border"])
    insight_title.configure(text_color=colors["text"])
    insight_text.configure(text_color=colors["muted"])
    help_card.configure(fg_color=colors["surface"], border_color=colors["surface_border"])
    help_title.configure(text_color=colors["text"])
    help_text.configure(text_color=colors["muted"])
    card.configure(fg_color=colors["panel"], border_color=colors["panel_border"])
    section_kicker.configure(fg_color=colors["badge_bg"], text_color=colors["badge_text"])
    title_label.configure(text_color=colors["text"])
    subtitle_label.configure(text_color=colors["muted"])
    form_help_label.configure(text_color=colors["muted"])
    username_label.configure(text_color=colors["text"])
    password_label.configure(text_color=colors["text"])
    error_label.configure(text_color=colors["danger"])

    style_entry(username_entry, colors)
    style_entry(password_entry, colors)

    eye_btn.configure(
        image=current_eye_icon(),
        fg_color=colors["entry"],
        hover_color=colors["surface"],
    )
    login_btn.configure(
        fg_color=colors["primary"],
        hover_color=colors["primary_hover"],
        text_color="#ffffff",
    )
    exit_btn.configure(
        fg_color=colors["secondary"],
        hover_color=colors["secondary_hover"],
        text_color=colors["secondary_text"],
    )
    theme_btn.configure(
        image=sun_icon if theme == "dark" else moon_icon,
        fg_color=colors["panel"],
        hover_color=colors["surface"],
        border_color=colors["panel_border"],
    )
    register_link.configure(text_color=colors["link"])


def toggle_theme():
    apply_theme("dark" if current_theme == "light" else "light")


def login_action(event=None):
    username = username_entry.get().strip()
    password = password_entry.get()
    error_label.configure(text="")
    if not username or not password:
        error_label.configure(text="Enter your registered username/email and password.")
        if not username:
            username_entry.focus()
        else:
            password_entry.focus()
        return
    user = database.login_user(username, password)
    if user:
        app.destroy()
        subprocess.Popen([sys.executable, "dashboard.py", username])
    else:
        error_label.configure(text="Invalid credentials. Check your details or create a new account.")
        messagebox.showerror("Login Failed", "Invalid credentials. Check your username/email and password.")


def go_back():
    app.destroy()
    exit()


def open_register(event=None):
    app.destroy()
    subprocess.Popen([sys.executable, "register.py"])


def handle_link_enter(_event):
    colors = palette()
    register_link.configure(text_color=colors["link_hover"])


def handle_link_leave(_event):
    colors = palette()
    register_link.configure(text_color=colors["link"])


# ---------- UI ----------
bg_frame = ctk.CTkFrame(app, fg_color="transparent")
bg_frame.pack(fill="both", expand=True)

stage_panel = ctk.CTkFrame(bg_frame, corner_radius=40, border_width=1)
stage_panel.place(relx=0.5, rely=0.52, relwidth=0.92, relheight=0.73, anchor="center")
stage_accent = ctk.CTkFrame(bg_frame, width=8, corner_radius=999)
stage_accent.place(relx=0.045, rely=0.52, relheight=0.46, anchor="w")

header = ctk.CTkFrame(bg_frame, height=72, corner_radius=24, border_width=1)
header.pack(fill="x", padx=36, pady=(24, 12))
brand_label = ctk.CTkLabel(header, text="SCHEDLY", font=("Segoe UI Semibold", 24))
brand_label.pack(side="left", padx=26, pady=16)
theme_btn = ctk.CTkButton(
    header,
    text="",
    width=44,
    height=44,
    corner_radius=14,
    border_width=1,
    command=toggle_theme,
)
theme_btn.pack(side="right", padx=18, pady=14)

main_frame = ctk.CTkFrame(bg_frame, fg_color="transparent")
main_frame.pack(fill="both", expand=True, padx=52, pady=(8, 36))
main_frame.grid_columnconfigure(0, weight=11)
main_frame.grid_columnconfigure(1, weight=9)
main_frame.grid_rowconfigure(0, weight=1)

hero_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
hero_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 24))
hero_inner = ctk.CTkFrame(hero_frame, fg_color="transparent", width=560, height=440)
hero_inner.place(relx=0.03, rely=0.46, anchor="w")
hero_inner.pack_propagate(False)

badge_label = ctk.CTkLabel(
    hero_inner,
    text=" Focus with structure ",
    font=("Segoe UI Semibold", 13),
    corner_radius=999,
    padx=14,
    pady=8,
)
badge_label.pack(anchor="w", pady=(0, 18))

hero_title = ctk.CTkLabel(
    hero_inner,
    text="Plan smarter, study calmer, finish stronger.",
    font=("Georgia", 35, "bold"),
    justify="left",
    wraplength=500,
)
hero_title.pack(anchor="w")

hero_subtitle = ctk.CTkLabel(
    hero_inner,
    text="Built for college students who want to track sessions, organize coursework, and return to a workspace that feels clear and ready.",
    font=("Segoe UI", 15),
    justify="left",
    wraplength=500,
)
hero_subtitle.pack(anchor="w", pady=(14, 28))

insight_card = ctk.CTkFrame(hero_inner, width=520, height=160, corner_radius=22, border_width=1)
insight_card.pack(anchor="w", ipadx=10, ipady=10)
insight_card.pack_propagate(False)
insight_title = ctk.CTkLabel(insight_card, text="Today feels easier when the next step is obvious.", font=("Segoe UI Semibold", 16))
insight_title.pack(anchor="w", padx=22, pady=(18, 8))
insight_text = ctk.CTkLabel(
    insight_card,
    text="Use your planner to move from scattered tasks to a steady routine with fewer missed deadlines.",
    font=("Segoe UI", 14),
    justify="left",
    wraplength=360,
)
insight_text.pack(anchor="w", padx=22, pady=(0, 18))

help_card = ctk.CTkFrame(hero_inner, width=520, height=118, corner_radius=22, border_width=1)
help_card.pack(anchor="w", pady=(14, 0), ipadx=10, ipady=10)
help_card.pack_propagate(False)
help_title = ctk.CTkLabel(help_card, text="Returning user guide", font=("Segoe UI Semibold", 15))
help_title.pack(anchor="w", padx=22, pady=(16, 6))
help_text = ctk.CTkLabel(
    help_card,
    text="Login using your registered username or email and password to continue your study journey. Forgot your password? Create a new account or ask your app admin to reset access.",
    font=("Segoe UI", 13),
    justify="left",
    wraplength=430,
)
help_text.pack(anchor="w", padx=22)

card_wrap = ctk.CTkFrame(main_frame, fg_color="transparent")
card_wrap.grid(row=0, column=1, sticky="nsew")

card = ctk.CTkFrame(card_wrap, width=450, height=500, corner_radius=30, border_width=1)
card.place(relx=0.5, rely=0.46, anchor="center")
card.pack_propagate(False)

content = ctk.CTkFrame(card, fg_color="transparent")
content.place(relx=0.5, rely=0.5, anchor="center")

section_kicker = ctk.CTkLabel(content, text=" Welcome Back ", font=("Segoe UI Semibold", 12), corner_radius=999, padx=12, pady=6)
section_kicker.pack(pady=(0, 14))

title_label = ctk.CTkLabel(content, text="Sign in to your account", font=("Segoe UI Semibold", 28))
title_label.pack()
subtitle_label = ctk.CTkLabel(content, text="Pick up where you left off and continue your study flow.", font=("Segoe UI", 14))
subtitle_label.pack(pady=(8, 28))

form_help_label = ctk.CTkLabel(
    content,
    text="Use the account details you created during registration.",
    font=("Segoe UI", 12),
    wraplength=330,
    justify="center",
)
form_help_label.pack(pady=(0, 12))

username_label = ctk.CTkLabel(content, text="Username", font=("Segoe UI Semibold", 12), anchor="w")
username_label.pack(anchor="w", padx=18, pady=(0, 6))
username_entry = ctk.CTkEntry(content, width=340, height=50, corner_radius=18, border_width=1, placeholder_text="Username")
username_entry.pack(pady=(0, 16))

password_label = ctk.CTkLabel(content, text="Password", font=("Segoe UI Semibold", 12), anchor="w")
password_label.pack(anchor="w", padx=18, pady=(0, 6))
password_entry = ctk.CTkEntry(
    content,
    width=340,
    height=50,
    corner_radius=18,
    placeholder_text="Password",
    border_width=1,
    show="*"
)
password_entry.pack(pady=(0, 10))

eye_btn = ctk.CTkButton(
    content,
    image=eye_open_img if not password_visible else eye_closed_img,
    text="",
    width=30,
    height=30,
    corner_radius=0,
    border_width=0,
    command=toggle_password,
)
eye_btn.place(in_=password_entry, relx=0.93, rely=0.5, anchor="center")

error_label = ctk.CTkLabel(content, text="", font=("Segoe UI Semibold", 12), wraplength=330, justify="center")
error_label.pack(pady=(0, 2))

btn_frame = ctk.CTkFrame(content, fg_color="transparent")
btn_frame.pack(pady=(18, 20))
login_btn = ctk.CTkButton(btn_frame, text="Login", width=160, height=48, corner_radius=18, font=("Segoe UI Semibold", 15), command=login_action)
login_btn.grid(row=0, column=0, padx=8)
exit_btn = ctk.CTkButton(btn_frame, text="Exit", width=160, height=48, corner_radius=18, font=("Segoe UI Semibold", 15), command=go_back)
exit_btn.grid(row=0, column=1, padx=8)

register_link = ctk.CTkLabel(content, text="Don't have an account? Register", font=("Segoe UI Semibold", 13), cursor="hand2")
register_link.pack(pady=(6, 0))
register_link.bind("<Button-1>", open_register)
register_link.bind("<Enter>", handle_link_enter)
register_link.bind("<Leave>", handle_link_leave)

app.bind("<Return>", login_action)
apply_theme(current_theme)
app.after(80, lambda: reveal_window(app))
app.mainloop()
