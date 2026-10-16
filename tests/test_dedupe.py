import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sync_engine import HEADERS, find_duplicate_rows


def row(path, scanned):
    r = [""] * len(HEADERS)
    r[HEADERS.index("Full Path")] = path
    r[HEADERS.index("Last Scanned")] = scanned
    return r


class FindDuplicateRowsTest(unittest.TestCase):
    def test_no_dupes(self):
        vals = [HEADERS, row("a", "2026-01-01 10:00"), row("b", "2026-01-01 10:00")]
        self.assertEqual(find_duplicate_rows(vals), [])

    def test_removes_oldest_scanned(self):
        vals = [HEADERS, row("a", "2026-02-01 10:00"), row("b", "2026-01-01 10:00"),
                row("a", "2026-03-01 10:00"), row("a", "2026-01-15 10:00")]
        self.assertEqual(find_duplicate_rows(vals), [2, 5])

    def test_tie_keeps_lowest_row(self):
        vals = [HEADERS, row("a", "2026-01-01 10:00"), row("a", "2026-01-01 10:00")]
        self.assertEqual(find_duplicate_rows(vals), [3])

    def test_ignores_blank_paths_and_short_rows(self):
        vals = [HEADERS, [], [""], ["only name"]]
        self.assertEqual(find_duplicate_rows(vals), [])


if __name__ == "__main__":
    unittest.main()
