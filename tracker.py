"""A small, local-only personal expense tracker. Run with Python 3."""

import csv
import json
import logging
import os
import re
import sys
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    TK_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised on systems without Tkinter
    tk = None  # type: ignore[assignment]
    filedialog = None  # type: ignore[assignment]
    messagebox = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]
    TK_AVAILABLE = False


__version__ = "1.1.0"
logger = logging.getLogger(__name__)

MAX_CENTAVOS = 99999999999  # ₱999,999,999.99 in centavos
MAX_AMOUNT = Decimal("999999999.99")


def _default_data_dir():
    """Return the per-user data directory, tolerating a missing HOME."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Personal Expense Tracker"
    try:
        home = Path.home()
    except RuntimeError:
        home = Path.cwd()
    return home / ".local" / "share" / "Personal Expense Tracker"


LEGACY_FILE = Path(__file__).resolve().with_name("expenses.json")
DATA_DIR = _default_data_dir()
DATA_FILE = DATA_DIR / "expenses.json"
BACKUP_FILE = DATA_DIR / "expenses.backup.json"
LOCK_FILE = DATA_DIR / "tracker.lock"
CATEGORIES = ("Food", "Bills", "Transport", "Shopping", "Other")
BG, PANEL, TEXT, MUTED, ACCENT = "#111827", "#1f2937", "#f3f4f6", "#9ca3af", "#60a5fa"


def _file_signature(path):
    """Return (mtime_ns, size) for change detection, or None if missing."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _is_same_path(a, b):
    """Case-insensitive, symlink-aware path equality (Windows-safe)."""
    try:
        if a.exists() and b.exists() and os.path.samefile(a, b):
            return True
    except OSError:
        pass
    return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))


def _fsync_dir(directory):
    """Best-effort fsync of a directory so a rename survives a crash (POSIX)."""
    if os.name == "nt":
        return
    try:
        fd = os.open(str(directory), os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _cleanup_stale_temps(directory):
    """Remove orphaned atomic-write temp files left by a crash."""
    try:
        for entry in directory.glob("tmp*"):
            try:
                if entry.is_file():
                    entry.unlink(missing_ok=True)
            except OSError:
                pass
    except OSError:
        pass


def load_expenses(path=DATA_FILE):
    """Load and strictly validate an expense file. Raises ValueError/OSError."""
    if not path.is_file():
        if path.exists():
            raise ValueError(f"{path} is not a file.")
        return []
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError(f"The expense file is not valid UTF-8: {error}") from None
    try:
        records = json.loads(text)
    except RecursionError:
        raise ValueError("The expense file is too deeply nested.") from None
    if not isinstance(records, list):
        raise ValueError("The expense file must contain a list.")
    ids = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Invalid expense record.")
        if (not isinstance(record.get("id"), str) or not record["id"].strip()
                or record["id"] in ids
                or not isinstance(record.get("name"), str) or not record["name"].strip()
                or "\n" in record["name"] or "\r" in record["name"]
                or type(record.get("centavos")) is not int or record["centavos"] <= 0
                or record["centavos"] > MAX_CENTAVOS
                or record.get("category") not in CATEGORIES
                or not isinstance(record.get("date"), str)):
            raise ValueError("Invalid expense record.")
        try:
            datetime.strptime(record["date"], "%Y-%m-%d %H:%M")
        except ValueError:
            raise ValueError("Invalid expense record.") from None
        ids.add(record["id"])
    return records


@contextmanager
def atomic_write(path):
    # Replace only after a complete write, keeping the previous file intact on failure.
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            yield handle
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def save_expenses(records, path=DATA_FILE):
    with atomic_write(path) as handle:
        json.dump(records, handle, ensure_ascii=False, indent=2)


def initialize_storage():
    """Load primary data, migrating the legacy beside-app file on first run."""
    if DATA_FILE.is_file():
        return load_expenses()
    if DATA_FILE.exists():
        raise ValueError(f"{DATA_FILE} is not a file.")
    if BACKUP_FILE.is_file():
        raise ValueError("The expense file is missing. Use Restore backup to recover it.")
    if BACKUP_FILE.exists():
        raise ValueError(f"{BACKUP_FILE} is not a file.")
    if LEGACY_FILE.is_file():
        records = load_expenses(LEGACY_FILE)
        save_expenses(records, DATA_FILE)
        return records
    if LEGACY_FILE.exists():
        raise ValueError(f"{LEGACY_FILE} is not a file.")
    return []


def lock_instance(handle):
    """Take a non-blocking exclusive lock on the open lock file."""
    if os.name == "nt":
        import msvcrt
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)


