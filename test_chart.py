"""Chart hit tests must resolve real evidence, including compressed peaks."""

import copy
from types import SimpleNamespace
import unittest

import chart
from test_presentation import case
from test_workbench import config, dataset


def record(row, score):
    return {"row": row, "scores": {} if score is None else {"value": score}}


class GeometryTests(unittest.TestCase):
    def test_first_last_single_and_resized_points_are_selectable(self):
        for width in (180, 450, 900):
            with self.subTest(width=width):
                points = chart.points([record(1, 0), record(2, 6)], width, 6)
                self.assertEqual(points[0].x, 58)
                self.assertEqual(points[-1].x, width - 22)
                for point in points:
                    self.assertEqual(chart.hit(points, point.x, point.y), point)
        single = chart.points([record(1, 3)], 450, 6)[0]
        self.assertEqual(chart.hit([single], single.x, single.y).row, 1)

    def test_collapsed_column_preserves_uncapped_peak_and_source_row(self):
        records = [record(i, 0) for i in range(1, 10001)]
        records[4] = record(5, 30)
        records[5] = record(6, 90)
        records[6] = record(7, 90)
        points = chart.points(records, 180, 6)
        peak = next(p for p in points if p.x == 58)
        self.assertEqual(peak.row, 6)  # Earliest real maximum, not earliest capped value.
        self.assertEqual(peak.score, 90)
        self.assertEqual(peak.y, 26)
        self.assertGreater(peak.count, 1)
        self.assertEqual(chart.hit(points, peak.x, peak.y).row, 6)
        self.assertLessEqual(len(points), 101)

    def test_missing_values_are_not_zero_and_labels_are_not_click_targets(self):
        points = chart.points([record(1, None), record(2, 0), record(3, None)], 450, 6)
        self.assertEqual([p.row for p in points], [2])
        self.assertIsNone(chart.hit(points, 58, 82))
        self.assertIsNone(chart.hit(points, points[0].x, 12))
        self.assertIsNone(chart.hit(points, points[0].x, 101))
        self.assertEqual(chart.points([record(1, None)], 450, 6), [])

    def test_signal_is_the_field_with_highest_deviation(self):
        point = chart.points([{"row": 1, "scores": {"first": 2, "second": 15}}], 450, 6)[0]
        self.assertEqual((point.field, point.score), ("second", 15))


class ChartUITests(unittest.TestCase):
    def setUp(self):
        from app import Workbench

        self.win = Workbench(start_hidden=True)
        self.win.withdraw()
        source = dataset(
            [
                {"reading": "10.123456789012345"},
                {"reading": 100},
                {"reading": None},
                {"reading": 11},
            ]
        )
        self.win.current, self.win.reference, self.win.run_config, self.win.result = case(
            source, config()
        )
        self.win._render_findings()

    def tearDown(self):
        self.win.destroy()

    def click(self, row):
        point = next(p for p in self.win._chart_points if p.row == row)
        self.win._chart_click(SimpleNamespace(x=point.x, y=point.y))

    def test_click_selects_actual_record_and_preserves_exact_original_value(self):
        self.click(1)
        win = self.win
        self.assertEqual(win.findings.selection(), ("1",))
        self.assertIn("10.123456789012345", win.chart_readout.cget("text"))
        self.assertIn('reading: "10.123456789012345"', win.detail.get("1.0", "end"))
        self.assertIn("Below review at: 6", win.detail.get("1.0", "end"))
        self.assertIn("No configured condition matched.", win.detail.get("1.0", "end"))
        self.assertTrue(win.only_leads.get())  # Temporary reveal is not a filter change.
        self.assertEqual(win._chart_reveal, 1)
        win.chart_return.invoke()
        self.assertEqual(win.findings.get_children(), ("2", "3"))
        self.assertIsNone(win._chart_reveal)

    def test_click_reveals_record_outside_search_and_priority_without_changing_evidence(self):
        win = self.win
        original = copy.deepcopy(win.result)
        win.search.set("no-match")
        win.minimum_priority.set("Critical")
        win._render_findings()
        self.click(2)
        self.assertEqual(win.findings.get_children(), ("2",))
        self.assertEqual(win.findings.selection(), ("2",))
        self.assertEqual(win.search.get(), "no-match")
        self.assertEqual(win.minimum_priority.get(), "Critical")
        self.assertEqual(win.result, original)
        self.assertIn("outside filters", win.chart_readout.cget("text"))
        self.assertIn("1 record with gaps hidden", win.filter_note.cget("text"))
        win.chart_return.invoke()
        self.assertEqual(win.findings.get_children(), ())
        self.assertEqual(win.result, original)

    def test_arrows_reach_uncompressed_records_and_skip_missing_measurements(self):
        self.click(1)
        win = self.win
        win._chart_step(1)
        self.assertEqual(win.findings.selection(), ("2",))
        win._chart_step(1)
        self.assertEqual(win.findings.selection(), ("4",))
        win._chart_step(1)
        self.assertEqual(win.findings.selection(), ("4",))
        win._chart_step(-1)
        self.assertEqual(win.findings.selection(), ("2",))

    def test_real_canvas_click_binding_selects_point(self):
        win = self.win
        win.deiconify()
        win.show_page("Findings")
        win.update()
        point = next(p for p in win._chart_points if p.row == 2)
        win.timeline.event_generate("<Button-1>", x=point.x, y=round(point.y))
        win.update()
        self.assertEqual(win.findings.selection(), ("2",))
        self.assertIn("reading: 100", win.chart_readout.cget("text"))

    def test_empty_space_and_stale_chart_cannot_select_records(self):
        win = self.win
        selected = win.findings.selection()
        win._chart_click(SimpleNamespace(x=2, y=12))
        self.assertEqual(win.findings.selection(), selected)
        self.click(1)
        win._changed()
        self.assertEqual(win._chart_points, [])
        self.assertEqual(win.chart_readout.cget("text"), "")
        self.assertIsNone(win._chart_reveal)
        win._chart_click(SimpleNamespace(x=58, y=82))
        self.assertEqual(win.findings.get_children(), ())

    def test_rule_only_chart_is_hidden_and_missing_numeric_data_is_explicit(self):
        win = self.win
        settings = config(
            features=[], rules=[dict(name="High", field="reading", op="gt", value=50)]
        )
        win.current, win.reference, win.run_config, win.result = case(win.current, settings)
        win._render_findings()
        self.assertEqual(win._chart_points, [])
        self.assertEqual(win.chart_frame.winfo_manager(), "")
        win.current, win.reference, win.run_config, win.result = case(
            dataset([{"reading": None}]), config()
        )
        win._render_findings()
        self.assertEqual(win.chart_frame.winfo_manager(), "pack")
        labels = [
            win.timeline.itemcget(item, "text")
            for item in win.timeline.find_all()
            if win.timeline.type(item) == "text"
        ]
        self.assertIn("No numeric values to plot.", labels)


if __name__ == "__main__":
    unittest.main(verbosity=2)
