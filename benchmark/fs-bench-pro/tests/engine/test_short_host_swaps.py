"""Mocked short-command aggregate swap admission; no native/Docker execution."""
import importlib.util
import json
import os
from pathlib import Path
import resource
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
SOURCE = Path(os.environ.get('FS_BENCH_SHORT_SWAP_SOURCE', BENCH / 'engine/receipts.py'))
spec = importlib.util.spec_from_file_location('short_swap_receipts', SOURCE)
receipts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receipts)


def usage(swaps=0):
    return SimpleNamespace(ru_nswap=swaps, ru_utime=.1, ru_stime=.2, ru_inblock=3, ru_oublock=4)


class Child:
    def __init__(self, code=0, waits=None):
        self.pid, self.returncode, self.code = 1234, None, code
        self.wait_results, self.wait_calls = list(waits or []), []

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        self.wait_calls.append(timeout)
        result = self.wait_results.pop(0) if self.wait_results else self.code
        if isinstance(result, BaseException):
            raise result
        self.returncode = result
        return result


class ShortHostSwaps(unittest.TestCase):
    def execute(self, home, child, snapshots, **options):
        def launch(argv, **kwargs):
            kwargs['stdout'].write(b'original native stdout\n')
            kwargs['stderr'].write(b'original native stderr\n')
            return child
        with (patch.object(receipts.subprocess, 'Popen', side_effect=launch) as popen,
              patch.object(receipts.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='2048\n', stderr='')) as ps,
              patch('resource.getrusage', side_effect=snapshots) as observed,
              patch.object(receipts.os, 'killpg') as kill):
            try:
                result = receipts.command(['native', '--profile', 'Disposable'], home, 'init', 120,
                    cwd=home, environment={'fixture': 'explicit'}, **options)
                error = None
            except BaseException as caught:
                result, error = None, caught
            return SimpleNamespace(result=result, error=error, popen=popen, ps=ps, usage=observed, kill=kill)

    def completion(self, home):
        return json.loads((home / 'init.completion.json').read_text())

    def test_default_preserves_streams_custody_command_identity_and_has_no_swap_probe(self):
        with tempfile.TemporaryDirectory(prefix='fsb-short-swap-') as temp:
            home = Path(temp); child = Child()
            outcome = self.execute(home, child, [AssertionError('default must not observe swaps')])
            self.assertIsNone(outcome.error)
            self.assertEqual(outcome.usage.call_count, 0)
            self.assertEqual(outcome.ps.call_count, 0)
            self.assertNotIn('host_swaps', outcome.result)
            self.assertEqual(child.wait_calls, [120])
            self.assertEqual((home / 'init.stdout').read_bytes(), b'original native stdout\n')
            self.assertEqual((home / 'init.stderr').read_bytes(), b'original native stderr\n')
            self.assertEqual(json.loads((home / 'init.host-custody.json').read_text())['host_pid'], child.pid)
            self.assertEqual(outcome.popen.call_args.args[0], ['native', '--profile', 'Disposable'])
            self.assertEqual(outcome.popen.call_args.kwargs['env'], {'fixture': 'explicit'})
            outcome.kill.assert_not_called()

    def test_zero_before_after_known_wait_is_expanded_aggregate_not_native_specific(self):
        with tempfile.TemporaryDirectory(prefix='fsb-short-swap-') as temp:
            home = Path(temp); outcome = self.execute(home, Child(), [usage(), usage()], host_swap_guard=True)
            self.assertIsNone(outcome.error)
            swaps = outcome.result['host_swaps']
            self.assertEqual(swaps['status'], 'PASS_ZERO_BEFORE_AFTER')
            self.assertTrue(swaps['known_child_wait'])
            self.assertEqual(swaps['before']['ru_nswap'], 0)
            self.assertEqual(swaps['after_known_wait']['ru_nswap'], 0)
            self.assertIn('all reaped children', swaps['scope'])
            self.assertIn('not native-specific', swaps['scope'])
            self.assertEqual(outcome.usage.call_args_list[0].args, (resource.RUSAGE_CHILDREN,))
            self.assertEqual(outcome.usage.call_count, 2)
            self.assertEqual(outcome.popen.call_count, 1)
            self.assertEqual(outcome.ps.call_count, 0)
            outcome.kill.assert_not_called()

    def test_init_rss_guard_and_swap_guard_preserve_existing_current_pid_rss(self):
        with tempfile.TemporaryDirectory(prefix='fsb-short-swap-') as temp:
            home = Path(temp); outcome = self.execute(home, Child(), [usage(), usage()],
                host_rss_limit_bytes=2 * 1024**3, host_swap_guard=True)
            self.assertIsNone(outcome.error)
            self.assertEqual(outcome.result['host_rss']['limit_bytes'], 2 * 1024**3)
            self.assertEqual(outcome.result['host_rss']['samples'][0]['rss_bytes'], 2048 * 1024)
            self.assertEqual(outcome.result['host_swaps']['status'], 'PASS_ZERO_BEFORE_AFTER')
            self.assertEqual(outcome.ps.call_count, 1)
            outcome.kill.assert_not_called()

    def test_nonzero_or_unknown_baseline_fails_before_launch_without_inferred_zero(self):
        for baseline in (usage(1), OSError('aggregate baseline unavailable')):
            with self.subTest(baseline=baseline), tempfile.TemporaryDirectory(prefix='fsb-short-swap-') as temp:
                home = Path(temp); outcome = self.execute(home, Child(), [baseline], host_swap_guard=True)
                self.assertIsNotNone(outcome.error)
                self.assertEqual(outcome.popen.call_count, 0)
                outcome.kill.assert_not_called()
                record = self.completion(home)
                self.assertEqual(record['status'], 'FAIL')
                self.assertEqual(record['host_swaps']['launch_status'], 'NOT_LAUNCHED')
                self.assertIsNone(record['host_swaps']['after_known_wait'])
                self.assertFalse(record['host_swaps']['known_child_wait'])
                self.assertFalse((home / 'init.host-custody.json').exists())
                if isinstance(baseline, OSError):
                    self.assertIsNone(record['host_swaps']['before'])
                    self.assertEqual(record['host_swaps']['status'], 'UNAVAILABLE')
                else:
                    self.assertEqual(record['host_swaps']['before']['ru_nswap'], 1)
                    self.assertEqual(record['host_swaps']['status'], 'FAIL')

    def test_nonzero_or_unknown_after_known_wait_fails_even_allow_failure(self):
        for after in (usage(1), OSError('aggregate result unavailable')):
            with self.subTest(after=after), tempfile.TemporaryDirectory(prefix='fsb-short-swap-') as temp:
                home = Path(temp); outcome = self.execute(home, Child(), [usage(), after], host_swap_guard=True, allow_failure=True)
                self.assertIsNotNone(outcome.error)
                record = self.completion(home)
                self.assertEqual(record['status'], 'FAIL')
                self.assertEqual(record['exit_code'], 0)
                self.assertTrue(record['host_swaps']['known_child_wait'])
                self.assertNotEqual(record['host_swaps']['status'], 'PASS_ZERO_BEFORE_AFTER')
                outcome.kill.assert_not_called()

    def test_original_timeout_and_existing_host_fence_are_not_replaced_by_swap_error(self):
        with tempfile.TemporaryDirectory(prefix='fsb-short-swap-') as temp:
            home = Path(temp); original = subprocess.TimeoutExpired(['native'], 120)
            child = Child(waits=[original, -9])
            outcome = self.execute(home, child, [usage(), OSError('after fence usage unavailable')], host_swap_guard=True)
            self.assertIs(outcome.error, original)
            self.assertEqual(child.wait_calls, [120, 1])
            self.assertEqual(outcome.kill.call_count, 1)  # existing command fence only
            record = self.completion(home)
            self.assertTrue(record['timeout'])
            self.assertEqual(record['original_failure_type'], 'TimeoutExpired')
            self.assertIn('after fence usage unavailable', record['independent_host_swap_failure'])
            self.assertTrue(record['host_swaps']['known_child_wait'])
            self.assertIsNone(record['host_swaps']['after_known_wait'])

    def test_unknown_host_fence_retains_unavailable_after_and_original_failure(self):
        with tempfile.TemporaryDirectory(prefix='fsb-short-swap-') as temp:
            home = Path(temp); original = subprocess.TimeoutExpired(['native'], 120)
            child = Child(waits=[original, subprocess.TimeoutExpired(['native'], 1)])
            outcome = self.execute(home, child, [usage()], host_swap_guard=True)
            self.assertIs(outcome.error, original)
            self.assertEqual(outcome.usage.call_count, 1)
            self.assertEqual(outcome.kill.call_count, 1)
            record = self.completion(home)
            self.assertIn('independent_host_fence_failure', record)
            self.assertFalse(record['host_swaps']['known_child_wait'])
            self.assertIsNone(record['host_swaps']['after_known_wait'])
            self.assertEqual(record['host_swaps']['status'], 'UNAVAILABLE')

    def test_nonzero_exit_allow_failure_default_and_guarded_preserve_original_outcome(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory(prefix='fsb-short-swap-') as temp:
                outcome = self.execute(Path(temp), Child(7), [usage(), usage()], allow_failure=True, host_swap_guard=enabled)
                self.assertIsNone(outcome.error)
                self.assertEqual(outcome.result['exit_code'], 7)
                self.assertEqual(outcome.result['status'], 'FAIL')
                self.assertEqual(outcome.usage.call_count, 2 if enabled else 0)
                outcome.kill.assert_not_called()


if __name__ == '__main__':
    unittest.main()
