# Personal Expense Tracker

Double-click **run_tracker.bat** to launch the desktop app. It uses Python 3.8
or newer with Tkinter and needs no extra packages. You can also run
`python tracker.py`.

## Add, edit, and find expenses

- Enter a name, an amount such as `125.50` or `₱1,250.00`, and a category.
  Enter a purchase date as `YYYY-MM-DD`, or leave it blank for today.
  Click **Add expense** or press Enter in a text field.
- Select a row and click **Edit selected expense** to update it. Click
  **Save changes** to finish or **Cancel edit** to discard the form changes.
  **Delete selected expense** asks for confirmation before saving the deletion.
- Set either date bound or choose a category, then click **Apply**. Both dates
  are inclusive. The filtered total reflects the rows on screen. Click
  **Clear** to see all expenses again.
- **Export CSV** saves the displayed rows. Clear the filters first to export
  the full list.

## Storage and recovery

The app saves immediately to
`%LOCALAPPDATA%\Personal Expense Tracker\expenses.json`. On first launch
with no data file or backup there, the app copies and validates the old
`expenses.json` beside the app if present. That original file stays in place.
New changes go to the Windows data folder. Amounts are stored as integer
centavos for exact totals. Only one instance can open the data at a time.

Before saving a change, the app writes the previous list to
`expenses.backup.json` in the same folder. **Restore backup** replaces the
current list with that copy after confirmation. It can also recover a missing
or unreadable primary file. This backup holds one previous version. Keep a
separate copy of the active JSON file if you want to retain older versions.
