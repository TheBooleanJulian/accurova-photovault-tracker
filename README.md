<div align="center">

# Accurova PhotoVault Tracker

**A desktop app that scans your PhotoVault-style folders and keeps a Google Sheet of RAW-vs-processed shoot progress up to date.**

![Python](https://img.shields.io/badge/-Python-3776AB?logo=python&logoColor=white)
![Tkinter](https://img.shields.io/badge/-Tkinter-3776AB)
![Google Sheets](https://img.shields.io/badge/-Google%20Sheets-34A853?logo=googlesheets&logoColor=white)
![License](https://img.shields.io/badge/license-AGPLv3%20%2B%20Commercial-00D4C8.svg)

</div>

---

**Current version: v1.8.0**

## What it does

Accurova PhotoVault Tracker scans your photoshoot folders, counts RAW vs processed files in each subfolder, and keeps a single Google Sheet up to date with a chronological log of every shoot — flagged as **Fully Processed**, **Partially Processed**, or **Unprocessed** based on the RAW-to-JPG ratio.

It's built to match the folder pattern you already use:
```
2026_07_01 ISO test/
2026_07_02 BNI Crescendo Novena/
2026_07_22 Connect Society Bukit Merah/
```
Each immediate subfolder of a root folder = one row in the sheet. Files are counted recursively within each subfolder, so it doesn't matter if your NEFs and JPGs live in nested folders (e.g. `raw/` and `edited/`).

You can point the app at a year (or drive root) folder directly. If a subfolder doesn't itself look like a dated shoot (`YYYY_MM_DD ...`), the app treats it as a container and automatically keeps descending into it until it finds the actual shoot folders, however many levels deep that goes.

## Features

- Recursive RAW/processed file counting per shoot subfolder
- Recursive container-folder detection — point it at a whole year or drive and it finds the shoot folders itself
- Google Sheets sync with a clickable `HYPERLINK("file:///...")` Full Path column
- Newest-shoot-first sorting, with a preserved manual `Remarks` column
- Moved/relocated folder detection — updates the existing row in place instead of creating an orphan + duplicate
- Incremental sync — unchanged rows untouched, changed rows updated in place, new folders inserted at the correct position
- Local scan cache written before every Sheets sync, so a failed sync never loses data, plus a "Retry Last Sync" button
- Bulk-write fallback and automatic retry-with-backoff for Google's per-minute write-quota limits
- OAuth (Desktop app) sign-in — no service-account key file, no org policy conflict
- Configurable RAW/processed extensions and "Fully Processed" ratio threshold
- Headless re-scan mode (`sync_engine.py`) for cron/Task Scheduler automation

## Tech Stack

| Layer | Choice |
|---|---|
| UI | Tkinter (desktop GUI) |
| Sheets/Drive | gspread + google-auth + google-auth-oauthlib |
| Auth | OAuth 2.0 (Desktop app flow) |
| Config/cache | Local JSON files under `~/.photovault_tracker/` |

## Screenshots

_Screenshots coming soon._ The app is a native Tkinter window with an "Add Folder...", Sheet ID/URL field, and a scan log panel.

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```
(tkinter ships with standard Python on Windows/macOS; on Linux install `python3-tk` via your package manager if it's missing.)

### 2. Create a Google Cloud OAuth Client (Desktop app)

Many orgs now block service-account **key** creation (`iam.disableServiceAccountKeyCreation`), so this app authenticates as *you* instead, via OAuth — no key file, no org policy conflict.

1. Create (or pick) a project at https://console.cloud.google.com/.
2. Enable **Google Sheets API** and **Google Drive API** for that project.
3. Go to **APIs & Services → OAuth consent screen**, choose **External** (or Internal on a Workspace org), fill in the required fields, and add yourself as a **Test user** if prompted.
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID** — Application type: **Desktop app**.
5. Copy the **Client ID** and **Client secret** into a `.env` file next to `main.py` (copy `.env.example`):
   ```
   GOOGLE_OAUTH_CLIENT_ID=...
   GOOGLE_OAUTH_CLIENT_SECRET=...
   ```
   Real environment variables take priority over `.env`. `.env` is gitignored — never commit it.

   Fallback: instead of `.env`, click **Download JSON** and point the app's **OAuth Client Secret JSON** field at it (keep that file out of the repo; it is gitignored as `client_secret.json`).

### 3. Point the app at your Google Sheet
Create (or open) the Google Sheet you want as your master tracker, and copy its ID or URL.

### 4. Run it
Double-click `run.bat`, or:
```bash
python main.py
```
In the window: **Add Folder...**, paste the **Sheet ID or URL**, (skip the **OAuth Client Secret JSON** field if you're using `.env`), adjust RAW/Processed extensions and the "Fully Processed" threshold if needed (defaults: `nef` / `jpg, jpeg` / `90%`), **Save Settings**, then **Scan & Sync Now**. **Open Sheet** opens the tracker sheet in your browser. On first sync, a browser window opens to sign in and grant Sheets/Drive access — approved once, then cached.

### Optional: automate it (no GUI)
Once you've run the app once and clicked **Save Settings**:
```bash
python sync_engine.py
```
This reads the same saved settings from `~/.photovault_tracker/config.json`, so it can be triggered headlessly via Task Scheduler, cron, or a Zeabur cron job.

## Notes / things worth knowing

- **"Fully Processed" is an approximation.** Lower the threshold in the app (e.g. to 40–60%) if a 1:1 RAW-to-JPG ratio doesn't match your actual culling ratio.
- **Extensions are configurable** — add `.CR2`/`.ARW`/`.TIFF`/`.PNG` etc. in the Options section.
- **Nothing is uploaded except folder names and file counts.** The app never reads or transmits actual photo content.

## Status / Roadmap

- [x] Folder scanning, RAW vs. processed counting, Google Sheets sync
- [x] OAuth (Desktop app) authentication
- [x] Incremental sync (update-in-place, no full rewrite)
- [x] Clickable Full Path links, newest-first sort, preserved Remarks column
- [x] Recursive container-folder detection (year/drive-root scanning)
- [x] Local scan cache + Retry Last Sync + bulk-write fallback + retry-with-backoff
- [x] Moved/relocated folder detection
- [ ] Scheduled auto-runs built into the app
- [ ] Dry-run / preview mode before writing to the sheet
- [ ] Per-root extension/threshold overrides
- [ ] True orphan cleanup (flag, not auto-delete)

Further ideas (summary tab, standalone `.exe` build, CSV/Excel export, duplicate-name warnings, thumbnail previews, multi-user support) are tracked as longer-term, uncommitted possibilities.

## Changelog

Versioned as `MAJOR.MINOR.PATCH`: **MAJOR** = a workflow or config-breaking change, **MINOR** = a new feature, **PATCH** = a bug fix with no new behavior.

- **v1.9.0** — Renamed to Accurova PhotoVault Tracker; OAuth client credentials now load from environment / `.env` first (JSON file is a fallback); added `run.bat` and an **Open Sheet** button
- **v1.8.0** — Prepopulated RAW/Processed extension fields with common formats across camera brands by default
- **v1.7.0** — Added moved/relocated folder detection
- **v1.6.1** — Fixed a crash (`NameError: is_shoot_folder`) from a dropped function definition
- **v1.6.0** — Added local scan cache, Retry Last Sync button, bulk-write fallback, and automatic retry-with-backoff for quota errors
- **v1.5.0** — Added recursive container-folder detection (year/drive-root scanning)
- **v1.4.0** — Clickable Full Path `HYPERLINK` formula, newest-shoot-first sort, added the Remarks column
- **v1.3.0** — Rewrote the sync engine to be incremental instead of clear-and-rewrite
- **v1.2.0** — Added the Status Icon column (🔴/🟡/🟢) via an in-sheet formula
- **v1.1.1** — Fixed a crash from Google Sheets auto-typing numeric-looking folder names as integers
- **v1.1.0** — Switched authentication from a service-account key to OAuth (Desktop app) sign-in
- **v1.0.0** — Initial release: tkinter GUI, folder scanning, RAW vs. processed counting, Google Sheets sync

## Feedback & Bug Reports

Found a bug, or have an idea for the roadmap above? Submit it here:
https://forms.gle/qRCimSyoosWyNwXdA

## License

This project is dual licensed.

- Community Edition — [GNU Affero General Public License v3 (AGPLv3)](LICENSE). Free to use, modify, and self-host. If you distribute a modified version or run it as a network service, you must make the corresponding source available.
- Commercial License — for organisations that want to embed, modify, or distribute this software without AGPLv3's obligations. See [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md).

---

<div align="center">
<sub>Built by <a href="https://github.com/TheBooleanJulian">@TheBooleanJulian</a></sub>
</div>
