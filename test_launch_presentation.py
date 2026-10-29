"""Trusted launch placement stays outside evidence and renderer request arguments."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from desktop_worker import Workspace
from survive_workspace import SurviveWorkspace
from scripts.check_windows_package import restricted_environment


class LaunchPresentationTests(unittest.TestCase):
    def test_worker_bootstrap_threads_a_validated_copy_to_survive(self):
        bounds = {"x": -1044, "y": 48, "width": 1008, "height": 567}
        workspace = Workspace(game_window=bounds)
        bounds["x"] = 9000
        try:
            with patch("survive_workspace.SurviveWorkspace") as factory:
                workspace.dispatch("survive_sources", {})
                self.assertEqual(factory.call_args.kwargs["game_window"]["x"], -1044)
                factory.return_value.dispatch.assert_called_once_with("survive_sources", {})
        finally:
            workspace.close()

    def test_study_receives_constructor_presentation_without_request_fields(self):
        bounds = {"x": -1044, "y": 48, "width": 1008, "height": 567}
        workspace = SurviveWorkspace(game_window=bounds)
        bounds["x"] = 9000
        try:
            with patch("survive_study.StudyManager") as factory:
                self.assertIs(workspace.study, factory.return_value)
                self.assertEqual(factory.call_args.kwargs["game_window"]["x"], -1044)
        finally:
            workspace.close()

    def test_worker_rejects_invalid_presentation_at_bootstrap(self):
        with self.assertRaises(ValueError):
            Workspace(game_window={"command": "quit"})

    def test_restricted_package_environment_preserves_only_optional_presentation(self):
        config = '{"point":{"x":-540,"y":936},"hidden":true}'
        with patch.dict(os.environ, {"SystemRoot": "C:/Windows", "SURGE_PRESENTATION": config,
                                     "NODE_OPTIONS": "untrusted", "SURGE_OTHER": "untrusted"}, clear=True):
            env = restricted_environment(Path("C:/owned-test-temp"))
        self.assertEqual(env["SURGE_PRESENTATION"], config)
        self.assertNotIn("NODE_OPTIONS", env)
        self.assertNotIn("SURGE_OTHER", env)
        with patch.dict(os.environ, {"SystemRoot": "C:/Windows"}, clear=True):
            self.assertNotIn("SURGE_PRESENTATION", restricted_environment(Path("C:/owned-test-temp")))


if __name__ == "__main__":
    unittest.main()
