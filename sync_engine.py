"""
sync_engine.py
Core logic for Accurova PhotoVault Tracker:
  1. Scan one or more root folders for photoshoot subfolders
  2. Count RAW files (e.g. .NEF) and processed files (e.g. .JPG) in each,
     recursively (so nested "edited/" or "export/" subfolders still count)
  3. Parse a date out of the subfolder name for chronological sorting
  4. Push the results into a single Google Sheet, diffing against whatever is
     already there so unchanged rows are left completely untouched, changed
     rows are updated in place, and brand-new folders are inserted at the
     correct chronological position

Can be run headless from the CLI (see bottom of file) or imported and driven
by the tkinter GUI in main.py.
"""

import bisect
import json
import os
import re
import time
import urllib.parse
from datetime import datetime, date

# gspread / google-auth are only imported when actually syncing, so the
# scan-only functions still work even if those packages aren't installed yet.

HEADERS = [
    "Photoshoot Name",
    "Date",
    "Root Folder",
    "Full Path",
    "RAW Count",
    "Processed Count",
    "Ratio %",
    "Status",
    "Last Scanned",
    "Status Icon",
    "Remarks",
]

DATE_PATTERN = re.compile(r"^(\d{4})_(\d{2})_(\d{2})[\s_\-]*(.*)$")


def parse_date_from_name(folder_name: str):
    """
    Extract a date + display title from a folder name like:
        '2026_07_01 ISO test' -> (date(2026,7,1), 'ISO test')
    Returns (None, folder_name) if no leading date is found.
    """
    match = DATE_PATTERN.match(folder_name.strip())
    if not match:
        return None, folder_name
    year, month, day, rest = match.groups()
    try:
        d = date(int(year), int(month), int(day))
    except ValueError:
        return None, folder_name
    return d, (rest.strip() or folder_name)


def count_files(folder_path: str, extensions: list) -> int:
    """
    Recursively count files under folder_path whose extension (case-insensitive,
    no dot) matches one of `extensions`.
    """
    exts = {e.lower().lstrip(".") for e in extensions}
    count = 0
    for _root, _dirs, files in os.walk(folder_path):
        for fname in files:
            ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
            if ext in exts:
                count += 1
    return count


def classify(raw_count: int, processed_count: int, threshold_pct: float) -> tuple:
    """Return (ratio_pct, status_label)."""
    if raw_count == 0 and processed_count == 0:
        return 0.0, "Empty / No Photos"
    if raw_count == 0:
        return 100.0, "No RAW Found (JPG only)"
    ratio = round((processed_count / raw_count) * 100, 1)
    if processed_count == 0:
        return 0.0, "Unprocessed"
    if ratio >= threshold_pct:
        return ratio, "Fully Processed"
    return ratio, "Partially Processed"


def _record_to_json(rec: dict) -> dict:
    d = dict(rec)
    d["date"] = rec["date"].isoformat() if rec["date"] else None
    return d


def _record_from_json(d: dict) -> dict:
    rec = dict(d)
    rec["date"] = date.fromisoformat(d["date"]) if d.get("date") else None
    return rec


def save_scan_cache(records: list, cache_path: str) -> None:
    """Persist scan results to local disk, ahead of attempting the Sheets sync."""
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump([_record_to_json(r) for r in records], f, indent=2)


