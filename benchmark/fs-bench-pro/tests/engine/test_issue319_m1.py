"""The native M1 atomic save preserves the explicit destination timestamp."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class AtomicSaveTimestamp(unittest.TestCase):
    def test_replacement_sets_mtime_after_its_payload_write(self):
        recipe = os.environ['WORKSPACE_RECIPE_TEST_WRITER']
        workload = os.environ['M1_WORKLOAD_TEST_WRITER']
        case = 'v016-mixed-development-100mb-5000-k10-v1'
        with tempfile.TemporaryDirectory(dir=ROOT / 'core/target') as temporary:
            root = Path(temporary) / 'native'
            made = subprocess.run([recipe, 'expected-step', case, '4', str(root)],
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(made.returncode, 0, made.stderr)
            before = {p.relative_to(root): (p.stat().st_ino, p.stat().st_mtime_ns)
                      for p in root.rglob('*') if p.is_file() and not p.is_symlink()}
            changed = subprocess.run([workload, 'v016-m1-stage', 'L100', '1', '1', '0', 'branch0', '5'],
                                     cwd=root, capture_output=True, text=True, timeout=30)
            self.assertEqual(changed.returncode, 0, changed.stderr)
            replacements = [(p, old, (root / p).stat()) for p, old in before.items()
                            if (root / p).is_file() and not (root / p).is_symlink()
                            and (root / p).stat().st_ino != old[0]
                            and old[1] != 1700000000000000000]
            self.assertEqual(len(replacements), 4)
            for path, (_, expected), actual in replacements:
                self.assertEqual(actual.st_mtime_ns, expected, str(path))
            fields = dict(line.split('=', 1) for line in changed.stdout.splitlines())
            self.assertEqual(fields['m1_syscall_temporary_create'], '4')
            self.assertEqual(fields['m1_syscall_rename_overwrite'], '4')
            self.assertEqual(fields['m1_oracle_reads'], '0')


class FrozenSourceRouting(unittest.TestCase):
    def test_only_timestamp_order_differs_from_the_frozen_helper(self):
        original = (ROOT / 'benchmark/fs-bench-pro/workload/v016_m1.rs').read_text()
        corrected = (ROOT / 'benchmark/fs-bench-pro/writers/v016_m1.rs').read_text()
        before = ('            set_mtime(&temporary, replacement_seconds, replacement_nanos)?;\n'
                  '            file.write_all(&bytes)?;')
        after = ('            file.write_all(&bytes)?;\n'
                 '            set_mtime(&temporary, replacement_seconds, replacement_nanos)?;')
        self.assertEqual(original.count(before), 1)
        self.assertEqual(corrected, original.replace(before, after))


if __name__ == '__main__':
    unittest.main()
