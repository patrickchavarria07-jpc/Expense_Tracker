# Personal Expense Tracker

Double-click **run_tracker.bat** to launch the dark-mode desktop app.
Requires Python 3 with Tkinter (included with the standard Windows Python installer).
No extra packages are needed. You can also run `python tracker.py`.

Enter an expense name, a positive PHP amount with up to two decimal places,
and a category, then click **Add expense** or press Enter. The list shows newest
entries first. Select an entry and click **Delete selected expense** to remove it.

Changes are saved immediately to `expenses.json` next to the app. Keep that file
to retain your history, or copy it as a backup. Amounts are stored as integer
centavos for exact totals. Run one instance of the app at a time.

If saving fails, the app reports the error and keeps the displayed entries unchanged.
If an existing data file cannot be read, the app preserves it and disables edits;
fix or rename the file and reopen the app to continue.
