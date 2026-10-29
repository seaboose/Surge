"""Desktop admission order must survive moving handlers into separate modules."""

import copy
import unittest

from desktop_worker import Workspace
import engine


VIEW_OPERATIONS = (
    "labels_template", "labels_load", "evaluation", "evaluation_save",
    "preview", "inspect", "record_step", "copy",
    "findings", "evidence", "chart", "chart_step",
    "save", "alerts", "compare", "comparison", "details",
)


class DesktopAdmissionTests(unittest.TestCase):
    def test_stale_requests_and_missing_sources_fail_before_operation_arguments(self):
        workspace = Workspace()
        for method in (*VIEW_OPERATIONS, "unknown"):
            with self.subTest(method=method):
                with self.assertRaisesRegex(ValueError, "Data or settings changed"):
                    workspace.dispatch(method, {"revision": -1})
                with self.assertRaisesRegex(ValueError, "Import data or open a case first"):
                    workspace.dispatch(method, {"revision": workspace.revision})
        self.assertIsNone(workspace.current)
        self.assertIsNone(workspace.result)
        self.assertIsNone(workspace.labels)

    def test_unknown_operations_do_not_resolve_module_or_attribute_names(self):
        workspace = Workspace()
        workspace.current = engine.parse_bytes(b'[{"value":1}]', "one.json")
        before = copy.deepcopy(workspace.snapshot())
        for method in ("unknown", "desktop_records.handle", "__dict__", None, [], {}):
            with self.subTest(method=method):
                with self.assertRaisesRegex(ValueError, "Unsupported operation"):
                    workspace.dispatch(method, {"revision": workspace.revision})
                self.assertEqual(workspace.snapshot(), before)

    def test_analysis_guard_does_not_block_raw_evidence_inspection(self):
        workspace = Workspace()
        workspace.current = engine.parse_bytes(b'[{"value":9007199254740993}]', "one.json")
        args = {"revision": workspace.revision, "row": 1}
        for method in (
            "labels_load", "evaluation", "evaluation_save", "findings", "evidence",
            "chart", "chart_step", "save", "alerts", "compare", "comparison", "details",
        ):
            with self.subTest(method=method):
                with self.assertRaisesRegex(ValueError, "Analyze the current settings first"):
                    workspace.dispatch(method, args)
        inspected = workspace.dispatch("inspect", args)
        self.assertEqual(inspected["fields"][0]["value"], "9007199254740993")
        copied = workspace.dispatch("copy", dict(args, scope="value", field="value"))
        self.assertEqual(copied, {"text": "9007199254740993"})
        self.assertIsNone(workspace.result)


if __name__ == "__main__":
    unittest.main()
