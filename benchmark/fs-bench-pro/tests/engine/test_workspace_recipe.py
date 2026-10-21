"""Native checkpoint generation/verification without a Store, mount or sample."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

BENCH = Path(__file__).resolve().parents[2]
ROOT = BENCH.parents[1]


class NativeCheckpointRecipe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.writer = Path(os.environ.get("WORKSPACE_RECIPE_TEST_WRITER", ROOT / "core/target/fsb-history-native-recipe"))
        if not cls.writer.is_file():
            raise unittest.SkipTest("build the private native recipe CLI before this scoped test")

    def call(self, *args, success=True):
        result = subprocess.run([str(self.writer), *map(str,args)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode == 0, success, result.stderr)
        return json.loads(result.stdout) if success else result

    def test_metadata_checkpoints_are_distinct_and_verification_is_read_only(self):
        with tempfile.TemporaryDirectory(prefix="fsb-native-step-test-") as temporary:
            home = Path(temporary)
            row1 = self.call("expected-step", "dedup-history-metadata-100", 1, home / "one")
            row2 = self.call("expected-step", "dedup-history-metadata-100", 2, home / "two")
            self.assertEqual((row1["files"], row1["entries"], row1["logical_bytes"]), (200,334,1048576))
            target = Path("wide/s000-f000.dat")
            self.assertEqual(stat.S_IMODE((home/"one"/target).stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE((home/"two"/target).stat().st_mode), 0o640)
            self.assertNotEqual(row1["fixture_digest"],row2["fixture_digest"])
            seal = (home/"one.manifest.tsv").read_bytes()
            proof = self.call("verify-step", "dedup-history-metadata-100",1,home/"one")
            self.assertEqual(proof["verification_status"],"pass")
            self.assertEqual(proof["fixture_digest"],row1["fixture_digest"])
            self.assertEqual((home/"one.manifest.tsv").read_bytes(),seal)
            self.call("verify-step","dedup-history-metadata-100",2,home/"one",success=False)
            self.assertEqual((home/"one.manifest.tsv").read_bytes(),seal)

    def test_selected_deep_recurring_state_matches_repeated_A_B_bytes(self):
        with tempfile.TemporaryDirectory(prefix="fsb-native-step-test-") as temporary:
            home = Path(temporary)
            rows = [self.call("expected-step","dedup-history-recurring-100",step,home/str(step)) for step in (0,1,2,99)]
            self.assertEqual(rows[0]["fixture_digest"],rows[2]["fixture_digest"])
            self.assertEqual(rows[1]["fixture_digest"],rows[3]["fixture_digest"])
            self.assertNotEqual(rows[0]["fixture_digest"],rows[1]["fixture_digest"])
            self.assertEqual(rows[3]["logical_bytes"],1048576)
            self.call("verify-step","dedup-history-recurring-100",99,home/"99")

    def test_namespace_alias_has_real_shared_inode_before_atomic_save(self):
        with tempfile.TemporaryDirectory(prefix="fsb-native-step-test-") as temporary:
            home = Path(temporary)
            self.call("expected-step","v016-history-namespace-inode-k10-v1",4,home/"four")
            self.call("expected-step","v016-history-namespace-inode-k10-v1",5,home/"five")
            target = home/"four/tiny-moved/t4.dat"; alias = home/"four/tiny-moved/a4.dat"
            self.assertEqual(target.stat().st_ino,alias.stat().st_ino)
            self.assertEqual(target.stat().st_nlink,2)
            self.assertFalse((home/"five/tiny-moved/a4.dat").exists())
            self.call("verify-step","v016-history-namespace-inode-k10-v1",4,home/"four")
            self.call("verify-step","v016-history-namespace-inode-k10-v1",5,home/"five")

    def test_original_step_envelope_and_existing_manifest_are_never_bypassed(self):
        with tempfile.TemporaryDirectory(prefix="fsb-native-step-test-") as temporary:
            home = Path(temporary)
            for step in (101,-1,"unknown"):
                self.call("expected-step","dedup-history-metadata-100",step,home/("invalid"+str(step)),success=False)
            manifest = home/"new.manifest.tsv";manifest.write_bytes(b"closed original evidence")
            self.call("expected-step","dedup-history-metadata-100",1,home/"new",success=False)
            self.assertEqual(manifest.read_bytes(),b"closed original evidence")
            self.assertFalse((home/"new").exists())

    def test_legacy_expected_mode_output_and_final_bytes_remain_compatible(self):
        with tempfile.TemporaryDirectory(prefix="fsb-native-step-test-") as temporary:
            home = Path(temporary)
            old = self.call("expected","dedup-history-distributed-1",home/"old")
            new = self.call("expected-step","dedup-history-distributed-1",1,home/"new")
            self.assertEqual(new.pop("step"),1)
            self.assertEqual(old,new)
            self.assertEqual((home/"old.manifest.tsv").read_bytes(),(home/"new.manifest.tsv").read_bytes())


class NativeM1SelectiveRecipe(unittest.TestCase):
    CASE = "v016-mixed-development-100mb-5000-k10-v1"

    @classmethod
    def setUpClass(cls):
        cls.writer = Path(os.environ.get("WORKSPACE_RECIPE_TEST_WRITER", ROOT / "core/target/fsb-history-native-recipe"))
        if not cls.writer.is_file():
            raise unittest.SkipTest("build the private composed native M1 recipe before this scoped test")

    def call(self, *args, success=True):
        result = subprocess.run([str(self.writer), *map(str,args)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode == 0, success, result.stderr)
        return json.loads(result.stdout) if success else result

    @unittest.skipUnless(sys.platform == 'darwin', 'Darwin lstat interposer count tier')
    def test_each_namespace_path_pays_for_one_metadata_call(self):
        counter = Path(os.environ['FSBP_LSTAT_COUNTER']).resolve(strict=True)
        with tempfile.TemporaryDirectory(prefix='fsb-native-m1-count-') as temporary:
            home = Path(temporary).resolve()
            root = home / 'initial'
            modes = home / 'created.tsv'
            modes.write_bytes(b'')
            fixture = self.call('expected-step', self.CASE, 0, root)
            manifest = (home / 'initial.manifest.tsv').read_bytes()
            result = subprocess.run([str(self.writer), 'verify-m1-step', self.CASE,
                '0', str(root), str(modes)], capture_output=True, text=True, timeout=30,
                env={**os.environ, 'DYLD_INSERT_LIBRARIES': str(counter), 'FSBP_LSTAT_ROOT': str(root)})
            self.assertEqual(result.returncode, 0, result.stderr)
            proof = json.loads(result.stdout)
            self.assertEqual(proof['verification_status'], 'pass')
            self.assertEqual(proof['entries'], fixture['entries'])
            self.assertEqual((home / 'initial.manifest.tsv').read_bytes(), manifest)
            lines = result.stderr.splitlines()
            self.assertEqual(lines.count('FSBP_LSTAT_COUNTER_ACTIVE=1'), 1, result.stderr)
            counts = [int(line.split('=', 1)[1]) for line in lines
                      if line.startswith('FSBP_LSTAT_COUNTER_COUNT=')]
            self.assertEqual(len(counts), 1, result.stderr)
            self.assertGreater(counts[0], 0)
            self.assertEqual(counts[0], fixture['entries'])
            print(json.dumps({'case': self.CASE, 'step': 0, 'entries': fixture['entries'],
                              'metadata_calls': counts[0], 'counter_active': True}))

    def test_original_selective_ranges_and_unconstrained_automatic_metadata(self):
        with tempfile.TemporaryDirectory(prefix="fsb-native-m1-scope-test-") as temporary:
            home = Path(temporary); root = home/"step2"; modes = home/"created.tsv"; modes.write_bytes(b"")
            self.call("expected-step", self.CASE, 2, root)
            manifest = (home/"step2.manifest.tsv").read_bytes()
            rows = [line.split("\t") for line in manifest.decode().splitlines()[1:]]
            exact = next(row[0] for row in rows if row[1] == "file" and int(row[2]) == 131072)
            tiny = next(row[0] for row in rows if row[1] == "file" and int(row[2]) == 4096)
            first = self.call("verify-m1-step", self.CASE, 2, root, modes)
            self.assertEqual(first["scope"], "original-m1-selective-scope-v1")
            self.assertEqual(first["verification_status"], "pass")
            # Frozen exhaustive proofs may bind the final cumulative helper
            # map even though this selected state predates stage3 creation.
            modes.write_text("d055x\t750\n")
            (root/tiny).chmod(0o600)
            os.utime(root/tiny, ns=(1800000000000000000,)*2)
            os.utime(root, ns=(1800000000000000000,)*2)
            with (root/exact).open("r+b") as output:
                byte = output.read(1); output.seek(0); output.write(bytes([byte[0]^1]))
            second = self.call("verify-m1-step", self.CASE, 2, root, modes)
            self.assertEqual(first["scope_digest"], second["scope_digest"])
            self.assertEqual((home/"step2.manifest.tsv").read_bytes(), manifest)
            refused = self.call("verify-step", self.CASE, 2, root, success=False)
            self.assertIn("selective", refused.stderr)
            with (root/tiny).open("r+b") as output:
                byte = output.read(1); output.seek(0); output.write(bytes([byte[0]^1]))
            failed = self.call("verify-m1-step", self.CASE, 2, root, modes, success=False)
            self.assertIn("declared byte range differs", failed.stderr)

    def test_streamed_membership_kind_symlink_and_alias_checks_refuse_corruption(self):
        with tempfile.TemporaryDirectory(prefix='fsb-native-m1-membership-') as temporary:
            home = Path(temporary)
            root = home / 'initial'
            modes = home / 'created.tsv'
            modes.write_bytes(b'')
            self.call('expected-step', self.CASE, 4, root)
            rows = [line.split('\t') for line in
                    (home / 'initial.manifest.tsv').read_text().splitlines()[1:]]
            created = [row[0] for row in rows if row[1] == 'directory' and row[0].endswith('x')]
            self.assertEqual(len(created), 8)
            modes.write_text(''.join(f'{path}\t{stat.S_IMODE((root / path).stat().st_mode):o}\n'
                                     for path in created))
            self.call('verify-m1-step', self.CASE, 4, root, modes)
            extra = root / 'unlisted'
            extra.touch()
            refused = self.call('verify-m1-step', self.CASE, 4, root, modes, success=False)
            self.assertIn('namespace differs', refused.stderr)
            extra.unlink()
            regular = root / next(row[0] for row in rows if row[1] == 'file' and int(row[2]) == 0)
            regular.unlink()
            regular.mkdir()
            refused = self.call('verify-m1-step', self.CASE, 4, root, modes, success=False)
            self.assertIn('kind differs', refused.stderr)
            regular.rmdir()
            regular.touch()
            symlink = root / next(row[0] for row in rows if row[1] == 'symlink')
            target = os.readlink(symlink)
            symlink.unlink()
            symlink.symlink_to('wrong-target')
            refused = self.call('verify-m1-step', self.CASE, 4, root, modes, success=False)
            self.assertIn('symlink target/length differs', refused.stderr)
            symlink.unlink()
            symlink.symlink_to(target)
            alias = root / next(row[0] for row in rows if row[1] == 'hardlink')
            contents = alias.read_bytes()
            alias.unlink()
            alias.write_bytes(contents)
            refused = self.call('verify-m1-step', self.CASE, 4, root, modes, success=False)
            self.assertTrue('link count differs' in refused.stderr or
                            'inode classes differ' in refused.stderr, refused.stderr)

    def test_missing_or_undeclared_helper_observations_fail_before_native_access(self):
        with tempfile.TemporaryDirectory(prefix="fsb-native-m1-scope-test-") as temporary:
            home = Path(temporary); modes=home/"created.tsv"; modes.write_bytes(b"")
            missing = self.call("verify-m1-step", self.CASE, 3, home/"absent", modes, success=False)
            self.assertIn("created mode missing", missing.stderr)
            for content in ("../unsafe\t750\n", "undeclared/path\t750\n", "name\tbad\n",
                            "d055x\t2000\n", "d055x\t750\nd055x\t750\n"):
                modes.write_text(content)
                self.call("verify-m1-step", self.CASE, 2, home/"absent", modes, success=False)
            modes.write_bytes(b"")
            self.call("verify-m1-step", "dedup-history-metadata-100", 1, home/"absent", modes, success=False)
            self.call("expected-step", self.CASE, 11, home/"outside", success=False)


if __name__ == "__main__":
    unittest.main()
