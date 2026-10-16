import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sync_engine import HEADERS, plan_duplicate_cleanup, remove_duplicate_rows


def row(path, scanned, **cols):
    r = [""] * len(HEADERS)
    r[HEADERS.index("Full Path")] = path
    r[HEADERS.index("Last Scanned")] = scanned
    r[HEADERS.index("Photoshoot Name")] = path
    for name, value in cols.items():
        r[HEADERS.index(name.replace("_", " "))] = value
    return r


class FakeSpreadsheet:
    def __init__(self):
        self.requests = []

    def batch_update(self, body):
        self.requests.extend(body["requests"])


class FakeWorksheet:
    id = 7

    def __init__(self, values):
        self.values = values
        self.spreadsheet = FakeSpreadsheet()
        self.updates = []

    def get_all_values(self):
        return self.values

    def batch_update(self, data, value_input_option=None):
        self.updates.extend(data)


class PlanTest(unittest.TestCase):
    def test_no_dupes(self):
        vals = [HEADERS, row("a", "2026-01-01 10:00"), row("b", "2026-01-01 10:00")]
        self.assertEqual(plan_duplicate_cleanup(vals), [])

    def test_keeps_newest_scan(self):
        vals = [HEADERS, row("a", "2026-02-01 10:00"), row("b", "2026-01-01 10:00"),
                row("a", "2026-03-01 10:00"), row("a", "2026-01-15 10:00")]
        (plan,) = plan_duplicate_cleanup(vals)
        self.assertEqual((plan["keep"], plan["drop"]), (4, [2, 5]))

    def test_tie_keeps_lowest_row(self):
        vals = [HEADERS, row("a", "2026-01-01 10:00"), row("a", "2026-01-01 10:00")]
        (plan,) = plan_duplicate_cleanup(vals)
        self.assertEqual((plan["keep"], plan["drop"]), (2, [3]))

    def test_ignores_blank_paths_and_short_rows(self):
        vals = [HEADERS, [], [""], ["only name"]]
        self.assertEqual(plan_duplicate_cleanup(vals), [])

    def test_blank_on_kept_row_is_a_fill_not_a_conflict(self):
        vals = [HEADERS, row("a", "2026-01-01 10:00", Remarks="old note"), row("a", "2026-02-01 10:00")]
        (plan,) = plan_duplicate_cleanup(vals)
        self.assertEqual(plan["fills"], {"Remarks": "old note"})
        self.assertEqual(plan["conflicts"], {})

    def test_differing_values_are_a_conflict_newest_first(self):
        vals = [HEADERS, row("a", "2026-01-01 10:00", Client="Old Co"),
                row("a", "2026-02-01 10:00", Client="New Co")]
        (plan,) = plan_duplicate_cleanup(vals)
        self.assertEqual(plan["conflicts"], {"Client": ["New Co", "Old Co"]})

    def test_identical_values_are_not_a_conflict(self):
        vals = [HEADERS, row("a", "2026-01-01 10:00", Remarks="same"),
                row("a", "2026-02-01 10:00", Remarks="same")]
        (plan,) = plan_duplicate_cleanup(vals)
        self.assertEqual(plan["conflicts"], {})


class RemoveTest(unittest.TestCase):
    def conflict_sheet(self):
        return [HEADERS,
                row("a", "2026-01-01 10:00", Remarks="old", Client="Old Co", Client_Token="tok-old"),
                row("a", "2026-02-01 10:00", Remarks="new", Client="New Co", Client_Token="tok-new")]

    def test_conflict_without_permission_leaves_rows(self):
        ws = FakeWorksheet(self.conflict_sheet())
        remove_duplicate_rows(ws, ws.values, log=lambda m: None, confirm_merge=lambda plans: False)
        self.assertEqual(ws.spreadsheet.requests, [])
        self.assertEqual(ws.updates, [])

    def test_conflict_with_no_callback_leaves_rows(self):
        ws = FakeWorksheet(self.conflict_sheet())
        remove_duplicate_rows(ws, ws.values, log=lambda m: None)
        self.assertEqual(ws.spreadsheet.requests, [])

    def test_approved_merge_combines_text_keeps_newest_for_single_valued(self):
        ws = FakeWorksheet(self.conflict_sheet())
        asked = []
        remove_duplicate_rows(ws, ws.values, log=lambda m: None,
                              confirm_merge=lambda plans: asked.append(plans) or True)
        self.assertEqual(len(asked[0]), 1)
        written = {u["range"]: u["values"][0][0] for u in ws.updates}
        self.assertEqual(written[f"{chr(65 + HEADERS.index('Remarks'))}3"], "new | old")
        self.assertEqual(written[f"{chr(65 + HEADERS.index('Client'))}3"], "New Co")
        self.assertEqual(written[f"{chr(65 + HEADERS.index('Client Token'))}3"], "tok-new")
        (req,) = ws.spreadsheet.requests
        self.assertEqual(req["deleteDimension"]["range"]["startIndex"], 1)  # row 2

    def test_nonconflicting_dupes_removed_without_asking(self):
        ws = FakeWorksheet([HEADERS, row("a", "2026-01-01 10:00", Remarks="note"), row("a", "2026-02-01 10:00")])
        remove_duplicate_rows(ws, ws.values, log=lambda m: None,
                              confirm_merge=lambda plans: self.fail("should not ask"))
        self.assertEqual(len(ws.spreadsheet.requests), 1)
        self.assertEqual(ws.updates[0]["values"], [["note"]])


if __name__ == "__main__":
    unittest.main()
