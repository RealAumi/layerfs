"""A parity build is supplied explicitly; old argument-less calls remain valid."""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
spec = importlib.util.spec_from_file_location('fsb_parity_cli', BENCH / 'bench.py')
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
from engine import fixtures, identity, project


class ParityBuildCli(unittest.TestCase):
    def test_explicit_sealed_build_is_forwarded_and_legacy_call_is_unchanged(self):
        for extra in ([], ['--build', '/sealed/build']):
            family = 'branch_development' if extra else 'file_size_transition'
            argv = ['parity', family, '--prepared', '/closed/prepared', '--out', '/fresh/parity', *extra]
            with self.subTest(extra=extra), patch.object(project, 'parity_workspace', return_value={'family': family, 'status': 'PASS', 'cases': []}) as parity, contextlib.redirect_stdout(io.StringIO()):
                bench.main(argv)
            positional = parity.call_args.args
            self.assertEqual(positional[0]['family'], family)
            self.assertEqual(positional[1:], (Path('/closed/prepared'), Path('/fresh/parity')))
            self.assertEqual(parity.call_args.kwargs, {'build_folder': Path('/sealed/build')} if extra else {})

    def test_explicit_historical_reuse_reaches_setup_adapter_without_new_producer(self):
        with patch.object(fixtures, 'prepare_historical_workspace', return_value={'status':'PASS','master_volume':'mock','fixture':{}}) as reuse, \
             patch.object(fixtures, 'prepare') as fresh, contextlib.redirect_stdout(io.StringIO()):
            output=identity.ROOT/'benchmark-results/fs-bench-pro/mock-cli-route'
            bench.main(['prepare','v016-access-boundary-after-v1','--build','/sealed/build','--reuse-producer','/closed/first-access','--out',str(output)])
        fresh.assert_not_called()
        self.assertEqual(reuse.call_args.args[1]['id'],'v016-access-boundary-after-v1')
        self.assertEqual(reuse.call_args.kwargs,{'closed_producer_folder':Path('/closed/first-access')})



if __name__ == '__main__':
    unittest.main()
