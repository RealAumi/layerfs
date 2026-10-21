"""Receipt-only harness checks; no Docker execution."""
import contextlib
import importlib.util
import io
import json
import os
import pathlib
import tempfile
import types
import unittest
from unittest.mock import patch


class Hygiene(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cxi-hygiene-')
        root = pathlib.Path(self.temp.name)
        with patch.dict(os.environ, IGN_RECEIPTS=str(root / 'receipts'), IGN_WORK=str(root / 'work')):
            spec = importlib.util.spec_from_file_location('ignore_e2e', pathlib.Path(__file__).with_name('run-ignore-e2e.py'))
            self.h = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.h)
        self.addCleanup(self.temp.cleanup)

    def test_receipt_paths_commands_and_outputs_are_redacted(self):
        home = str(pathlib.Path.home())
        response = types.SimpleNamespace(stdout=home + '/output', returncode=0)
        with patch.object(self.h.subprocess, 'run', return_value=response) as call:
            self.h.run(['echo', home + '/input'])
        self.assertEqual(call.call_args.args[0][1], home + '/input')
        row = json.loads(self.h.JSONL.read_text())
        self.assertEqual(row['command'], ['echo', '~/input'])
        self.assertEqual(row['output'], '~/output')
        with contextlib.redirect_stdout(io.StringIO()):
            self.h.say(home + '/console')
        self.assertEqual(self.h.CONSOLE.read_text(), '~/console\n')
        path = self.h.RECEIPTS / 'captured.log'
        self.h.receipt(path, home + '/log')
        self.assertEqual(path.read_text(), '~/log')

    def test_copied_logs_are_redacted(self):
        destination = self.h.RECEIPTS / 'cxi-daemon.log'
        def copy(args, **kw):
            pathlib.Path(args[-1]).write_text(str(pathlib.Path.home()) + '/daemon')
            return types.SimpleNamespace(stdout='', returncode=0)
        with patch.object(self.h.subprocess, 'run', side_effect=copy):
            self.h.docker('cp', 'cxi-b1:/state/daemon.log', str(destination))
        self.assertEqual(destination.read_text(), '~/daemon')

    def test_all_resource_listings_are_scoped_before_execution(self):
        with patch.object(self.h, 'out', return_value='') as listing:
            with self.assertRaisesRegex(AssertionError, 'missing: run the build phase'):
                self.h.Env().__enter__()
        self.assertEqual(len(listing.call_args_list), 3)
        for call in listing.call_args_list:
            self.assertIn('--filter', call.args)
            self.assertEqual(call.args[call.args.index('--filter') + 1], 'name=cxi-')


if __name__ == '__main__':
    unittest.main()
