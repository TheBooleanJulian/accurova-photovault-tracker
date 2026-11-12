"""
theme.py
Julian Unified UI for tkinter (spec: thebooleanjulian-branding/julian-unified-ui-design-system.md).

DARK / LIGHT hold the opaque colour tokens from tokens/unified.json (the rgba
tints/scrim are left out - tkinter can't draw alpha). Dark is the default; the
Windows "apps" light/dark setting is followed when it can be read.

Native Windows message boxes cannot be themed, so `show_dialog` is a small
branded replacement for messagebox.showinfo / showwarning / showerror / askyesno.
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

DARK = {
    "bg": "#05060d", "surface": "#0b0e1a", "surface-raised": "#121629", "surface-overlay": "#1a2040",
    "line": "#262d52", "line-strong": "#6370b6",
    "ink": "#e8ecff", "ink-muted": "#9ca5d4", "ink-faint": "#8089bd",
    "cyan": "#00e5ff", "magenta": "#ff2bd6", "cyan-ink": "#19e6ff", "magenta-ink": "#ff6be2",
    "on-accent": "#02101a",
    "success": "#2de2a6", "warning": "#ffc233", "danger": "#ff6482",
}

LIGHT = {
    "bg": "#f3f5ff", "surface": "#ffffff", "surface-raised": "#eaeefc", "surface-overlay": "#dde3f9",
    "line": "#cdd4f0", "line-strong": "#6c76a8",
    "ink": "#0b1030", "ink-muted": "#414a78", "ink-faint": "#5a6391",
    "cyan": "#00c8e8", "magenta": "#f01fc8", "cyan-ink": "#00657d", "magenta-ink": "#a8008a",
    "on-accent": "#02101a",
    "success": "#00704f", "warning": "#7f5400", "danger": "#c4003a",
}

# Brand family first, then the spec's system fallbacks.
DISPLAY_FONTS = ("Chakra Petch", "Rajdhani", "Segoe UI")
SANS_FONTS = ("IBM Plex Sans", "Segoe UI")
MONO_FONTS = ("JetBrains Mono", "Cascadia Code", "Consolas")

# kind -> (colour token, glyph, word). Colour is never the only cue.
KINDS = {
    "info": ("cyan-ink", "i", "INFO"),
    "success": ("success", "✓", "DONE"),
    "warning": ("warning", "!", "WARNING"),
    "error": ("danger", "✕", "ERROR"),
    "question": ("cyan-ink", "?", "CONFIRM"),
}

_state = {"colors": DARK, "fonts": {}}


def detect_mode() -> str:
    """'light' if Windows is set to light apps, otherwise 'dark' (the default)."""
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            return "light" if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 1 else "dark"
    except (ImportError, OSError):
        return "dark"


def _pick(installed, wanted):
    return next((f for f in wanted if f in installed), wanted[-1])


def colors() -> dict:
    return _state["colors"]


def fonts() -> dict:
    return _state["fonts"]


def apply(root, mode=None) -> None:
    """Style the root window and every ttk widget. Call once, before building the UI."""
    c = DARK if (mode or detect_mode()) == "dark" else LIGHT
    _state["colors"] = c
    installed = set(tkfont.families(root))
    display, sans, mono = (_pick(installed, DISPLAY_FONTS), _pick(installed, SANS_FONTS),
                           _pick(installed, MONO_FONTS))
    f = {
        "body": (sans, 10),
        "body-sm": (sans, 9),
        "title": (sans, 11, "bold"),
        "label": (display, 8, "bold"),
        "mono": (mono, 9),
    }
    _state["fonts"] = f

    root.configure(bg=c["bg"])
    # Defaults for the plain tk widgets (Listbox, Text, dialogs' Text boxes).
    root.option_add("*Font", f["body"])

    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=c["bg"], foreground=c["ink"], font=f["body"],
                bordercolor=c["line"], lightcolor=c["bg"], darkcolor=c["bg"],
                focuscolor=c["cyan-ink"], troughcolor=c["surface"])
    s.configure("TFrame", background=c["bg"])
    s.configure("TLabel", background=c["bg"], foreground=c["ink"])
    s.configure("Hint.TLabel", foreground=c["ink-faint"], font=f["body-sm"])
    s.configure("TLabelframe", background=c["bg"], bordercolor=c["line"],
                lightcolor=c["line"], darkcolor=c["line"], relief="solid", borderwidth=1)
    s.configure("TLabelframe.Label", background=c["bg"], foreground=c["ink-muted"], font=f["label"])

    s.configure("TEntry", fieldbackground=c["surface"], foreground=c["ink"], insertcolor=c["ink"],
                bordercolor=c["line-strong"], lightcolor=c["line-strong"], darkcolor=c["line-strong"],
                padding=4)
    s.map("TEntry", bordercolor=[("focus", c["cyan-ink"])],
          lightcolor=[("focus", c["cyan-ink"])], darkcolor=[("focus", c["cyan-ink"])])

    s.configure("TButton", background=c["surface-raised"], foreground=c["ink"],
                bordercolor=c["line-strong"], lightcolor=c["surface-raised"],
                darkcolor=c["surface-raised"], padding=(12, 5), font=f["label"])
    s.map("TButton",
          background=[("disabled", c["surface"]), ("active", c["surface-overlay"])],
          foreground=[("disabled", c["ink-faint"])],
          bordercolor=[("disabled", c["line"]), ("focus", c["cyan-ink"])])
    s.configure("Primary.TButton", background=c["cyan"], foreground=c["on-accent"],
                bordercolor=c["cyan"], lightcolor=c["cyan"], darkcolor=c["cyan"])
    s.map("Primary.TButton",
          background=[("disabled", c["surface-overlay"]), ("active", c["cyan-ink"])],
          foreground=[("disabled", c["ink-faint"])],
          bordercolor=[("disabled", c["line"]), ("active", c["cyan-ink"])])

    s.configure("Vertical.TScrollbar", background=c["surface-overlay"], troughcolor=c["surface"],
                bordercolor=c["surface"], arrowcolor=c["ink-muted"],
                lightcolor=c["surface-overlay"], darkcolor=c["surface-overlay"])
    s.map("Vertical.TScrollbar", background=[("active", c["line-strong"])])


def style_listbox(widget) -> None:
    c = _state["colors"]
    widget.config(bg=c["surface"], fg=c["ink"], selectbackground=c["surface-overlay"],
                  selectforeground=c["ink"], relief="flat", borderwidth=0, highlightthickness=1,
                  highlightbackground=c["line-strong"], highlightcolor=c["cyan-ink"],
                  font=_state["fonts"]["mono"], activestyle="none")


def style_text(widget) -> None:
    c = _state["colors"]
    widget.config(bg=c["surface"], fg=c["ink"], insertbackground=c["ink"],
                  selectbackground=c["surface-overlay"], selectforeground=c["ink"],
                  relief="flat", borderwidth=0, highlightthickness=1,
                  highlightbackground=c["line-strong"], highlightcolor=c["cyan-ink"],
                  font=_state["fonts"]["mono"], padx=8, pady=6)
    widget.tag_config("error", foreground=c["danger"])


def show_dialog(parent, title, message, kind="info", buttons=("OK",), primary=None) -> str:
    """
    Modal branded dialog. Returns the text of the clicked button (the first
    button if the window is closed). `primary` is the highlighted button
    (default: the first).
    """
    c, f = _state["colors"], _state["fonts"]
    accent, glyph, word = KINDS[kind]
    primary = primary or buttons[0]
    result = {"value": buttons[-1] if len(buttons) > 1 else buttons[0]}

    win = tk.Toplevel(parent)
    win.title(title)
    win.configure(bg=c["surface"], highlightthickness=1, highlightbackground=c["line"])
    win.transient(parent)
    win.resizable(False, False)

    head = tk.Frame(win, bg=c["surface"])
    head.pack(fill="x", padx=20, pady=(18, 8))
    tk.Label(head, text=glyph, bg=c["surface"], fg=c[accent], font=(f["title"][0], 18, "bold"),
             width=2).pack(side="left")
    tk.Label(head, text=f"{word} · {title}".upper(), bg=c["surface"], fg=c[accent],
             font=f["label"], anchor="w").pack(side="left", padx=(6, 0))

    body = tk.Frame(win, bg=c["surface"])
    body.pack(fill="both", expand=True, padx=20)
    lines = sum(max(1, len(line) // 62 + 1) for line in message.split("\n"))
    box = tk.Text(body, width=64, height=min(max(lines, 2), 14), wrap="word")
    style_text(box)
    box.config(font=f["body"], highlightbackground=c["line"])
    box.insert("1.0", message)
    box.config(state="disabled")
    bar = ttk.Scrollbar(body, orient="vertical", command=box.yview)
    box.config(yscrollcommand=bar.set)
    box.pack(side="left", fill="both", expand=True)
    if lines > 14:
        bar.pack(side="left", fill="y")

    foot = tk.Frame(win, bg=c["surface"])
    foot.pack(fill="x", padx=20, pady=16)

    def choose(text):
        result["value"] = text
        win.destroy()

    for text in reversed(buttons):
        ttk.Button(foot, text=text.upper(), command=lambda t=text: choose(t),
                   style="Primary.TButton" if text == primary else "TButton").pack(side="right", padx=(8, 0))

    win.protocol("WM_DELETE_WINDOW", lambda: choose(result["value"]))
    win.bind("<Escape>", lambda _e: choose(result["value"]))
    win.bind("<Return>", lambda _e: choose(primary))

    win.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - win.winfo_reqwidth()) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - win.winfo_reqheight()) // 3
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.grab_set()
    win.focus_set()
    parent.wait_window(win)
    return result["value"]
