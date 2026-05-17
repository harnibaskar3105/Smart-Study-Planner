import sys

import customtkinter as ctk


def disable_unsafe_windows_titlebar_focus_restore():
    if not sys.platform.startswith("win"):
        return

    for window_class_name in ("CTk", "CTkToplevel"):
        window_class = getattr(ctk, window_class_name, None)
        if window_class is not None:
            window_class._deactivate_windows_window_header_manipulation = True
