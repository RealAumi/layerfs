"""Native qualification of the shared bounded Unix splice writer."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "benchmark/fs-bench-pro"))
from engine import identity


class NativeSpliceWriter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Compilation precedes this invocation. A shared immutable build is
        # reusable only when every compiled input and binary still matches.
        cls.build = identity.load_build(Path(os.environ["LAYERFS_EDIT_WRITER_BUILD"]))
        cls.writer = cls.build["binaries"]["edit-host"]["path"]
        cls.fixture = cls.build["binaries"]["workspace-writer"]["path"]
        cls.workload = cls.build["binaries"]["workload-host"]["path"]
        cls.temporary = tempfile.TemporaryDirectory(prefix="edit-writer-native-", dir=ROOT / "core/target")
        cls.folder = Path(cls.temporary.name)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def fixture_root(self, case, label):
        path = self.folder / label
        completed = subprocess.run([self.fixture, "fixture", case, str(path)], cwd=ROOT,
                                   capture_output=True, text=True, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return path

    def command(self, root, *args):
        return subprocess.run([self.writer, *args], cwd=root, capture_output=True, text=True, timeout=15)

    def test_original_overwrite_and_all_splice_shapes_preserve_complete_tree(self):
        ids = ["overwrite-middle-4k-on-1mib-ops-1",
               "insert-middle-4k-on-1mib-ops-1",
               "delete-middle-4k-on-1mib-ops-1", "append-tail-4k-on-1mib-ops-1",
               "prepend-head-4k-on-1mib-ops-1", "replace-grow-middle-2k-to-4k-on-1mib-ops-1",
               "replace-shrink-middle-4k-to-2k-on-1mib-ops-1", "truncate-tail-4k-on-1mib-ops-1",
               "zero-extend-tail-4k-on-1mib-ops-1"]
        for index, case in enumerate(ids):
            with self.subTest(case=case):
                root = self.fixture_root(case, "splice-" + str(index))
                inode = (root / "payload.bin").stat().st_ino
                changed = self.command(root, "apply", case)
                self.assertEqual(changed.returncode, 0, changed.stderr)
                self.assertEqual((root / "payload.bin").stat().st_ino, inode)
                verified = self.command(root, "verify", case, "1")
                self.assertEqual(verified.returncode, 0, verified.stderr)
                fields = dict(line.split("=", 1) for line in verified.stdout.splitlines())
                self.assertEqual(fields["verification_status"], "pass")
                self.assertEqual(int(fields["verified_paths"]), 2)

    def test_wrong_input_length_is_refused_before_mutation(self):
        case = "overwrite-middle-4k-on-1mib-ops-1"
        root = self.fixture_root(case, "wrong-length")
        with (root / "payload.bin").open("r+b") as file:
            file.truncate(1_048_575)
        before = (root / "payload.bin").read_bytes()
        refused = self.command(root, "apply", case)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("fixture length differs", refused.stderr)
        self.assertEqual((root / "payload.bin").read_bytes(), before)

    def test_unchanged_byte_corruption_is_rejected_by_original_full_oracle(self):
        case = "overwrite-middle-4k-on-1mib-ops-1"
        root = self.fixture_root(case, "corrupted")
        changed = self.command(root, "apply", case)
        self.assertEqual(changed.returncode, 0, changed.stderr)
        with (root / "payload.bin").open("r+b") as file:
            original = file.read(1)
            file.seek(0)
            file.write(bytes([original[0] ^ 1]))
        os.utime(root / "payload.bin", ns=(1_700_000_000_000_000_000,) * 2)
        refused = self.command(root, "verify", case, "1")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("native content mismatch: payload.bin", refused.stderr)

    def test_named_boundary_sdk_steps_preserve_complete_bytes_metadata_and_inodes(self):
        schedules = {"small-control": [4096]*3, "below": [131071]*3,
                     "exact": [131072]*3, "above": [131073]*3,
                     "large-control": [1048576]*3,
                     "roundtrip": [131071,131072,131073,131072,131071]}
        for name, lengths in schedules.items():
            case = "v016-boundary-" + name + "-v1"
            with self.subTest(case=case):
                root = self.fixture_root(case, "named-"+name)
                target = root / "data/target.bin"
                witness = root / "data/witness.bin"
                initial_inode, witness_bytes = target.stat().st_ino, witness.read_bytes()
                for step, length in enumerate(lengths[1:], 1):
                    changed = self.command(root, "apply-sdk-step", case, str(step))
                    self.assertEqual(changed.returncode, 0, changed.stderr)
                    self.assertEqual(target.stat().st_size, length)
                    self.assertEqual(target.stat().st_ino, initial_inode)
                    self.assertEqual(witness.read_bytes(), witness_bytes)
                    self.assertEqual(target.stat().st_mode & 0o7777, 0o640)
                    self.assertEqual(target.stat().st_mtime_ns, 1700000000000000000)
                    verified = self.command(root, "verify", case, str(step))
                    self.assertEqual(verified.returncode, 0, verified.stderr)
                    self.assertIn("verification_status=pass", verified.stdout)

    def test_named_sdk_selection_and_wrong_length_refuse_before_mutation(self):
        case = "v016-boundary-small-control-v1"
        root = self.fixture_root(case, "named-refusal")
        target = root / "data/target.bin"
        before = target.read_bytes()
        for args in (("0",), ("1", "0"), ("1", "2")):
            refused = self.command(root, "apply-sdk-step", case, *args)
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(target.read_bytes(), before)
        with target.open("r+b") as file:
            file.truncate(4095)
        before = target.read_bytes()
        refused = self.command(root, "apply-sdk-step", case, "1", "1")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("fixture length differs", refused.stderr)
        self.assertEqual(target.read_bytes(), before)

    def prepare_payloads(self, root, case, step, label):
        output = self.folder / label
        made = self.command(root, "prepare-sdk-step", case, str(step), str(output))
        self.assertEqual(made.returncode, 0, made.stderr)
        record = json.loads(made.stdout)
        descriptor = output / "descriptor.tsv"
        self.assertEqual(record["descriptor_sha256"], hashlib.sha256(descriptor.read_bytes()).hexdigest())
        return descriptor, record["descriptor_sha256"]

    def test_prepared_original_boundary_bytes_cover_overwrite_growth_and_shrink(self):
        for name, count in (("exact", 2), ("roundtrip", 4)):
            case = "v016-boundary-" + name + "-v1"
            root = self.fixture_root(case, "prepared-" + name)
            inode = (root / "data/target.bin").stat().st_ino
            for step in range(1, count + 1):
                descriptor, digest = self.prepare_payloads(root, case, step, f"prepared-{name}-step-{step}")
                applied = self.command(root, "apply-sdk-step-prepared", case, str(step), str(descriptor), digest)
                self.assertEqual(applied.returncode, 0, applied.stderr)
                self.assertEqual((root / "data/target.bin").stat().st_ino, inode)
                verified = self.command(root, "verify", case, str(step))
                self.assertEqual(verified.returncode, 0, verified.stderr)

    def test_prepared_binding_payload_and_unsafe_geometry_refuse_before_mutation(self):
        case = "v016-boundary-small-control-v1"
        root = self.fixture_root(case, "prepared-refusal")
        target = root / "data/target.bin"
        before = target.read_bytes()
        descriptor, digest = self.prepare_payloads(root, case, 1, "prepared-refusal-payload")
        for selected_case, selected_step, selected_digest in ((case, "1", "0"*64),
                                                            (case, "2", digest),
                                                            ("v016-boundary-below-v1", "1", digest)):
            refused = self.command(root, "apply-sdk-step-prepared", selected_case, selected_step,
                                   str(descriptor), selected_digest)
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(target.read_bytes(), before)
        original = descriptor.read_text()
        fields = original.splitlines()
        row = fields[4].split("\t")
        row[1] = "../outside"
        fields[4] = "\t".join(row)
        descriptor.write_text("\n".join(fields)+"\n")
        unsafe_digest = hashlib.sha256(descriptor.read_bytes()).hexdigest()
        refused = self.command(root, "apply-sdk-step-prepared", case, "1", str(descriptor), unsafe_digest)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("row/path/member differs", refused.stderr)
        self.assertEqual(target.read_bytes(), before)
        descriptor.write_text(original)
        payload = descriptor.parent / "member-1.bin"
        data = payload.read_bytes()
        payload.write_bytes(bytes([data[0] ^ 1])+data[1:])
        refused = self.command(root, "apply-sdk-step-prepared", case, "1", str(descriptor), digest)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("payload length/hash differs", refused.stderr)
        self.assertEqual(target.read_bytes(), before)

    def test_prepared_m1_two_named_members_keep_selective_original_state(self):
        case = "v016-mixed-development-100mb-5000-k10-v1"
        root = self.folder / "prepared-m1"
        state = subprocess.run([self.fixture, "expected-step", case, "1", str(root)], cwd=ROOT,
                               capture_output=True, text=True, timeout=30)
        self.assertEqual(state.returncode, 0, state.stderr)
        descriptor, digest = self.prepare_payloads(root, case, 2, "prepared-m1-pair")
        native = subprocess.run([self.workload, "v016-m1-stage", "L100", "1", "1", "0", "branch0", "2"],
                                cwd=root, capture_output=True, text=True, timeout=30)
        self.assertEqual(native.returncode, 0, native.stderr)
        rows = descriptor.read_text().splitlines()[4:]
        self.assertEqual(len(rows), 2)
        selected = [root / row.split("\t")[1] for row in rows]
        initial = [path.stat().st_ino for path in selected]
        for member in (1, 2):
            changed = self.command(root, "apply-sdk-step-prepared", case, "2", str(descriptor), digest, str(member))
            self.assertEqual(changed.returncode, 0, changed.stderr)
        self.assertEqual([path.stat().st_ino for path in selected], initial)
        modes = self.folder / "prepared-m1-modes.tsv"
        modes.write_text("")
        verified = subprocess.run([self.fixture, "verify-m1-step", case, "2", str(root), str(modes)], cwd=ROOT,
                                  capture_output=True, text=True, timeout=30)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertEqual(json.loads(verified.stdout)["verification_status"], "pass")


if __name__ == "__main__":
    unittest.main()
