if __name__ == "__main__":
    from single_window_app import run
    run(initial_page="register")
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
register_app = ctk.CTk()
register_app.title("Register | Schedly")

register_app.minsize(1100, 760)
try:
    register_app.attributes("-alpha", 0.0)
except Exception:
    pass

# Load theme
current_theme = load_theme()
ctk.set_appearance_mode(current_theme)
ctk.set_default_color_theme("blue")


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


eye_open_img = load_image("open eye.png", (18, 18))
eye_closed_img = load_image("close eye.png", (18, 18))
eye_open_img_dark = load_image("open eye white.png", (18, 18))
eye_closed_img_dark = load_image("close eye white.png", (18, 18))
sun_icon = load_image("sun.png", (22, 22))
moon_icon = load_image("moon.png", (22, 22))


# ---------- State ----------
password_visible = False
confirm_visible = False
field_labels = []


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


def eye_icon(is_visible):
    is_dark = current_theme == "dark"
    if is_visible:
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
    eye_btn.configure(image=eye_icon(password_visible))


def toggle_confirm():
    global confirm_visible
    if confirm_visible:
        confirm_entry.configure(show="*")
        confirm_visible = False
    else:
        confirm_entry.configure(show="")
        confirm_visible = True
    eye_btn2.configure(image=eye_icon(confirm_visible))


def apply_theme(theme):
    global current_theme
    ctk.set_appearance_mode(theme)
    save_theme(theme)
    current_theme = theme
    colors = palette(theme)

    register_app.configure(fg_color=colors["bg"])
    bg_frame.configure(fg_color=colors["bg"])
    stage_panel.configure(fg_color=colors["backdrop"], border_color=colors["backdrop_border"])
    stage_accent.configure(fg_color=colors["accent_line"])
    header.configure(fg_color=colors["header"], border_color=colors["header_border"])
    brand_label.configure(text_color=colors["text"])
    badge_label.configure(fg_color=colors["badge_bg"], text_color=colors["badge_text"])
    hero_title.configure(text_color=colors["text"])
    hero_subtitle.configure(text_color=colors["muted"])
    checklist_card.configure(fg_color=colors["surface"], border_color=colors["surface_border"])
    checklist_title.configure(text_color=colors["text"])

    for label in checklist_items:
        label.configure(text_color=colors["muted"])

    card.configure(fg_color=colors["panel"], border_color=colors["panel_border"])
    section_kicker.configure(fg_color=colors["badge_bg"], text_color=colors["badge_text"])
    title_label.configure(text_color=colors["text"])
    subtitle_label.configure(text_color=colors["muted"])
    required_hint.configure(text_color=colors["muted"])
    password_hint.configure(text_color=colors["muted"])
    confirm_hint.configure(text_color=colors["muted"])
    validation_label.configure(text_color=colors["danger"])
    for label in field_labels:
        label.configure(text_color=colors["text"])

    for entry in [fullname_entry, email_entry, username_entry, password_entry, confirm_entry]:
        style_entry(entry, colors)

    for eye in [eye_btn, eye_btn2]:
        eye.configure(fg_color=colors["entry"], hover_color=colors["surface"])
    eye_btn.configure(image=eye_icon(password_visible))
    eye_btn2.configure(image=eye_icon(confirm_visible))

    register_btn.configure(fg_color=colors["primary"], hover_color=colors["primary_hover"], text_color="#ffffff")
    exit_btn.configure(fg_color=colors["secondary"], hover_color=colors["secondary_hover"], text_color=colors["secondary_text"])
    theme_btn.configure(
        image=sun_icon if theme == "dark" else moon_icon,
        fg_color=colors["panel"],
        hover_color=colors["surface"],
        border_color=colors["panel_border"],
    )


def toggle_theme():
    apply_theme("dark" if current_theme == "light" else "light")


def go_back():
    register_app.destroy()
    subprocess.Popen([sys.executable, "login.py"])


