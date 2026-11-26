"""Unit tests for the pure logic in tracker.py (no display required)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tracker


class ParseAmountTests(unittest.TestCase):
    def test_valid_amounts(self):
        cases = {
            "125.50": 12550,
            "₱1,250.00": 125000,
            "₱ 125": 12500,
            ".50": 50,
            "0.01": 1,
            "1,000,000.00": 100000000,
            "999,999,999.99": 99999999999,
            "  42  ": 4200,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(tracker.parse_amount(raw), expected)

    def test_invalid_amounts(self):
        for raw in ["", "₱", "0", "0.00", "-5", "abc", "1,25", "12,34", "125.",
                    "1.234", "1,000,000,000.00", "1000000000", "₱₱10", "1 250"]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    tracker.parse_amount(raw)


class ParseDateTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(tracker.parse_date("2026-11-20"), "2026-11-20")
        self.assertEqual(tracker.parse_date(" 2024-02-29 "), "2024-02-29")

    def test_invalid(self):
        for raw in ["", "2026-02-30", "2026-13-01", "20/11/2026", "2026-11-20 17:55",
                    "2026-1-20", "abcd-ef-gh"]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    tracker.parse_date(raw)


class MoneyTests(unittest.TestCase):
    def test_formatting(self):
        self.assertEqual(tracker.money(0), "₱0.00")
        self.assertEqual(tracker.money(5), "₱0.05")
        self.assertEqual(tracker.money(100), "₱1.00")
        self.assertEqual(tracker.money(125000), "₱1,250.00")
        self.assertEqual(tracker.money(99999999999), "₱999,999,999.99")


class LoadSaveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def _record(self, **overrides):
        record = {"id": "a" * 32, "name": "Jan", "centavos": 50000,
                  "category": "Food", "date": "2026-11-20 17:55"}
        record.update(overrides)
        return record

    def test_roundtrip(self):
        path = self.dir / "expenses.json"
        records = [self._record(), self._record(id="b" * 32, name="Pat")]
        tracker.save_expenses(records, path)
        self.assertEqual(tracker.load_expenses(path), records)

    def test_missing_file_returns_empty(self):
        self.assertEqual(tracker.load_expenses(self.dir / "nope.json"), [])

    def test_rejects_non_list(self):
        path = self.dir / "x.json"
        path.write_text('{"a": 1}', encoding="utf-8")
        with self.assertRaises(ValueError):
            tracker.load_expenses(path)

    def test_rejects_duplicate_ids(self):
        path = self.dir / "x.json"
        path.write_text(json.dumps([self._record(), self._record()]), encoding="utf-8")
        with self.assertRaises(ValueError):
            tracker.load_expenses(path)

    def test_rejects_bad_category_and_date(self):
        for bad in [self._record(category="Nope"), self._record(date="2026-11-20"),
                    self._record(centavos=0), self._record(centavos=-1),
                    self._record(centavos=tracker.MAX_CENTAVOS + 1),
                    self._record(name="  "), self._record(name="a\nb"),
                    self._record(centavos=True)]:
            path = self.dir / "x.json"
            path.write_text(json.dumps([bad]), encoding="utf-8")
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    tracker.load_expenses(path)

    def test_rejects_bool_centavos(self):
        path = self.dir / "x.json"
        path.write_text(json.dumps([self._record(centavos=True)]), encoding="utf-8")
        with self.assertRaises(ValueError):
            tracker.load_expenses(path)

    def test_bom_file_loads(self):
        path = self.dir / "x.json"
        path.write_bytes(b"\xef\xbb\xbf" + json.dumps([self._record()]).encode("utf-8"))
        self.assertEqual(len(tracker.load_expenses(path)), 1)

    def test_directory_raises(self):
        with self.assertRaises(ValueError):
            tracker.load_expenses(self.dir)


class AtomicWriteTests(unittest.TestCase):
    def test_failed_write_preserves_old_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.json"
            path.write_text("old", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                with tracker.atomic_write(path):
                    raise RuntimeError("boom")
            self.assertEqual(path.read_text(encoding="utf-8"), "old")
            # No orphan temp files left behind.
            self.assertEqual([p.name for p in Path(tmp).glob("tmp*")], [])

    def test_successful_write_replaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.json"
            path.write_text("old", encoding="utf-8")
            with tracker.atomic_write(path) as handle:
                handle.write("new")
            self.assertEqual(path.read_text(encoding="utf-8"), "new")


class InitializeStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self._saved = (tracker.DATA_FILE, tracker.BACKUP_FILE, tracker.LEGACY_FILE)
        tracker.DATA_FILE = self.dir / "expenses.json"
        tracker.BACKUP_FILE = self.dir / "expenses.backup.json"
        tracker.LEGACY_FILE = self.dir / "legacy.json"
        self.addCleanup(self._restore)

    def _restore(self):
        tracker.DATA_FILE, tracker.BACKUP_FILE, tracker.LEGACY_FILE = self._saved

    def test_empty_start(self):
        self.assertEqual(tracker.initialize_storage(), [])

    def test_migrates_legacy(self):
        record = {"id": "a" * 32, "name": "Jan", "centavos": 100,
                  "category": "Food", "date": "2026-11-20 17:55"}
        tracker.LEGACY_FILE.write_text(json.dumps([record]), encoding="utf-8")
        self.assertEqual(tracker.initialize_storage(), [record])
        self.assertTrue(tracker.DATA_FILE.is_file())

    def test_missing_primary_with_backup_raises(self):
        tracker.BACKUP_FILE.write_text("[]", encoding="utf-8")
        with self.assertRaises(ValueError):
            tracker.initialize_storage()


class HelperTests(unittest.TestCase):
    def test_csv_safe_name(self):
        self.assertEqual(tracker._csv_safe_name("=2+5"), "'=2+5")
        self.assertEqual(tracker._csv_safe_name(" =2+5"), "' =2+5")
        self.assertEqual(tracker._csv_safe_name("Jan"), "Jan")

    def test_is_same_path_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "Expenses.JSON"
            b = Path(tmp) / "expenses.json"
            a.write_text("x", encoding="utf-8")
            # On case-sensitive filesystems these are different files; the
            # normcase comparison is what matters on Windows.
            self.assertTrue(tracker._is_same_path(a, a))
            self.assertFalse(tracker._is_same_path(a, Path(tmp) / "other.json"))

    def test_file_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.json"
            self.assertIsNone(tracker._file_signature(path))
            path.write_text("hi", encoding="utf-8")
            self.assertIsNotNone(tracker._file_signature(path))


if __name__ == "__main__":
    unittest.main()