def load_scan_cache(cache_path: str) -> list:
    """Load the most recently cached scan, if any."""
    if not os.path.exists(cache_path):
        return []
    with open(cache_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [_record_from_json(d) for d in data]


def _with_retry(func, *args, max_retries: int = 5, base_delay: float = 15, log=print, **kwargs):
    """
    Retry a Sheets API call with exponential backoff on quota (429) or
    transient server (5xx) errors. Anything else raises immediately.
    """
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - inspecting arbitrary API exceptions
            text = str(exc)
            is_transient = any(code in text for code in ("429", "500", "502", "503"))
            if not is_transient or attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            log(f"  ! Google Sheets API hiccup ({exc.__class__.__name__}: quota/transient error), "
                f"retrying in {delay:.0f}s... (attempt {attempt + 1}/{max_retries})")
            time.sleep(delay)


def is_shoot_folder(folder_name: str) -> bool:
    """True if folder_name itself looks like a dated photoshoot (starts with YYYY_MM_DD)."""
    return DATE_PATTERN.match(folder_name.strip()) is not None


def resolve_shoot_folders(path: str, max_depth: int = 6, _depth: int = 0) -> list:
    """
    Given a folder, figure out which folder(s) beneath it are actual photoshoots
    vs. plain "container" folders (e.g. a year folder holding month folders,
    which hold the actual dated shoot folders).

    Recurses down through any folder that doesn't itself look like a dated
    shoot, however many levels deep that goes (year > month > shoot, or just
    year > shoot, etc.) - no need to manually point the app at every month.
    Bottoms out at: a folder matching YYYY_MM_DD naming, a folder with no
    subfolders left to descend into, or max_depth being reached.
    """
    name = os.path.basename(os.path.normpath(path))

    if is_shoot_folder(name):
        return [path]

    try:
        subdirs = sorted(
            os.path.join(path, f) for f in os.listdir(path)
            if os.path.isdir(os.path.join(path, f))
        )
    except OSError:
        subdirs = []

    if not subdirs or _depth >= max_depth:
        # Nothing left to descend into (or safety depth reached) - treat this
        # folder itself as the shoot rather than silently skipping it.
        return [path]

    results = []
    for sub in subdirs:
        results.extend(resolve_shoot_folders(sub, max_depth, _depth + 1))
    return results


def scan_root_folder(root_path: str, raw_exts: list, processed_exts: list,
                      threshold_pct: float, log=print, max_depth: int = 6) -> list:
    """
    Scan root_path for photoshoot folders. Immediate subfolders that already
    look like dated shoots (YYYY_MM_DD ...) are used directly; anything else
    (year folders, month folders, etc.) is treated as a container and descended
    into automatically until real shoot folders are found.
    Returns a list of record dicts.
    """
    records = []
    if not os.path.isdir(root_path):
        log(f"  ! Skipping (not a folder): {root_path}")
        return records

    immediate_subfolders = sorted(
        f for f in os.listdir(root_path)
        if os.path.isdir(os.path.join(root_path, f))
    )

    for name in immediate_subfolders:
        child_path = os.path.join(root_path, name)
        shoot_paths = resolve_shoot_folders(child_path, max_depth=max_depth)

        for shoot_path in shoot_paths:
            shoot_name = os.path.basename(os.path.normpath(shoot_path))
            raw_count = count_files(shoot_path, raw_exts)
            processed_count = count_files(shoot_path, processed_exts)
            ratio, status = classify(raw_count, processed_count, threshold_pct)
            d, _title = parse_date_from_name(shoot_name)

            records.append({
                "name": shoot_name,
                "date": d,
                "root_folder": root_path,
                "full_path": shoot_path,
                "raw_count": raw_count,
                "processed_count": processed_count,
                "ratio": ratio,
                "status": status,
                "last_scanned": datetime.now().strftime("%Y-%m-%d %H:%M"),
            })
            rel = os.path.relpath(shoot_path, root_path)
            log(f"    {rel}: {raw_count} RAW / {processed_count} processed -> {status}")

    return records


def scan_all(root_folders: list, raw_exts: list, processed_exts: list,
             threshold_pct: float, log=print) -> list:
    """Scan every root folder and return a combined, sorted list of records."""
    all_records = []
    for root in root_folders:
        log(f"Scanning: {root}")
        all_records.extend(
            scan_root_folder(root, raw_exts, processed_exts, threshold_pct, log)
        )
    return sort_records(all_records)


def sort_records(records: list) -> list:
    """Newest date first (most recent shoot at the top); undated folders sorted alphabetically at the bottom."""
    return sorted(records, key=_sort_key)


def _sort_key(rec: dict):
    # (has_no_date, -ordinal, name): dated rows always sort before undated ones;
    # within dated rows, negating the ordinal gives newest-first while keeping
    # this a plain ascending sort (needed for the bisect-based insertion below).
    ordinal = rec["date"].toordinal() if rec["date"] else 0
    return (rec["date"] is None, -ordinal, str(rec["name"]).lower())


def _records_equal_ignoring_timestamp(a: dict, b: dict) -> bool:
    """True if two records are equivalent for sheet purposes (ignores Last Scanned)."""
    fields = ("name", "date", "root_folder", "raw_count", "processed_count", "ratio", "status")
    return all(a[f] == b[f] for f in fields)


def _status_icon_formula(row_number: int) -> str:
    """
    Build a Sheets formula that shows a 🔴/🟡/🟢 icon based on the Status
    cell (column H) of the given row number.
    """
    return (
        f'=IFS(H{row_number}="Unprocessed","🔴",'
        f'H{row_number}="Partially Processed","🟡",'
        f'H{row_number}="Fully Processed","🟢",'
        f'TRUE,"")'
    )


def _full_path_hyperlink_formula(full_path: str) -> str:
    """
    Build a HYPERLINK formula so the Full Path cell is clickable and (on browsers
    that allow file:// navigation - notably NOT Chrome by default) opens the
    folder in File Explorer. The cell still displays the plain path as text
    either way, and still works as the unique key for sync diffing since Sheets
    shows the link's label text as the cell's value.
    """
    normalized = full_path.replace("\\", "/")
    encoded = urllib.parse.quote(normalized, safe="/:")
    url = "file:///" + encoded.lstrip("/")
    label = full_path.replace('"', '""')
    return f'=HYPERLINK("{url}","{label}")'


def _record_to_row(rec: dict) -> list:
    return [
        rec["name"],
        rec["date"].isoformat() if rec["date"] else "",
        rec["root_folder"],
        _full_path_hyperlink_formula(rec["full_path"]),
        rec["raw_count"],
        rec["processed_count"],
        rec["ratio"],
        rec["status"],
        rec["last_scanned"],
    ]


def _row_to_record(row: dict) -> dict:
    """Convert a Google Sheet row (dict, from get_all_records) back to our record shape.

    gspread's get_all_records() auto-converts numeric-looking cell values (e.g. a
    folder literally named "2026") into int/float, so every field is coerced back
    to its expected type here rather than trusted as-is.
    """
    raw_date = row.get("Date")
    d = None
    if raw_date:
        try:
            d = datetime.strptime(str(raw_date), "%Y-%m-%d").date()
        except ValueError:
            d = None

    def _to_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _to_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    return {
        "name": str(row.get("Photoshoot Name", "")),
        "date": d,
        "root_folder": str(row.get("Root Folder", "")),
        "full_path": str(row.get("Full Path", "")),
        "raw_count": _to_int(row.get("RAW Count", 0)),
        "processed_count": _to_int(row.get("Processed Count", 0)),
        "ratio": _to_float(row.get("Ratio %", 0)),
        "status": str(row.get("Status", "")),
        "last_scanned": str(row.get("Last Scanned", "")),
    }


def get_worksheet(sheet_id: str, oauth_client_secret_path: str, oauth_token_path: str = None):
    """
    Open (or create) the first worksheet of the target Google Sheet, authenticating
    as the user via OAuth (Desktop app flow) rather than a service account key.

    On first run this opens a browser window asking you to sign in and grant access;
    after that it reuses the cached token at `oauth_token_path` and refreshes silently.
    """
    import gspread

    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")

    if client_id and client_secret:
        # Credentials from the environment (preferred): no secret JSON file needed.
        client_config = {"installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }}
        token_info = None
        if oauth_token_path and os.path.exists(oauth_token_path):
            with open(oauth_token_path, "r", encoding="utf-8") as f:
                token_info = json.load(f)
        client, token_info = gspread.oauth_from_dict(client_config, authorized_user_info=token_info)
        if oauth_token_path:
            os.makedirs(os.path.dirname(oauth_token_path), exist_ok=True)
            with open(oauth_token_path, "w", encoding="utf-8") as f:
                json.dump(token_info, f)
    else:
        kwargs = {"credentials_filename": oauth_client_secret_path}
        if oauth_token_path:
            kwargs["authorized_user_filename"] = oauth_token_path
        client = gspread.oauth(**kwargs)
    sheet = client.open_by_key(sheet_id)
    worksheet = sheet.sheet1
    return worksheet


def sync_to_sheet(worksheet, new_records: list, log=print, bulk_insert_threshold: int = 25) -> None:
    """
    Incrementally sync new_records into the sheet:
      - Rows whose data hasn't changed are left completely untouched (not
        even the Last Scanned timestamp is rewritten).
      - Rows whose counts/status changed are updated in place, same row.
      - Brand-new photoshoot folders are inserted at the correct chronological
        position; Sheets shifts and re-adjusts other rows/formulas natively,
        so their cell content is never rewritten by this app.
      - If there's a LARGE batch of new folders (more than
        `bulk_insert_threshold`), they're written in a single bulk rewrite
        instead of one API call per row - inserting one row at a time for a
        big backlog (e.g. an initial import) can blow through Google's
        per-minute write-request quota very fast.
      - Rows for folders not included in this scan run (e.g. other root
        folders scanned in a previous run) are left alone entirely.
      - The Remarks column (far right) is never overwritten with blank text
        after its row is first created, so anything you type there is always
        preserved - including across a bulk rewrite.
      - Transient/quota (429/5xx) errors from the Sheets API are retried
        automatically with exponential backoff.
    """
    existing_values = _with_retry(worksheet.get_all_values, log=log)

    needs_full_init = (not existing_values) or (existing_values[0] != HEADERS)
    if needs_full_init:
        if existing_values:
            log("Sheet header doesn't match the expected format - rebuilding once to normalize it.")
        _full_rewrite(worksheet, new_records, log)
        return

    # Map existing sheet rows (by Full Path) to their row number + parsed record + remarks.
    remarks_col = HEADERS.index("Remarks")
    existing_by_key = {}
    for i, row_values in enumerate(existing_values[1:]):
        row_number = i + 2  # header is row 1
        if not any(cell.strip() for cell in row_values):
            continue
        padded = row_values + [""] * (len(HEADERS) - len(row_values))
        row_dict = dict(zip(HEADERS, padded))
        rec = _row_to_record(row_dict)
        if rec["full_path"]:
            existing_by_key[rec["full_path"]] = {
                "row_number": row_number,
                "record": rec,
                "remarks": padded[remarks_col],
            }

    # --- Step 1: update rows whose data actually changed, in place ---
    update_batch = []
    changed_count = 0
    overlap_count = 0
    for rec in new_records:
        key = rec["full_path"]
        if key in existing_by_key:
            overlap_count += 1
            old_rec = existing_by_key[key]["record"]
            if not _records_equal_ignoring_timestamp(rec, old_rec):
                row_number = existing_by_key[key]["row_number"]
                update_batch.append({
                    "range": f"A{row_number}:I{row_number}",
                    "values": [_record_to_row(rec)],
                })
                changed_count += 1
                existing_by_key[key]["record"] = rec  # keep local model in sync

    if update_batch:
        _with_retry(worksheet.batch_update, update_batch, value_input_option="USER_ENTERED", log=log)

    new_only = [r for r in new_records if r["full_path"] not in existing_by_key]
    new_only.sort(key=_sort_key)

    unchanged_count = overlap_count - changed_count

    # --- Step 2a: large batch of new folders -> one bulk rewrite (avoids per-row API quota burn) ---
    if len(new_only) > bulk_insert_threshold:
        log(f"{len(new_only)} new folder(s) found - writing them in a single bulk update "
            f"instead of {len(new_only)} separate API calls (keeps this within Google's write-quota limits).")
        total = _bulk_rewrite_preserving_remarks(worksheet, existing_by_key, new_only, log)
        log(f"{changed_count} row(s) updated, {unchanged_count} unchanged row(s) preserved, "
            f"{len(new_only)} new row(s) added via bulk rewrite ({total} total rows).")
        log("Done.")
        return

    # --- Step 2b: small batch -> insert one at a time at the correct chronological spot ---
    order_state = sorted(existing_by_key.items(), key=lambda kv: kv[1]["row_number"])
    order_sort_keys = [_sort_key(v["record"]) for _, v in order_state]

    inserted_count = 0
    for rec in new_only:
        skey = _sort_key(rec)
        idx = bisect.bisect_right(order_sort_keys, skey)
        target_row = idx + 2  # header offset
        icon_formula = _status_icon_formula(target_row)
        _with_retry(
            worksheet.insert_rows,
            [_record_to_row(rec) + [icon_formula, ""]],  # trailing "" = blank Remarks cell
            row=target_row,
            value_input_option="USER_ENTERED",
            log=log,
        )
        order_sort_keys.insert(idx, skey)
        inserted_count += 1

    log(f"{changed_count} row(s) updated, {unchanged_count} unchanged row(s) left untouched, "
        f"{inserted_count} new row(s) inserted.")
    log("Done.")


def _bulk_rewrite_preserving_remarks(worksheet, existing_by_key: dict, new_only: list, log=print) -> int:
    """
    Rewrite the whole sheet in one shot (used for large batches of new folders),
    while preserving every existing row's Remarks text exactly as-is.
    """
    combined = [(info["record"], info.get("remarks", "")) for info in existing_by_key.values()]
    combined.extend((rec, "") for rec in new_only)
    combined.sort(key=lambda pair: _sort_key(pair[0]))

    rows = [HEADERS]
    for i, (rec, remarks) in enumerate(combined):
        row_number = i + 2
        rows.append(_record_to_row(rec) + [_status_icon_formula(row_number), remarks])

    _with_retry(worksheet.clear, log=log)
    _with_retry(worksheet.update, "A1", rows, value_input_option="USER_ENTERED", log=log)
    return len(combined)


def _full_rewrite(worksheet, new_records: list, log=print) -> None:
    """One-time full rebuild - only used when the sheet is empty or has an unrecognized header."""
    final_records = sort_records(new_records)
    rows = [HEADERS]
    for i, rec in enumerate(final_records):
        row_number = i + 2
        rows.append(_record_to_row(rec) + [_status_icon_formula(row_number), ""])
    _with_retry(worksheet.clear, log=log)
    _with_retry(worksheet.update, "A1", rows, value_input_option="USER_ENTERED", log=log)
    log(f"Initialized sheet with {len(final_records)} row(s).")


def run_full_sync(root_folders: list, sheet_id: str, oauth_client_secret_path: str,
                   raw_exts: list, processed_exts: list,
                   threshold_pct: float = 90, log=print,
                   oauth_token_path: str = None, scan_cache_path: str = None) -> None:
    """
    Scan everything, cache the results to local disk (so a failed/slow Sheets
    sync never loses the scan), then push to the sheet.
    """
    records = scan_all(root_folders, raw_exts, processed_exts, threshold_pct, log)
    log(f"Scanned {len(records)} photoshoot folders total.")

    if scan_cache_path:
        try:
            save_scan_cache(records, scan_cache_path)
            log(f"Scan cached locally at {scan_cache_path} - safe even if the sync below fails "
                f"(use 'Retry Last Sync' to resume without re-scanning).")
        except OSError as exc:
            log(f"Warning: could not write local scan cache ({exc}).")

    log("Connecting to Google Sheets...")
    log("(First run will open a browser window to sign in and authorize access.)")
    worksheet = get_worksheet(sheet_id, oauth_client_secret_path, oauth_token_path)
    sync_to_sheet(worksheet, records, log)


def sync_cached_scan(sheet_id: str, oauth_client_secret_path: str, scan_cache_path: str,
                      log=print, oauth_token_path: str = None) -> None:
    """
    Retry syncing the most recently cached scan without re-scanning the
    filesystem - use this after a sync failure (e.g. a quota error) so you
    don't have to wait through a full re-scan of your drives again.
    """
    records = load_scan_cache(scan_cache_path)
    if not records:
        log("No cached scan found at that path - run a normal scan first.")
        return
    log(f"Loaded {len(records)} cached photoshoot record(s) from {scan_cache_path}.")
    log("Connecting to Google Sheets...")
    worksheet = get_worksheet(sheet_id, oauth_client_secret_path, oauth_token_path)
    sync_to_sheet(worksheet, records, log)


if __name__ == "__main__":
    # Minimal CLI usage for scheduling via cron / Task Scheduler, e.g.:
    #   python sync_engine.py
    # Reads settings from config_manager instead of argv for simplicity.
    from config_manager import load_config

    cfg = load_config()
    from config_manager import env_credentials_available

    if (not cfg["root_folders"] or not cfg["sheet_id"]
            or not (cfg["oauth_client_secret_path"] or env_credentials_available())):
        print("Config incomplete. Run main.py once to set folders, sheet ID, and OAuth client secret.")
    else:
        run_full_sync(
            cfg["root_folders"],
            cfg["sheet_id"],
            cfg["oauth_client_secret_path"],
            cfg["raw_extensions"],
            cfg["processed_extensions"],
            cfg.get("fully_processed_threshold", 90),
            oauth_token_path=cfg.get("oauth_token_path"),
            scan_cache_path=cfg.get("scan_cache_path"),
        )