def register_action():
    fullname = fullname_entry.get().strip()
    email = email_entry.get().strip()
    username = username_entry.get().strip()
    password = password_entry.get()
    confirm = confirm_entry.get()

    if not fullname or not email or not username or not password or not confirm:
        validation_label.configure(text="All fields are required.")
        messagebox.showerror("Missing Details", "All fields are required.")
        return

    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        validation_label.configure(text="Enter a valid email address.")
        messagebox.showerror("Invalid Email", "Enter a valid email address.")
        return

    if len(username) < 3:
        validation_label.configure(text="Username must be at least 3 characters.")
        messagebox.showerror("Invalid Username", "Username must be at least 3 characters.")
        return

    if len(password) < 8:
        validation_label.configure(text="Password must be at least 8 characters.")
        messagebox.showerror("Weak Password", "Password must be at least 8 characters.")
        return

    if password != confirm:
        validation_label.configure(text="Passwords do not match.")
        messagebox.showerror("Password Mismatch", "Passwords do not match.")
        return

    success = database.register_user(fullname, email, username, password)
    if success:
        messagebox.showinfo("Success", "Account created successfully")
        register_app.destroy()
        subprocess.Popen([sys.executable, "login.py"])
    else:
        validation_label.configure(text="Username or email already exists.")
        messagebox.showerror("Account Exists", "Username or email already exists")


def validate_form(_event=None):
    colors = palette()
    password = password_entry.get()
    confirm = confirm_entry.get()
    filled = all(entry.get().strip() for entry in [fullname_entry, email_entry, username_entry])

    if not filled:
        validation_label.configure(text="Complete name, email, username, password, and confirmation.", text_color=colors["muted"])
    elif len(password) < 6:
        validation_label.configure(text="Password needs at least 6 characters.", text_color=colors["danger"])
    elif confirm and password != confirm:
        validation_label.configure(text="Passwords do not match yet.", text_color=colors["danger"])
    elif password and confirm:
        validation_label.configure(text="Looks good. You can create your account.", text_color=colors["success"])
    else:
        validation_label.configure(text="Confirm your password to finish setup.", text_color=colors["muted"])


# ---------- UI ----------
bg_frame = ctk.CTkFrame(register_app, fg_color="transparent")
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
hero_inner = ctk.CTkFrame(hero_frame, fg_color="transparent", width=560, height=500)
hero_inner.place(relx=0.03, rely=0.46, anchor="w")
hero_inner.pack_propagate(False)

badge_label = ctk.CTkLabel(
    hero_inner,
    text=" Build your routine ",
    font=("Segoe UI Semibold", 13),
    corner_radius=999,
    padx=14,
    pady=8,
)
badge_label.pack(anchor="w", pady=(0, 18))

hero_title = ctk.CTkLabel(
    hero_inner,
    text="Create a study space that feels calm, clear, and motivating.",
    font=("Georgia", 34, "bold"),
    justify="left",
    wraplength=500,
)
hero_title.pack(anchor="w")

hero_subtitle = ctk.CTkLabel(
    hero_inner,
    text="Set up your account once, then come back to organized coursework, tasks, and progress designed for college students.",
    font=("Segoe UI", 15),
    justify="left",
    wraplength=500,
)
hero_subtitle.pack(anchor="w", pady=(14, 28))

checklist_card = ctk.CTkFrame(hero_inner, width=520, height=225, corner_radius=22, border_width=1)
checklist_card.pack(anchor="w", ipadx=10, ipady=10)
checklist_card.pack_propagate(False)
checklist_title = ctk.CTkLabel(checklist_card, text="What you get right away", font=("Segoe UI Semibold", 16))
checklist_title.pack(anchor="w", padx=22, pady=(18, 10))
checklist_items = []
for text in [
    "Track attendance, weekly leave, and study goals in one place",
    "Earn XP, level up, unlock badges, and keep streaks alive",
    "Plan tasks with clean reminders and progress visibility",
]:
    item = ctk.CTkLabel(checklist_card, text=f"- {text}", font=("Segoe UI", 14), justify="left", wraplength=360)
    item.pack(anchor="w", padx=22, pady=(0, 8))
    checklist_items.append(item)

card_wrap = ctk.CTkFrame(main_frame, fg_color="transparent")
card_wrap.grid(row=0, column=1, sticky="nsew")

card = ctk.CTkFrame(card_wrap, width=460, height=650, corner_radius=30, border_width=1)
card.place(relx=0.5, rely=0.46, anchor="center")
card.pack_propagate(False)

content = ctk.CTkFrame(card, fg_color="transparent")
content.place(relx=0.5, rely=0.5, anchor="center")

