"""Adversarial contract checks for versioned owned-app integrity evidence.

These fixtures test parser and approval boundaries, not authenticity of a local
collector. A consistent forged source remains outside this trust boundary.
"""

import copy
import hashlib
import json
import unittest
from unittest.mock import patch

import desktop_worker
import engine
import integrity_manifest
import native_integrity as native
import native_stream as stream


def versioned_capture():
    code = "908bc1c3"
    ranges = [
        dict(
            range_name=name,
            range_rva=rva,
            range_size=4,
            reference_hex=code,
            reference_sha256=hashlib.sha256(bytes.fromhex(code)).hexdigest(),
        )
        for name, rva in (("LabCodeProbe", 0x1000), ("LabCodeSecondary", 0x2000))
    ]
    manifest = dict(
        schema="surge-integrity-manifest-v1",
        architecture="x64",
        module_sha256="a" * 64,
        module_size=4096,
        image_size=0x5000,
        relocation_policy="reject",
        descriptor_version=1,
        executable_bytes=512,
        checked_bytes=8,
        excluded_bytes=504,
        ranges=copy.deepcopy(ranges),
        executable_ranges=[dict(range_rva=rva, range_size=256) for rva in (0x1000, 0x2000)],
        exclusions=[
            dict(range_rva=rva + 4, range_size=252, reason="not_declared")
            for rva in (0x1000, 0x2000)
        ],
    )
    return dict(
        schema="native-code-capture-v2",
        ranges=ranges,
        integrity_manifest=manifest,
        observations=[
            dict(
                spec,
                schema="native-code-range-v1",
                module_sha256=manifest["module_sha256"],
                module_size=manifest["module_size"],
                memory_status="complete",
                observed_hex=code,
                page_protection=32,
                session_id="1-start",
                captured_at="2026-01-01T00:00:00Z",
                process_started="1",
                pid=1,
                phase=phase,
                scenario="clean",
                build="v1",
            )
            for phase in native.PHASES
            for spec in ranges
        ],
    )


