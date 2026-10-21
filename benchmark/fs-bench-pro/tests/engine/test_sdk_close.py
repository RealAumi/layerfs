"""Public SDK setup close must be acknowledged and independently observed for the exact owner."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import project


class SetupClose(unittest.TestCase):
    def invoke(self, exit_code, stderr, stdout=None):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            folder = root / 'provision'
            container = 'a' * 64
            calls = []

            def command(argv, output, label, seconds, **options):
                calls.append((argv, label, options))
                if label == 'sdk-provision':
                    (folder / 'store.sqlite').write_bytes(b'actual sealed test input')
                    (folder / 'installed.manifest').write_bytes(b'original install acknowledgement')
                    (folder / 'provision.events.jsonl').write_text(
                        json.dumps({'event': 'setup_container_stopped', 'value': container}) + '\n'
                        + json.dumps({'event': 'finished'}) + '\n')
                    return {'exit_code': 0, 'argv': argv}
                self.assertEqual(label, 'setup-container-state')
                self.assertEqual(argv[-3:], [container, '--format', '{{.State.Running}}'])
                self.assertTrue(options['allow_failure'])
                out, err = folder / 'inspect.stdout', folder / 'inspect.stderr'
                out.write_text(stdout if stdout is not None else 'false\n' if exit_code == 0 else '')
                err.write_text(stderr)
                return {'exit_code': exit_code, 'stdout': str(out), 'stderr': str(err)}

            with patch.object(project.receipts, 'command', side_effect=command):
                result = project.provision(source, 'owned-volume', folder,
                    {'socket': '/exact/test/socket', 'binaries': {'runtime': {'path': '/runtime'}, 'daemon': {'path': '/daemon'}}})
            self.assertEqual([label for _, label, _ in calls], ['sdk-provision', 'setup-container-state'])
            self.assertEqual(result['status'], 'PASS')
            self.assertEqual(result['container'], container)
            self.assertIn('stop/delete', result['container_disposition'])
            return result

    def test_exact_absence_after_acknowledged_close_keeps_borrowed_store_and_original_identity(self):
        self.invoke(1, 'Error: No such object: ' + 'a' * 64 + '\n')

    def test_observed_lowercase_cli_absence_preserves_the_exact_acknowledged_identity(self):
        self.invoke(1, 'error: no such object: ' + 'a' * 64 + '\n')

    def test_output_cannot_claim_an_object_alongside_an_absence_error(self):
        with self.assertRaisesRegex(ValueError, 'exact independent deletion'):
            self.invoke(1, 'error: no such object: ' + 'a' * 64, stdout='false\n')

    def test_stopped_but_present_is_not_a_completed_close(self):
        with self.assertRaisesRegex(ValueError, 'exact independent deletion'):
            self.invoke(0, '')

    def test_a_different_missing_container_does_not_qualify_the_owned_close(self):
        with self.assertRaisesRegex(ValueError, 'exact independent deletion'):
            self.invoke(1, 'Error: No such object: ' + 'b' * 64)
        with self.assertRaisesRegex(ValueError, 'exact independent deletion'):
            self.invoke(1, 'error: no such object: ' + 'b' * 64)

    def test_unknown_inspect_failure_does_not_become_known_deletion(self):
        with self.assertRaisesRegex(ValueError, 'exact independent deletion'):
            self.invoke(1, 'Cannot connect to the Docker daemon')