def parse_amount(value):
    """Parse a peso amount string into integer centavos."""
    value = value.strip()
    if value.startswith("₱"):
        value = value[1:].strip()
    if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]{1,2})?|\.[0-9]{1,2}", value):
        raise ValueError("Use a peso amount such as 125.50 or ₱1,250.00, with up to two decimal places.")
    try:
        amount = Decimal(value.replace(",", ""))
        if not amount.is_finite() or amount <= 0 or amount > MAX_AMOUNT:
            raise ValueError("Enter an amount from ₱0.01 to ₱999,999,999.99.")
        return int(amount * 100)
    except InvalidOperation:
        raise ValueError("Enter a valid peso amount.") from None


def parse_date(value):
    """Parse a YYYY-MM-DD string, returning the ISO date or raising ValueError."""
    value = value.strip()
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
        except ValueError:
            pass
    raise ValueError("Enter a valid date in YYYY-MM-DD format.")


def money(centavos):
    """Format integer centavos as ₱1,250.00."""
    return f"₱{centavos // 100:,}.{centavos % 100:02d}"


def _csv_safe_name(name):
    """Prefix spreadsheet-formula names so Excel doesn't execute them."""
    if name.lstrip(" \t\r\n").startswith(("=", "+", "-", "@", "|", "%")) or name.startswith(("\t", "\r", "\n")):
        return "'" + name
    return name


