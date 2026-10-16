"""
Accurova PhotoVault Tracker
-------------------
Desktop app (tkinter) that scans one or more root folders full of photoshoot
subfolders (e.g. "2026_07_01 ISO test"), counts RAW (.NEF) vs processed
(.JPG) files in each, and syncs the results into a single Google Sheet -
sorted chronologically, with a rough "Fully / Partially / Unprocessed"
status per shoot.

Run with:  python main.py
Requires:  pip install gspread google-auth
See README.md for full setup instructions (Google Cloud service account etc).
"""

import re
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import config_manager
import sync_engine

SHEET_ID_PATTERN = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]+)")


def extract_sheet_id(text: str) -> str:
    """Accept either a raw Sheet ID or a full Google Sheets URL."""
    text = text.strip()
    match = SHEET_ID_PATTERN.search(text)
    return match.group(1) if match else text


class PhotoVaultTrackerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Accurova PhotoVault Tracker")
        self.root.geometry("760x640")
        self.root.minsize(680, 560)

        self.config = config_manager.load_config()

        self._build_ui()
        self._load_config_into_ui()

    # ---------------------------------------------------------------- UI --
    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        # --- Root folders ---
        folders_frame = ttk.LabelFrame(self.root, text="Root Folders to Scan")
        folders_frame.pack(fill="x", **pad)

        self.folders_listbox = tk.Listbox(folders_frame, height=5, selectmode="extended")
        self.folders_listbox.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)

        scrollbar = ttk.Scrollbar(folders_frame, orient="vertical", command=self.folders_listbox.yview)
        scrollbar.pack(side="left", fill="y", pady=10)
        self.folders_listbox.config(yscrollcommand=scrollbar.set)

        btns_frame = ttk.Frame(folders_frame)
        btns_frame.pack(side="left", fill="y", padx=10, pady=10)
        ttk.Button(btns_frame, text="Add Folder...", command=self._add_folder).pack(fill="x", pady=2)
        ttk.Button(btns_frame, text="Remove Selected", command=self._remove_folder).pack(fill="x", pady=2)

        # --- Google Sheet settings ---
        sheet_frame = ttk.LabelFrame(self.root, text="Google Sheet")
        sheet_frame.pack(fill="x", **pad)

        ttk.Label(sheet_frame, text="Sheet ID or URL:").grid(row=0, column=0, sticky="w", padx=10, pady=6)
        self.sheet_id_var = tk.StringVar()
        ttk.Entry(sheet_frame, textvariable=self.sheet_id_var).grid(row=0, column=1, sticky="ew", padx=10, pady=6)
        ttk.Button(sheet_frame, text="Open Sheet", command=self._open_sheet).grid(row=0, column=2, padx=10)

        ttk.Label(sheet_frame, text="OAuth Client Secret JSON:").grid(row=1, column=0, sticky="w", padx=10, pady=6)
        self.creds_path_var = tk.StringVar()
        ttk.Entry(sheet_frame, textvariable=self.creds_path_var).grid(row=1, column=1, sticky="ew", padx=10, pady=6)
        ttk.Button(sheet_frame, text="Browse...", command=self._browse_credentials).grid(row=1, column=2, padx=10)

        ttk.Label(
            sheet_frame,
            text="First sync opens a browser to sign in with your Google account - no service account needed.",
            foreground="#666666",
            font=("TkDefaultFont", 8),
        ).grid(row=2, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 6))

        sheet_frame.columnconfigure(1, weight=1)

        # --- Options ---
        options_frame = ttk.LabelFrame(self.root, text="Options")
        options_frame.pack(fill="x", **pad)

        ttk.Label(options_frame, text="RAW extensions (comma-separated):").grid(row=0, column=0, sticky="w", padx=10, pady=6)
        self.raw_ext_var = tk.StringVar()
        ttk.Entry(options_frame, textvariable=self.raw_ext_var, width=25).grid(row=0, column=1, sticky="w", padx=10, pady=6)

        ttk.Label(options_frame, text="Processed extensions (comma-separated):").grid(row=1, column=0, sticky="w", padx=10, pady=6)
        self.processed_ext_var = tk.StringVar()
        ttk.Entry(options_frame, textvariable=self.processed_ext_var, width=25).grid(row=1, column=1, sticky="w", padx=10, pady=6)

        ttk.Label(options_frame, text="'Fully Processed' threshold (%):").grid(row=2, column=0, sticky="w", padx=10, pady=6)
        self.threshold_var = tk.StringVar()
        ttk.Entry(options_frame, textvariable=self.threshold_var, width=10).grid(row=2, column=1, sticky="w", padx=10, pady=6)

        # --- Actions ---
        actions_frame = ttk.Frame(self.root)
        actions_frame.pack(fill="x", **pad)
        ttk.Button(actions_frame, text="Save Settings", command=self._save_config).pack(side="left", padx=(0, 8))
        self.scan_button = ttk.Button(actions_frame, text="Scan & Sync Now", command=self._run_scan_thread)
        self.scan_button.pack(side="left", padx=(0, 8))
        self.retry_button = ttk.Button(actions_frame, text="Retry Last Sync (no rescan)", command=self._run_retry_thread)
        self.retry_button.pack(side="left")

        # --- Log ---
        log_frame = ttk.LabelFrame(self.root, text="Log")
        log_frame.pack(fill="both", expand=True, **pad)
        self.log_box = scrolledtext.ScrolledText(log_frame, height=14, state="disabled", wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=10, pady=10)

    # ----------------------------------------------------------- helpers --
    def _load_config_into_ui(self):
        for folder in self.config["root_folders"]:
            self.folders_listbox.insert("end", folder)
        self.sheet_id_var.set(self.config["sheet_id"])
        self.creds_path_var.set(self.config["oauth_client_secret_path"])
        self.raw_ext_var.set(", ".join(self.config["raw_extensions"]))
        self.processed_ext_var.set(", ".join(self.config["processed_extensions"]))
        self.threshold_var.set(str(self.config.get("fully_processed_threshold", 90)))

    def _add_folder(self):
        folder = filedialog.askdirectory(title="Select a root folder containing photoshoot subfolders")
        if folder:
            current = self.folders_listbox.get(0, "end")
            if folder not in current:
                self.folders_listbox.insert("end", folder)

    def _remove_folder(self):
        for index in reversed(self.folders_listbox.curselection()):
            self.folders_listbox.delete(index)

    def _open_sheet(self):
        sheet_id = extract_sheet_id(self.sheet_id_var.get())
        if not sheet_id:
            messagebox.showwarning("Missing Sheet ID", "Enter a Google Sheet ID or URL first.")
            return
        webbrowser.open(f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit")

    def _browse_credentials(self):
        path = filedialog.askopenfilename(
            title="Select OAuth Client Secret JSON (Desktop app type)",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.creds_path_var.set(path)

    def _log(self, message: str):
        self.log_box.config(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")
        self.log_box.update_idletasks()

    def _gather_settings(self):
        folders = list(self.folders_listbox.get(0, "end"))
        sheet_id = extract_sheet_id(self.sheet_id_var.get())
        creds_path = self.creds_path_var.get().strip()
        raw_exts = [e.strip() for e in self.raw_ext_var.get().split(",") if e.strip()]
        processed_exts = [e.strip() for e in self.processed_ext_var.get().split(",") if e.strip()]
        try:
            threshold = float(self.threshold_var.get())
        except ValueError:
            threshold = 90.0
        return {
            "root_folders": folders,
            "sheet_id": sheet_id,
            "oauth_client_secret_path": creds_path,
            "oauth_token_path": self.config.get("oauth_token_path", config_manager.DEFAULT_CONFIG["oauth_token_path"]),
            "scan_cache_path": self.config.get("scan_cache_path", config_manager.DEFAULT_CONFIG["scan_cache_path"]),
            "raw_extensions": raw_exts or config_manager.DEFAULT_CONFIG["raw_extensions"],
            "processed_extensions": processed_exts or config_manager.DEFAULT_CONFIG["processed_extensions"],
            "fully_processed_threshold": threshold,
        }

    def _save_config(self):
        settings = self._gather_settings()
        config_manager.save_config(settings)
        self.config = settings
        messagebox.showinfo("Saved", "Settings saved.")

    # -------------------------------------------------------------- run --
    def _run_scan_thread(self):
        settings = self._gather_settings()

        if not settings["root_folders"]:
            messagebox.showwarning("Missing folders", "Add at least one root folder to scan.")
            return
        if not settings["sheet_id"]:
            messagebox.showwarning("Missing Sheet ID", "Enter a Google Sheet ID or URL.")
            return
        if not settings["oauth_client_secret_path"] and not config_manager.env_credentials_available():
            messagebox.showwarning("Missing credentials", "Set GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET in .env, or select your OAuth Client Secret JSON file.")
            return

        # Persist settings for next time
        config_manager.save_config(settings)
        self.config = settings

        self.scan_button.config(state="disabled")
        self.retry_button.config(state="disabled")
        self._log("=" * 60)
        self._log("Starting scan...")

        thread = threading.Thread(target=self._run_scan, args=(settings,), daemon=True)
        thread.start()

    def _run_scan(self, settings):
        try:
            sync_engine.run_full_sync(
                settings["root_folders"],
                settings["sheet_id"],
                settings["oauth_client_secret_path"],
                settings["raw_extensions"],
                settings["processed_extensions"],
                settings["fully_processed_threshold"],
                log=self._log,
                oauth_token_path=settings["oauth_token_path"],
                scan_cache_path=settings["scan_cache_path"],
            )
            self._log("Sync complete. Google Sheet is up to date.")
        except Exception as exc:  # noqa: BLE001 - surface any error to the log/user
            self._log(f"ERROR: {exc}")
            self._log("Your scan results were cached locally before this error, if it got that far - "
                       "use 'Retry Last Sync' to push them without re-scanning your drives.")
            messagebox.showerror("Sync failed", str(exc))
        finally:
            self.scan_button.config(state="normal")
            self.retry_button.config(state="normal")

    def _run_retry_thread(self):
        settings = self._gather_settings()

        if not settings["sheet_id"]:
            messagebox.showwarning("Missing Sheet ID", "Enter a Google Sheet ID or URL.")
            return
        if not settings["oauth_client_secret_path"] and not config_manager.env_credentials_available():
            messagebox.showwarning("Missing credentials", "Set GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET in .env, or select your OAuth Client Secret JSON file.")
            return

        config_manager.save_config(settings)
        self.config = settings

        self.scan_button.config(state="disabled")
        self.retry_button.config(state="disabled")
        self._log("=" * 60)
        self._log("Retrying sync from last cached scan (no rescan)...")

        thread = threading.Thread(target=self._run_retry, args=(settings,), daemon=True)
        thread.start()

    def _run_retry(self, settings):
        try:
            sync_engine.sync_cached_scan(
                settings["sheet_id"],
                settings["oauth_client_secret_path"],
                settings["scan_cache_path"],
                log=self._log,
                oauth_token_path=settings["oauth_token_path"],
            )
            self._log("Retry sync complete. Google Sheet is up to date.")
        except Exception as exc:  # noqa: BLE001
            self._log(f"ERROR: {exc}")
            messagebox.showerror("Retry failed", str(exc))
        finally:
            self.scan_button.config(state="normal")
            self.retry_button.config(state="normal")


def main():
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
    except tk.TclError:
        pass
    app = PhotoVaultTrackerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