class IntegrityManifestSecurityTests(unittest.TestCase):
    def setUp(self):
        self.capture = versioned_capture()
        self.manifest = self.capture["integrity_manifest"]
        self.empty = dict(schema=native.BASELINE_SCHEMA, entries=[])

    def validate(self, value):
        return integrity_manifest.validate(
            value,
            self.capture["ranges"],
            self.capture["observations"][0]["module_sha256"],
            self.capture["observations"][0]["module_size"],
        )

    def test_valid_manifest_covers_declared_executable_bytes(self):
        self.assertEqual(self.validate(self.manifest), self.manifest)

    def test_versions_architecture_unknown_keys_and_identity_rejected(self):
        for key, value in (
            ("schema", "surge-integrity-manifest-v2"),
            ("descriptor_version", 2),
            ("descriptor_version", True),
            ("architecture", "x86"),
            ("relocation_policy", "mask"),
            ("module_sha256", "b" * 64),
            ("module_size", 4095),
            ("ignored_security_option", True),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.validate(dict(self.manifest, **{key: value}))

    def test_dimensions_are_bounded_integers_not_boolean_or_floating(self):
        for key in (
            "module_size",
            "image_size",
            "executable_bytes",
            "checked_bytes",
            "excluded_bytes",
        ):
            for value in (True, False, -1, 1.5, 2**64):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    integrity_manifest.validate(dict(self.manifest, **{key: value}))

    def test_missing_duplicated_and_overlapping_exclusions_rejected(self):
        mutations = []
        value = copy.deepcopy(self.manifest)
        value["exclusions"].pop()
        value["excluded_bytes"] -= 252
        value["executable_bytes"] -= 252
        mutations.append(value)
        value = copy.deepcopy(self.manifest)
        value["exclusions"].append(copy.deepcopy(value["exclusions"][0]))
        value["excluded_bytes"] += 252
        value["executable_bytes"] += 252
        mutations.append(value)
        value = copy.deepcopy(self.manifest)
        value["exclusions"][0]["range_rva"] -= 1
        mutations.append(value)
        for value in mutations:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.validate(value)

    def test_matching_byte_total_does_not_hide_gap_or_non_executable_span(self):
        for rva in (0x1005, 0x3000, 0x4FFF):
            value = copy.deepcopy(self.manifest)
            value["exclusions"][0]["range_rva"] = rva
            with self.subTest(rva=rva), self.assertRaises(ValueError):
                self.validate(value)

    def test_executable_overlap_zero_size_and_image_overflow_rejected(self):
        for key, value in (
            ("range_rva", 0x1001),
            ("range_size", 0),
            ("range_size", True),
            ("range_rva", 0x4FFF),
        ):
            bad = copy.deepcopy(self.manifest)
            bad["executable_ranges"][1][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.validate(bad)

    def test_range_identity_and_exclusion_reason_cannot_silently_change(self):
        bad = copy.deepcopy(self.manifest)
        bad["ranges"][1]["range_name"] = "AnotherRoutine"
        with self.assertRaises(ValueError):
            self.validate(bad)
        bad = copy.deepcopy(self.manifest)
        bad["exclusions"][0]["reason"] = "trusted"
        with self.assertRaises(ValueError):
            self.validate(bad)

    def test_approval_is_bound_to_complete_manifest(self):
        approved = native.approve(self.capture, self.empty, "Reviewed coverage")
        rows = native.convert(self.capture, approved)
        self.assertTrue(all(r["baseline_approved"] for r in rows))
        self.assertTrue(
            all(r["integrity_manifest_sha256"] == native.digest(self.manifest) for r in rows)
        )
        changed = copy.deepcopy(self.capture)
        # A changed coverage policy needs another explicit approval, even when
        # selected bytes and the module file identity have not changed.
        changed["integrity_manifest"]["exclusions"][0]["reason"] = "loader_fixup"
        rows = native.convert(changed, approved)
        self.assertTrue(all(r["baseline_approved"] is False for r in rows))

    def test_legacy_and_versioned_approvals_do_not_silently_cross(self):
        versioned_approval = native.approve(self.capture, self.empty, "Versioned review")
        legacy = copy.deepcopy(self.capture)
        del legacy["integrity_manifest"]
        legacy_approval = native.approve(legacy, self.empty, "Historical review")
        for capture, approval in (
            (legacy, versioned_approval),
            (self.capture, legacy_approval),
        ):
            with self.subTest(versioned="integrity_manifest" in capture):
                rows = native.convert(capture, approval)
                self.assertTrue(all(r["baseline_approved"] is False for r in rows))

    def test_raw_rows_cannot_launder_manifest_metadata_into_legacy_approval(self):
        legacy = copy.deepcopy(self.capture)
        del legacy["integrity_manifest"]
        approved = native.approve(legacy, self.empty, "Historical review")
        for row in legacy["observations"]:
            row.update(
                integrity_manifest=json.dumps(
                    self.manifest, sort_keys=True, separators=(",", ":")
                ),
                integrity_manifest_sha256=native.digest(self.manifest),
            )
        with self.assertRaises(ValueError):
            native.convert(legacy, approved)

    def test_legacy_capture_schema_cannot_hide_versioned_metadata(self):
        bad = copy.deepcopy(self.capture)
        bad["schema"] = "native-code-capture-v1"
        with self.assertRaises(ValueError):
            native.validate_capture(bad)

    def test_import_rejects_partial_or_inconsistent_manifest_metadata(self):
        approved = native.approve(self.capture, self.empty, "Reviewed coverage")
        rows = native.convert(self.capture, approved)
        for key in ("integrity_manifest", "integrity_manifest_sha256"):
            bad = copy.deepcopy(rows)
            del bad[1][key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                native.default_policy(
                    engine.parse_bytes(json.dumps(bad).encode(), "native.json")
                )
        bad = copy.deepcopy(rows)
        bad[1]["integrity_manifest_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            native.default_policy(engine.parse_bytes(json.dumps(bad).encode(), "native.json"))

    def test_stream_ready_manifest_does_not_allow_different_module_identity(self):
        ready = dict(
            schema=stream.STREAM_SCHEMA,
            type="ready",
            build="v1",
            ranges=self.capture["ranges"],
            integrity_manifest=self.manifest,
            interval_ms=500,
            duration_ms=1000,
        )
        raw = copy.deepcopy(self.capture["observations"][:2])
        for row in raw:
            row.pop("scenario")
            row.update(phase="live", module_sha256="b" * 64)
        sample = dict(
            schema=stream.STREAM_SCHEMA,
            type="sample",
            sequence=1,
            elapsed_ms=0,
            dropped_samples=0,
            observations=raw,
        )
        decoder = stream.StreamDecoder(self.empty)
        decoder.accept(ready)
        with self.assertRaises(ValueError):
            decoder.accept(sample)

    def test_inspector_distinguishes_declared_scope_from_successful_reads(self):
        approved = native.approve(self.capture, self.empty, "Reviewed coverage")
        self.capture["observations"][2].update(memory_status="failed", observed_hex=None)
        rows = native.convert(self.capture, approved)
        data = engine.parse_bytes(json.dumps(rows).encode(), "native.json")
        workspace = desktop_worker.Workspace()
        with patch.object(engine, "load_dataset", return_value=data):
            workspace.dispatch("import", {"role": "current", "path": "native.json"})
        workspace.dispatch("analyze", {"revision": workspace.revision})
        failed = workspace.dispatch("evidence", {"revision": workspace.revision, "row": 3})
        clean = workspace.dispatch("evidence", {"revision": workspace.revision, "row": 4})
        self.assertEqual(failed["status"], "Unknown")
        self.assertEqual(clean["status"], "No finding")
        for evidence in (failed, clean):
            coverage = next(
                group for group in evidence["groups"] if group["field"] == "Coverage"
            )
            self.assertEqual(coverage["value"], "1/2 ranges read")
            self.assertIn("8/512 executable bytes in scope", coverage["lines"][0]["text"])
            details = coverage["lines"][0]["details"]
            self.assertIn("4/8 configured bytes read", details)
            self.assertIn("504 bytes outside declared checks", details)
            self.assertIn(native.digest(self.manifest), details)
            self.assertIn("not whole-DLL verification", details)


if __name__ == "__main__":
    unittest.main()