class ExpenseTracker(tk.Tk if tk else object):  # type: ignore[misc]
    def __init__(self):
        if not TK_AVAILABLE:
            raise RuntimeError("Tkinter is not available. Install Python with Tkinter support.")
        super().__init__()
        self.title("Personal Expense Tracker")
        self.geometry("980x680")
        self.minsize(850, 560)
        self.configure(bg=BG)
        self.expenses = []
        self.storage_ready = True
        self.editing_id = None
        self.filters = ("", "", "All categories", "")
        self.visible_expenses = []
        self.sort_column = None
        self.sort_reverse = False
        self._data_signature = None
        self.configure_styles()
        self.build_ui()
        try:
            self.expenses = initialize_storage()
            self._data_signature = _file_signature(DATA_FILE)
        except (OSError, ValueError) as error:
            logger.exception("Could not load expenses")
            self.storage_ready = False
            self.after(100, lambda detail=str(error): messagebox.showerror(
                "Could not load expenses",
                f"Your existing file has been left untouched.\n\n{detail}\n\n"
                f"Use Restore backup if available, or repair the file and reopen the app.\n{DATA_FILE}",
                parent=self))
        self.update_storage_controls()
        self.refresh()

    def configure_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Title.TLabel", font=("Segoe UI", 23, "bold"))
        style.configure("Total.TLabel", foreground=ACCENT, font=("Segoe UI", 22, "bold"))
        style.configure("TEntry", fieldbackground=PANEL, foreground=TEXT, insertcolor=TEXT, padding=8)
        style.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=TEXT, padding=8)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", TEXT)])
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        style.configure("TButton", background="#334155", foreground=TEXT, padding=(14, 9), font=("Segoe UI", 10))
        style.map("TButton", background=[("active", "#475569"), ("disabled", PANEL)])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                        rowheight=34, borderwidth=0, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#334155", foreground=TEXT,
                        font=("Segoe UI", 10, "bold"), padding=8)
        style.map("Treeview", background=[("selected", "#1d4ed8")], foreground=[("selected", "white")])

    def build_ui(self):
        main = ttk.Frame(self, padding=24)
        main.pack(fill="both", expand=True)
        ttk.Label(main, text="Personal Expense Tracker", style="Title.TLabel").pack(anchor="w")
        ttk.Label(main, text="Every peso, in one place. Saved automatically on this computer.",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 20))
        form = ttk.Frame(main)
        form.pack(fill="x")
        form.columnconfigure(0, weight=3)
        form.columnconfigure(1, weight=2)
        form.columnconfigure(2, weight=2)
        form.columnconfigure(3, weight=2)
        self.name = tk.StringVar()
        self.amount = tk.StringVar()
        self.category = tk.StringVar(value=CATEGORIES[0])
        self.purchase_date = tk.StringVar()
        for col, label in enumerate(("Expense name", "Amount (₱)", "Category", "Purchase date (YYYY-MM-DD)")):
            ttk.Label(form, text=label).grid(row=0, column=col, sticky="w", pady=(0, 6))
        self.name_entry = ttk.Entry(form, textvariable=self.name)
        self.name_entry.grid(row=1, column=0, sticky="ew", padx=(0, 12))
        ttk.Entry(form, textvariable=self.amount, width=14).grid(row=1, column=1, sticky="ew", padx=(0, 12))
        ttk.Combobox(form, textvariable=self.category, values=CATEGORIES, state="readonly", width=14).grid(
            row=1, column=2, sticky="ew", padx=(0, 12))
        ttk.Entry(form, textvariable=self.purchase_date, width=12).grid(row=1, column=3, sticky="ew")
        actions = ttk.Frame(main)
        actions.pack(fill="x", pady=(10, 14))
        self.add_button = ttk.Button(actions, text="+ Add expense", command=self.add_expense)
        self.add_button.pack(side="left")
        self.cancel_button = ttk.Button(actions, text="Cancel edit", command=self.reset_form)
        ttk.Label(actions, text="Leave the purchase date blank for today.", style="Muted.TLabel").pack(
            side="right")

        filters = ttk.Frame(main)
        filters.pack(fill="x", pady=(0, 12))
        self.from_date = tk.StringVar()
        self.to_date = tk.StringVar()
        self.filter_category = tk.StringVar(value="All categories")
        self.search_text = tk.StringVar()
        for label, variable in (("From (YYYY-MM-DD)", self.from_date), ("To (YYYY-MM-DD)", self.to_date)):
            ttk.Label(filters, text=label).pack(side="left", padx=(0, 5))
            ttk.Entry(filters, textvariable=variable, width=11).pack(side="left", padx=(0, 10))
        ttk.Combobox(filters, textvariable=self.filter_category, values=("All categories", *CATEGORIES),
                     state="readonly", width=14).pack(side="left", padx=(0, 8))
        ttk.Label(filters, text="Search").pack(side="left", padx=(0, 5))
        ttk.Entry(filters, textvariable=self.search_text, width=14).pack(side="left", padx=(0, 8))
        ttk.Button(filters, text="Apply", command=self.apply_filters).pack(side="left", padx=(0, 4))
        ttk.Button(filters, text="Clear", command=self.clear_filters).pack(side="left")
        table = ttk.Frame(main)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=("date", "name", "category", "amount"),
                                 show="headings", selectmode="browse", height=1)
        for column, label, width in (("date", "Date", 135), ("name", "Expense", 260),
                                     ("category", "Category", 120), ("amount", "Amount (₱)", 140)):
            self.tree.heading(column, text=label, command=lambda c=column: self.sort_by(c))
            self.tree.column(column, width=width, minwidth=85, anchor="e" if column == "amount" else "w")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        summary = ttk.Frame(main)
        summary.pack(fill="x", pady=(12, 0))
        self.total_label = ttk.Label(summary, style="Total.TLabel")
        self.total_label.pack(side="left")
        self.count_label = ttk.Label(summary, style="Muted.TLabel")
        self.count_label.pack(side="right", anchor="s")
        table_actions = ttk.Frame(main)
        table_actions.pack(fill="x", pady=(14, 6))
        self.edit_button = ttk.Button(table_actions, text="Edit selected expense", command=self.edit_expense)
        self.edit_button.pack(side="left", padx=(0, 6))
        self.delete_button = ttk.Button(table_actions, text="Delete selected expense", command=self.delete_expense)
        self.delete_button.pack(side="left")
        self.restore_button = ttk.Button(table_actions, text="Restore backup", command=self.restore_backup)
        self.restore_button.pack(side="right")
        self.export_button = ttk.Button(table_actions, text="Export CSV", command=self.export_csv)
        self.export_button.pack(side="right", padx=(0, 6))
        self.import_button = ttk.Button(table_actions, text="Import CSV", command=self.import_csv)
        self.import_button.pack(side="right", padx=(0, 6))
        self.status = ttk.Label(main, style="Muted.TLabel")
        self.status.pack(anchor="w")
        for widget in form.winfo_children():
            if isinstance(widget, ttk.Entry):
                widget.bind("<Return>", lambda event: self.add_expense())
        # Enter in filter fields applies filters; Escape cancels an edit.
        for widget in filters.winfo_children():
            if isinstance(widget, ttk.Entry):
                widget.bind("<Return>", lambda event: self.apply_filters())
        self.bind("<Escape>", lambda event: self.reset_form() if self.editing_id else None)
        self.bind("<Delete>", lambda event: self.delete_expense() if event.widget is self.tree else None)
        self.tree.bind("<Double-1>", lambda event: self.edit_expense())
        self.name_entry.focus_set()

    def sort_by(self, column):
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False
        labels = {"date": "Date", "name": "Expense", "category": "Category", "amount": "Amount (₱)"}
        for col, label in labels.items():
            arrow = ""
            if col == self.sort_column:
                arrow = " ▼" if self.sort_reverse else " ▲"
            self.tree.heading(col, text=label + arrow)
        self.refresh()

    def _check_external_change(self):
        """Return True if the on-disk file changed since we last loaded/saved."""
        current = _file_signature(DATA_FILE)
        if current == self._data_signature:
            return False
        # Fresh start with no file yet: only a change if a file appeared.
        if self._data_signature is None and current is None:
            return False
        return True

    def commit(self, updated):
        if self._check_external_change():
            logger.warning("Expense file changed on disk; asking user before overwriting")
            if messagebox.askyesno(
                    "File changed on disk",
                    "The expense file was changed outside the app.\n\n"
                    "Yes: Reload from disk (your pending change is discarded).\n"
                    "No: Overwrite the file with your change.",
                    parent=self):
                try:
                    self.expenses = load_expenses()
                    self._data_signature = _file_signature(DATA_FILE)
                    self.storage_ready = True
                    self.update_storage_controls()
                    self.refresh()
                except (OSError, ValueError) as error:
                    messagebox.showerror("Could not reload", str(error), parent=self)
                return False
        try:
            save_expenses(self.expenses, BACKUP_FILE)
            save_expenses(updated)
        except OSError as error:
            logger.exception("Could not save expenses")
            self.update_storage_controls()
            messagebox.showerror("Could not save", f"The change was not saved.\n\n{error}", parent=self)
            return False
        self.expenses = updated
        self._data_signature = _file_signature(DATA_FILE)
        self.update_storage_controls()
        self.refresh()
        return True

    def add_expense(self):
        if not self.storage_ready:
            return
        name = self.name.get().strip()
        if not name:
            messagebox.showwarning("Expense name needed", "Enter a name for this expense.", parent=self)
            self.name_entry.focus_set()
            return
        try:
            centavos = parse_amount(self.amount.get())
        except ValueError as error:
            messagebox.showwarning("Check the amount", str(error), parent=self)
            return
        now = datetime.now()
        try:
            day = parse_date(self.purchase_date.get()) if self.purchase_date.get().strip() else now.date().isoformat()
        except ValueError as error:
            messagebox.showwarning("Check the purchase date", str(error), parent=self)
            return
        previous = next((item for item in self.expenses if item["id"] == self.editing_id), None)
        time = previous["date"][11:] if previous else now.strftime("%H:%M")
        record = dict(id=self.editing_id or uuid.uuid4().hex, name=name, centavos=centavos,
                      category=self.category.get(), date=f"{day} {time}")
        updated = ([record if item["id"] == self.editing_id else item for item in self.expenses]
                   if previous else self.expenses + [record])
        if self.commit(updated):
            self.reset_form()
            if self.filters != ("", "", "All categories", ""):
                self.clear_filters()

    def reset_form(self):
        self.editing_id = None
        self.name.set("")
        self.amount.set("")
        self.purchase_date.set("")
        self.add_button.configure(text="+ Add expense")
        self.cancel_button.pack_forget()
        self.name_entry.focus_set()

    def edit_expense(self):
        record = self.selected_expense("edit")
        if record is None:
            return
        self.editing_id = record["id"]
        self.name.set(record["name"])
        self.amount.set(money(record["centavos"]))
        self.category.set(record["category"])
        self.purchase_date.set(record["date"][:10])
        self.add_button.configure(text="Save changes")
        self.cancel_button.pack(side="left", padx=(6, 0))
        self.name_entry.focus_set()

    def selected_expense(self, action="delete"):
        if not self.storage_ready:
            return
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Select an expense", f"Select an entry in the list to {action} it.", parent=self)
            return
        return next((item for item in self.expenses if item["id"] == selected[0]), None)

    def delete_expense(self):
        record = self.selected_expense("delete")
        if record is None:
            return
        if messagebox.askyesno("Delete expense", f'Delete "{record["name"]}" ({money(record["centavos"])})?', parent=self):
            if self.commit([item for item in self.expenses if item["id"] != record["id"]]):
                if self.editing_id == record["id"]:
                    self.reset_form()

    def update_storage_controls(self):
        for button in (self.add_button, self.edit_button, self.delete_button, self.export_button, self.import_button):
            button.state(["!disabled"] if self.storage_ready else ["disabled"])
        self.restore_button.state(["!disabled"] if BACKUP_FILE.is_file() else ["disabled"])

    def restore_backup(self):
        if not messagebox.askyesno(
                "Restore backup", "Replace the current expenses with the last backup? "
                "Your current list will be saved as the new backup, so you can restore again to undo.",
                parent=self):
            return
        try:
            if not BACKUP_FILE.is_file():
                raise ValueError("The backup file is missing.")
            records = load_expenses(BACKUP_FILE)
            if self.storage_ready:
                # Preserve the pre-restore list so a second restore undoes this one.
                save_expenses(self.expenses, BACKUP_FILE)
            save_expenses(records)
        except (OSError, ValueError) as error:
            logger.exception("Could not restore backup")
            messagebox.showerror("Could not restore backup", str(error), parent=self)
            return
        self.expenses = records
        self._data_signature = _file_signature(DATA_FILE)
        self.storage_ready = True
        self.reset_form()
        self.update_storage_controls()
        self.refresh()
        messagebox.showinfo("Backup restored", f"Restored {len(records)} expenses.", parent=self)

    def apply_filters(self):
        try:
            start = parse_date(self.from_date.get()) if self.from_date.get().strip() else ""
            end = parse_date(self.to_date.get()) if self.to_date.get().strip() else ""
            if start and end and start > end:
                raise ValueError("The From date must be on or before the To date.")
        except ValueError as error:
            messagebox.showwarning("Check the filter dates", str(error), parent=self)
            return
        self.filters = (start, end, self.filter_category.get(), self.search_text.get().strip().lower())
        self.refresh()

    def clear_filters(self):
        self.from_date.set("")
        self.to_date.set("")
        self.filter_category.set("All categories")
        self.search_text.set("")
        self.apply_filters()

    def export_csv(self):
        filename = filedialog.asksaveasfilename(
            parent=self, title="Export displayed expenses", defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")], initialfile="expenses.csv")
        if not filename:
            return
        path = Path(filename)
        try:
            if path.suffix.lower() != ".csv":
                raise ValueError("Use a .csv filename for the export.")
            for protected in (DATA_FILE, BACKUP_FILE, LEGACY_FILE, LOCK_FILE):
                if _is_same_path(path, protected):
                    raise ValueError("Choose a separate file for the CSV export.")
            with atomic_write(path) as handle:
                handle.write("\ufeff")
                writer = csv.writer(handle)
                writer.writerow(("Date", "Expense", "Category", "Amount (PHP)"))
                for record in self.visible_expenses:
                    writer.writerow((record["date"], _csv_safe_name(record["name"]), record["category"],
                                     money(record["centavos"])[1:].replace(",", "")))
        except (OSError, ValueError) as error:
            logger.exception("Could not export CSV")
            messagebox.showerror("Could not export CSV", str(error), parent=self)
            return
        messagebox.showinfo("CSV exported", f"Exported {len(self.visible_expenses)} expenses.", parent=self)

    def import_csv(self):
        filename = filedialog.askopenfilename(
            parent=self, title="Import expenses from CSV", filetypes=[("CSV files", "*.csv")])
        if not filename:
            return
        path = Path(filename)
        try:
            if path.suffix.lower() != ".csv":
                raise ValueError("Choose a .csv file to import.")
            for protected in (DATA_FILE, BACKUP_FILE, LEGACY_FILE, LOCK_FILE):
                if _is_same_path(path, protected):
                    raise ValueError("Choose a separate CSV file to import.")
            records = []
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames is None:
                    raise ValueError("The CSV file is empty.")
                headers = {h.strip().lower(): h for h in reader.fieldnames}
                if not {"date", "expense", "category", "amount (php)"}.issubset(headers):
                    raise ValueError("The CSV must have Date, Expense, Category, Amount (PHP) columns.")
                for row in reader:
                    name = (row.get(headers["expense"]) or "").strip()
                    if name.startswith("'") and len(name) > 1 and name[1] in "=+-@|%":
                        name = name[1:]
                    if not name:
                        continue
                    category = (row.get(headers["category"]) or "").strip()
                    if category not in CATEGORIES:
                        raise ValueError(f"Unknown category: {category!r}.")
                    raw_date = (row.get(headers["date"]) or "").strip()
                    if len(raw_date) == 10:
                        day = parse_date(raw_date)
                        stamp = f"{day} 00:00"
                    else:
                        datetime.strptime(raw_date, "%Y-%m-%d %H:%M")
                        stamp = raw_date
                    centavos = parse_amount((row.get(headers["amount (php)"]) or "").strip())
                    records.append(dict(id=uuid.uuid4().hex, name=name, centavos=centavos,
                                        category=category, date=stamp))
        except (OSError, ValueError) as error:
            logger.exception("Could not import CSV")
            messagebox.showerror("Could not import CSV", str(error), parent=self)
            return
        if not records:
            messagebox.showinfo("Nothing to import", "No expense rows were found in that file.", parent=self)
            return
        if not messagebox.askyesno("Import expenses",
                                   f"Import {len(records)} expenses? They will be added to your list.",
                                   parent=self):
            return
        if self.commit(self.expenses + records):
            self.clear_filters()

    def refresh(self):
        selected = self.tree.selection()
        selected_id = selected[0] if selected else None
        try:
            scroll_first = self.tree.yview()[0]
        except Exception:
            scroll_first = 0.0
        for item in self.tree.get_children():
            self.tree.delete(item)
        start, end, category, search = self.filters
        filtered = bool(start or end or category != "All categories" or search)
        base = [
            item for item in reversed(self.expenses)
            if (not start or item["date"][:10] >= start)
            and (not end or item["date"][:10] <= end)
            and (category == "All categories" or item["category"] == category)
            and (not search or search in item["name"].lower())
        ]
        if self.sort_column is not None:
            key_map = {
                "date": lambda item: item["date"],
                "name": lambda item: item["name"].lower(),
                "category": lambda item: item["category"],
                "amount": lambda item: item["centavos"],
            }
            self.visible_expenses = sorted(base, key=key_map[self.sort_column], reverse=self.sort_reverse)
        else:
            self.visible_expenses = base
        for item in self.visible_expenses:
            self.tree.insert("", "end", iid=item["id"], values=(
                item["date"], item["name"], item["category"], money(item["centavos"])))
        if selected_id and self.tree.exists(selected_id):
            self.tree.selection_set(selected_id)
            self.tree.focus(selected_id)
        try:
            self.tree.yview_moveto(scroll_first)
        except Exception:
            pass
        total = money(sum(item["centavos"] for item in self.visible_expenses))
        label = "Filtered total" if filtered else "Total spent"
        self.total_label.configure(text=f"{label}: {total}")
        count = len(self.visible_expenses)
        count_text = f"{count} of {len(self.expenses)} expenses" if filtered else (
            f'{count} expense{"s" if count != 1 else ""}')
        self.count_label.configure(text=count_text)
        if not self.storage_ready:
            status = "Storage unavailable — existing file preserved."
        elif filtered and not count:
            status = "No expenses match the filters."
        elif not count:
            status = "No expenses yet. Add your first expense above."
        elif self.sort_column is not None:
            status = "All changes saved • Sorted"
        else:
            status = "All changes saved • Latest additions first"
        self.status.configure(text=status)


def show_startup_error(title, detail):
    if not TK_AVAILABLE:
        print(f"{title}\n\n{detail}", file=sys.stderr)
        return
    try:
        root = tk.Tk()
    except tk.TclError:
        print(f"{title}\n\n{detail}", file=sys.stderr)
        return
    root.withdraw()
    try:
        messagebox.showerror(title, detail, parent=root)
    finally:
        root.destroy()


def setup_logging():
    """Log to DATA_DIR/tracker.log (best-effort) plus stderr."""
    handlers = [logging.StreamHandler()]
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(DATA_DIR / "tracker.log", encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers)


def main():
    if not TK_AVAILABLE:
        print("Tkinter is not available. Install Python with Tkinter support "
              "(e.g. `apt install python3-tk` on Debian/Ubuntu, or reinstall "
              "Python from python.org with Tcl/Tk enabled).", file=sys.stderr)
        return
    setup_logging()
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _cleanup_stale_temps(DATA_DIR)
        lock = LOCK_FILE.open("a+b")
    except OSError as error:
        show_startup_error("Could not open expense storage", f"{DATA_DIR}\n\n{error}")
        return
    with lock:
        try:
            lock_instance(lock)
        except OSError as error:
            show_startup_error("Could not open Tracker", f"Close any other Tracker window and try again.\n\n{error}")
            return
        try:
            ExpenseTracker().mainloop()
        except tk.TclError as error:
            logger.exception("Tracker window failed to start")
            show_startup_error("Could not start Tracker", str(error))


if __name__ == "__main__":
    main()
