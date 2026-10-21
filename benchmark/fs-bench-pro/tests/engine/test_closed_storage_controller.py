"""Synthetic controller bindings; no actual Docker or case qualification."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import receipts, workspace


class ClosedStorageController(unittest.TestCase):
    def test_actual_source_command_and_stream_hashes_are_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            runtime = SimpleNamespace(container='a' * 64)
            calls = []
            def command(argv, output, label, seconds):
                calls.append(argv)
                stdout = output / (label + '.stdout')
                stdout.write_text('{}\n')
                receipts.write_new(output / (label + '.completion.json'), {'argv': argv, 'status': 'PASS'})
                return {'stdout': str(stdout)}
            with patch.object(receipts, 'command', side_effect=command):
                bound = workspace.storage_source_observations(runtime, {'socket': '/socket'}, home, lambda n: n)
            self.assertEqual(len(calls), 2)
            for kind, argv in zip(('store', 'overlay'), calls):
                self.assertEqual(argv[3:9], ['exec', '--user', '0:0', runtime.container, 'python3', '-B'])
                self.assertEqual(argv[9:], ['-c', workspace.oracle.storage_source_stat_body(kind)])
                self.assertEqual(bound[kind]['stdout_sha256'], workspace.identity.sha256(bound[kind]['stdout']))
                self.assertEqual(bound[kind]['completion_sha256'], workspace.identity.sha256(bound[kind]['completion']))

    def test_every_actual_mounted_token_is_bound_without_physical_zero(self):
        for store_status, cleanup_status, files_status in [('PASS', 'PASS', 'PASS'), ('FAIL', 'PASS', 'PASS'),
                                                           ('PASS', 'FAIL', 'PASS'), ('PASS', 'PASS', 'FAIL')]:
            with self.subTest(store=store_status, cleanup=cleanup_status, files=files_status), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary)
                events = home / 'runtime.events.jsonl'
                events.write_text('synthetic-only\n')
                runtime = SimpleNamespace(container='a' * 64, rows=[
                    {'event': 'mount', 'fields': {'key': 'paid', 'workspace_namespace': 1, 'workspace_incarnation': '01' * 32}},
                    {'event': 'mount', 'fields': {'key': 'proof', 'workspace_namespace': 2, 'workspace_incarnation': '02' * 32}}])
                row = {'custody': 'KNOWN_STOP', 'clone': {'volume': 'layerfs-fsb-sample-synthetic'}}
                calls = []
                commands = []
                def command(argv, output, label, seconds):
                    commands.append(argv[3:])
                    receipts.write_new(output / (label + '.completion.json'), {'argv': argv})
                    if argv[5] == '-':
                        # The archive of the stopped overlay directory, on the command's stdout.
                        stdout = output / (label + '.stdout')
                        stdout.write_bytes(b'synthetic-not-archive')
                        return {'stdout': str(stdout)}
                    Path(argv[5]).write_bytes(b'synthetic-not-database')
                def observe(path, custody, *, kind, owners=()):
                    calls.append((kind, custody, owners))
                    return ({'source_main_store_4gib_status': store_status} if kind == 'store' else
                            {'namespace_cleanup_status': cleanup_status, 'owned_files_after_cleanup_status': files_status})
                with patch.object(receipts, 'command', side_effect=command), patch.object(workspace.oracle, 'observe_closed_storage', side_effect=observe):
                    operation = lambda: workspace.observe_family_closed_storage(runtime, row, {'socket': '/socket'}, home, home / 'store', {'normalization': 'binding'}, {'store': 'native-source-store', 'overlay': 'native-source-overlay'}, lambda n: n)
                    if store_status == cleanup_status == files_status == 'PASS':
                        operation()
                    else:
                        with self.assertRaisesRegex(ValueError, 'boundary or exact Workspace file cleanup'):
                            operation()
                self.assertEqual(commands, [
                    ['cp', runtime.container + ':/layerfs-local/overlay/overlay.sqlite', str(home / 'closed-overlay.sqlite')],
                    ['cp', runtime.container + ':/layerfs-local/overlay', '-']])
                directory = calls[1][1]['directory']
                self.assertEqual(directory['stdout_sha256'], workspace.identity.sha256(directory['stdout']))
                self.assertEqual(directory['completion_sha256'], workspace.identity.sha256(directory['completion']))
                self.assertEqual(calls[0][1]['source_stat'], 'native-source-store')
                self.assertEqual(calls[1][1]['source_stat'], 'native-source-overlay')
                self.assertEqual([owner['key'] for owner in calls[1][2]], ['paid', 'proof'])
                self.assertEqual([owner['namespace'] for owner in calls[1][2]], [1, 2])
                record = json.loads((home / 'closed-storage-observations.json').read_text())
                self.assertEqual(record['original_physical_resource_status'], 'UNAVAILABLE')


if __name__ == '__main__':
    unittest.main()