section_kicker = ctk.CTkLabel(content, text=" New Account ", font=("Segoe UI Semibold", 12), corner_radius=999, padx=12, pady=6)
section_kicker.pack(pady=(0, 14))

title_label = ctk.CTkLabel(content, text="Create your account", font=("Segoe UI Semibold", 28))
title_label.pack()
subtitle_label = ctk.CTkLabel(content, text="A few details and you are ready to start planning.", font=("Segoe UI", 14))
subtitle_label.pack(pady=(8, 12))

required_hint = ctk.CTkLabel(
    content,
    text="Create your account to track attendance, manage study goals, earn rewards, and access gamified features. All fields are required.",
    font=("Segoe UI", 12),
    wraplength=340,
    justify="center",
)
required_hint.pack(pady=(0, 14))


def create_entry(label, placeholder):
    field_label = ctk.CTkLabel(content, text=label, font=("Segoe UI Semibold", 12), anchor="w")
    field_label.pack(anchor="w", padx=18, pady=(0, 6))
    field_labels.append(field_label)
    entry = ctk.CTkEntry(content, width=340, height=50, corner_radius=18, border_width=1, placeholder_text=placeholder)
    entry.pack(pady=(0, 14))
    return entry


fullname_entry = create_entry("Full name", "Full Name")
email_entry = create_entry("Email address", "Email Address")
username_entry = create_entry("Username", "Username")

password_label = ctk.CTkLabel(content, text="Password", font=("Segoe UI Semibold", 12), anchor="w")
password_label.pack(anchor="w", padx=18, pady=(0, 6))
field_labels.append(password_label)
password_entry = ctk.CTkEntry(content, width=340, height=50, corner_radius=18, border_width=1, placeholder_text="Password", show="*")
password_entry.pack(pady=(0, 6))

eye_btn = ctk.CTkButton(
    content,
    image=eye_open_img,
    text="",
    width=30,
    height=30,
    corner_radius=0,
    border_width=0,
    command=toggle_password,
)
eye_btn.place(in_=password_entry, relx=0.93, rely=0.5, anchor="center")

password_hint = ctk.CTkLabel(content, text="Use at least 6 characters.", font=("Segoe UI", 11), wraplength=330, justify="left")
password_hint.pack(anchor="w", padx=18, pady=(0, 8))

confirm_label = ctk.CTkLabel(content, text="Confirm password", font=("Segoe UI Semibold", 12), anchor="w")
confirm_label.pack(anchor="w", padx=18, pady=(0, 6))
field_labels.append(confirm_label)
confirm_entry = ctk.CTkEntry(content, width=340, height=50, corner_radius=18, border_width=1, placeholder_text="Confirm Password", show="*")
confirm_entry.pack(pady=(0, 6))

eye_btn2 = ctk.CTkButton(
    content,
    image=eye_open_img,
    text="",
    width=30,
    height=30,
    corner_radius=0,
    border_width=0,
    command=toggle_confirm,
)
eye_btn2.place(in_=confirm_entry, relx=0.93, rely=0.5, anchor="center")

confirm_hint = ctk.CTkLabel(content, text="Re-enter the same password to avoid mistakes.", font=("Segoe UI", 11), wraplength=330, justify="left")
confirm_hint.pack(anchor="w", padx=18, pady=(0, 6))

validation_label = ctk.CTkLabel(content, text="Complete all fields to enable your study dashboard.", font=("Segoe UI Semibold", 12), wraplength=330, justify="center")
validation_label.pack(pady=(0, 2))

btn_frame = ctk.CTkFrame(content, fg_color="transparent")
btn_frame.pack(fill="x", padx=18, pady=(12, 0))

register_btn = ctk.CTkButton(btn_frame, text="Register", height=48, corner_radius=18, font=("Segoe UI Semibold", 15), command=register_action)
register_btn.pack(fill="x", pady=(0, 10))

exit_btn = ctk.CTkButton(btn_frame, text="Back to Login", height=44, corner_radius=18, font=("Segoe UI Semibold", 15), command=go_back)
exit_btn.pack(fill="x")

for field in [fullname_entry, email_entry, username_entry, password_entry, confirm_entry]:
    field.bind("<KeyRelease>", validate_form)

apply_theme(current_theme)
register_app.after(80, lambda: reveal_window(register_app))
register_app.mainloop()
