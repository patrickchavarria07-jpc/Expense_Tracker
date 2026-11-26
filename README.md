# Personal Expense Tracker

Double-click **run_tracker.bat** to launch the desktop app (Windows). It uses
Python 3.8 or newer with Tkinter and needs no extra packages. You can also run
`python tracker.py`.

## Install (non-Windows)

Tkinter is part of standard Python on Windows/macOS. On Debian/Ubuntu:

```sh
sudo apt install python3-tk
python3 tracker.py
```

On macOS, install Python from python.org (includes Tkinter) or `brew install python-tk`.

## Add, edit, and find expenses

- Enter a name, an amount such as `125.50` or `₱1,250.00`, and a category.
  Enter a purchase date as `YYYY-MM-DD`, or leave it blank for today.
  Click **Add expense** or press Enter in a text field.
- Select a row and click **Edit selected expense** (or double-click the row)
  to update it. Click **Save changes** to finish or **Cancel edit** (or press
  Escape) to discard the form changes. **Delete selected expense** (or press
  Delete) asks for confirmation before saving the deletion.
- Set either date bound, choose a category, or type a name search, then click
  **Apply** (or press Enter in a filter field). Both dates are inclusive. The
  filtered total reflects the rows on screen. Click **Clear** to see all
  expenses again. Adding an expense while filtered clears the filters so the
  new row is visible.
- Click a column heading (Date, Expense, Category, Amount) to sort; click
  again to reverse. The default order is latest additions first.
- **Export CSV** saves the displayed rows. Clear the filters first to export
  the full list. **Import CSV** adds rows from a CSV with Date, Expense,
  Category, Amount (PHP) columns (the format produced by Export).

## Storage and recovery

The app saves immediately to
`%LOCALAPPDATA%\Personal Expense Tracker\expenses.json` on Windows, or
`~/.local/share/Personal Expense Tracker/expenses.json` on Linux/macOS.
On first launch with no data file or backup there, the app copies and
validates the old `expenses.json` beside the app if present. That original
file stays in place. New changes go to the per-user data folder. Amounts are
stored as integer centavos for exact totals. Only one instance can open the
data at a time (a `tracker.lock` file enforces this; the lock is advisory,
so don't edit the JSON in another editor while the app is open — the app
detects external changes and asks before overwriting).

Before saving a change, the app writes the previous list to
`expenses.backup.json` in the same folder. **Restore backup** replaces the
current list with that copy after confirmation. Your current list is first
saved as the new backup, so restoring again undoes the restore. It can also
recover a missing or unreadable primary file. This backup holds one previous
version. Keep a separate copy of the active JSON file if you want to retain
older versions.

If the file was changed outside the app, the next save asks whether to reload
from disk or overwrite. If the app reports storage unavailable, your existing
file is preserved — use **Restore backup** if available, or repair the file
and reopen the app.

## File format

`expenses.json` is a JSON list of objects:

```json
[{"id": "…", "name": "Jan", "centavos": 50000, "category": "Food", "date": "2026-11-20 17:55"}]
```

- `id`: unique non-empty string (UUID hex for new entries).
- `name`: non-empty, no newlines.
- `centavos`: positive integer ≤ 99999999999 (₱999,999,999.99).
- `category`: one of Food, Bills, Transport, Shopping, Other.
- `date`: `YYYY-MM-DD HH:MM` (editing a date keeps the original time).

Amounts in the UI accept `125.50`, `₱1,250.00`, `.50`, etc. (up to two
decimals, ₱0.01–₱999,999,999.99). Dates must be `YYYY-MM-DD`.

## Troubleshooting

- **"Tkinter is not available"**: reinstall Python with Tcl/Tk, or install
  the OS package (`python3-tk` on Debian/Ubuntu).
- **"Could not open Tracker"**: another Tracker window is already open. Close
  it and try again.
- **"Could not load expenses"**: the JSON is corrupt or a directory sits where
  the file should be. The file was left untouched. Use **Restore backup** if
  enabled, or fix the file manually and reopen.
- **Log file**: `tracker.log` in the data folder records errors for debugging.

## Development

```sh
python -m py_compile tracker.py
python -m unittest discover -s tests -v
```

No third-party dependencies; Python 3.8+ with Tkinter.
