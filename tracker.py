"""A small, local-only personal expense tracker. Run with Python 3."""

import json
import os
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk


DATA_FILE = Path(__file__).resolve().with_name("expenses.json")
CATEGORIES = ("Food", "Bills", "Transport", "Shopping", "Other")
BG, PANEL, TEXT, MUTED, ACCENT = "#111827", "#1f2937", "#f3f4f6", "#9ca3af", "#60a5fa"


def load_expenses(path=DATA_FILE):
    if not path.exists():
        return []
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("The expense file must contain a list.")
    ids = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Invalid expense record.")
        if (not isinstance(record.get("id"), str) or not record["id"]
                or record["id"] in ids
                or not isinstance(record.get("name"), str) or not record["name"].strip()
                or type(record.get("centavos")) is not int or record["centavos"] <= 0
                or record.get("category") not in CATEGORIES
                or not isinstance(record.get("date"), str)):
            raise ValueError("Invalid expense record.")
        ids.add(record["id"])
    return records


def save_expenses(records, path=DATA_FILE):
    # Replace only after a complete write, keeping the previous file intact on failure.
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(records, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def parse_amount(value):
    try:
        amount = Decimal(value.strip())
        if not amount.is_finite() or amount <= 0 or amount > Decimal("999999999.99"):
            raise ValueError
        cents = amount * 100
        if cents != cents.to_integral_value():
            raise ValueError
        return int(cents)
    except (InvalidOperation, ValueError):
        raise ValueError("Enter a positive amount with up to two decimal places (for example, 125.50).") from None


def money(centavos):
    return f"₱{centavos // 100:,}.{centavos % 100:02d}"


class ExpenseTracker(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Personal Expense Tracker")
        self.geometry("850x600")
        self.minsize(660, 460)
        self.configure(bg=BG)
        self.expenses = []
        self.storage_ready = True
        self.configure_styles()
        self.build_ui()
        try:
            self.expenses = load_expenses()
        except (OSError, ValueError) as error:
            self.storage_ready = False
            self.after(100, lambda detail=str(error): messagebox.showerror(
                "Could not load expenses",
                f"Your existing file has been left untouched.\n\n{detail}\n\n"
                f"Fix or rename this file, then reopen the app:\n{DATA_FILE}", parent=self))
            self.add_button.state(["disabled"])
            self.delete_button.state(["disabled"])
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
        self.name = tk.StringVar()
        self.amount = tk.StringVar()
        self.category = tk.StringVar(value=CATEGORIES[0])
        for col, label in enumerate(("Expense name", "Amount (₱)", "Category")):
            ttk.Label(form, text=label).grid(row=0, column=col, sticky="w", pady=(0, 6))
        self.name_entry = ttk.Entry(form, textvariable=self.name)
        self.name_entry.grid(row=1, column=0, sticky="ew", padx=(0, 12))
        ttk.Entry(form, textvariable=self.amount, width=14).grid(row=1, column=1, sticky="ew", padx=(0, 12))
        ttk.Combobox(form, textvariable=self.category, values=CATEGORIES, state="readonly", width=14).grid(
            row=1, column=2, sticky="ew")
        self.add_button = ttk.Button(main, text="+ Add expense", command=self.add_expense)
        self.add_button.pack(anchor="w", pady=(12, 20))
        summary = ttk.Frame(main)
        summary.pack(fill="x", pady=(0, 12))
        self.total_label = ttk.Label(summary, style="Total.TLabel")
        self.total_label.pack(side="left")
        self.count_label = ttk.Label(summary, style="Muted.TLabel")
        self.count_label.pack(side="right", anchor="s")
        table = ttk.Frame(main)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=("date", "name", "category", "amount"),
                                 show="headings", selectmode="browse")
        for column, label, width in (("date", "Date", 135), ("name", "Expense", 260),
                                     ("category", "Category", 120), ("amount", "Amount (₱)", 140)):
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width, minwidth=85, anchor="e" if column == "amount" else "w")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.delete_button = ttk.Button(main, text="Delete selected expense", command=self.delete_expense)
        self.delete_button.pack(anchor="w", pady=(14, 6))
        self.status = ttk.Label(main, style="Muted.TLabel")
        self.status.pack(anchor="w")
        self.bind("<Return>", lambda event: self.add_expense())
        self.name_entry.focus_set()

    def commit(self, updated):
        try:
            save_expenses(updated)
        except OSError as error:
            messagebox.showerror("Could not save", f"The change was not saved.\n\n{error}", parent=self)
            return False
        self.expenses = updated
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
        record = dict(id=uuid.uuid4().hex, name=name, centavos=centavos,
                      category=self.category.get(), date=datetime.now().strftime("%Y-%m-%d %H:%M"))
        if self.commit(self.expenses + [record]):
            self.name.set("")
            self.amount.set("")
            self.name_entry.focus_set()

    def delete_expense(self):
        if not self.storage_ready:
            return
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Select an expense", "Select an entry in the list to delete it.", parent=self)
            return
        record = next(item for item in self.expenses if item["id"] == selected[0])
        if messagebox.askyesno("Delete expense", f'Delete "{record["name"]}" ({money(record["centavos"])})?', parent=self):
            self.commit([item for item in self.expenses if item["id"] != selected[0]])

    def refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for item in reversed(self.expenses):
            self.tree.insert("", "end", iid=item["id"], values=(
                item["date"], item["name"], item["category"], money(item["centavos"])))
        self.total_label.configure(text=f'Total spent: {money(sum(item["centavos"] for item in self.expenses))}')
        count = len(self.expenses)
        self.count_label.configure(text=f'{count} expense{"s" if count != 1 else ""}')
        self.status.configure(text=("All changes saved • Newest entries first" if count else "No expenses yet. Add your first expense above.")
                              if self.storage_ready else "Storage unavailable — existing file preserved.")


if __name__ == "__main__":
    ExpenseTracker().mainloop()
