"""Mocked current-PID RSS, child-aggregate swaps and finite observer custody.

No native runtime, Docker or actual measurement is invoked. Optional source path
admits the ignored exact Root-prefix + owned-suffix integration adapter.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
SOURCE = Path(os.environ.get('FS_BENCH_HOST_OBSERVER_SOURCE', BENCH / 'engine/receipts.py'))
spec = importlib.util.spec_from_file_location('host_process_receipts', SOURCE)
receipts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receipts)


def usage(swaps=0, user=.25, system=.125, reads=3, writes=5):
    return SimpleNamespace(ru_nswap=swaps, ru_utime=user, ru_stime=system,
                           ru_inblock=reads, ru_oublock=writes, ru_maxrss=999999999)


class Process:
    def __init__(self):
        self.pid, self.returncode, self.poll_calls = 1234, None, 0

    def poll(self):
        self.poll_calls += 1
        return self.returncode


class Thread:
    def __init__(self):
        self.started, self.joins, self.stuck = False, [], False

    def start(self):
        self.started = True

    def join(self, timeout):
        self.joins.append(timeout)

    def is_alive(self):
        return self.stuck


class HostProcessObserver(unittest.TestCase):
    def observer(self, home, process=None, limit=8 * 1024**3, ps=None, usages=None):
        process, thread = process or Process(), Thread()
        ps = ps or SimpleNamespace(returncode=0, stdout=' 2048\n', stderr='')
        state = dict(process=process, thread=thread)
        mocks = [patch('threading.Thread', return_value=thread),
                 patch.object(receipts.subprocess, 'run', return_value=ps),
                 patch('resource.getrusage', side_effect=usages or [usage(), usage(user=.75, system=.5, reads=7, writes=11)])]
        for mock in mocks:
            active = mock.start(); self.addCleanup(mock.stop)
            if mock is mocks[1]: state['ps'] = active
            if mock is mocks[2]: state['usage'] = active
        state['observer'] = receipts.HostProcessObserver(process, home, 'runtime', limit)
        return state

    def rows(self, home):
        return [json.loads(line) for line in (home / 'runtime.host-process.samples.jsonl').read_text().splitlines()]

    def completion(self, home):
        return json.loads((home / 'runtime.host-process.completion.json').read_text())

    def test_current_owned_pid_rss_exact_limit_and_children_deltas_are_separate(self):
        with tempfile.TemporaryDirectory(prefix='fsb-host-observer-') as temp:
            home = Path(temp); state = self.observer(home)
            observed, process = state['observer'], state['process']
            pending = observed.check()
            self.assertEqual(pending['swap_status'], 'UNAVAILABLE_UNTIL_KNOWN_CHILD_WAIT')
            self.assertEqual(pending['maximum_observed_rss_bytes'], 2048 * 1024)
            state['ps'].assert_called_once_with(['/bin/ps', '-o', 'rss=', '-p', '1234'],
                                                capture_output=True, text=True, timeout=.25, check=False)
            process.returncode = 0  # mocked known Popen wait result
            result = observed.finish()
            self.assertEqual(result['status'], 'PASS')
            self.assertEqual(result['rss_limit_bytes'], 8 * 1024**3)
            self.assertEqual(result['swap_status'], 'PASS_AGGREGATE_ZERO_BEFORE_AFTER')
            self.assertEqual(result['children_aggregate_delta'], {'ru_nswap': 0, 'user_cpu_ns': 500000000,
                'system_cpu_ns': 375000000, 'input_block_operations': 4, 'output_block_operations': 6})
            self.assertEqual(state['thread'].joins, [1])
            self.assertNotIn('ru_maxrss', json.dumps(result))
            self.assertIn('other waited commands', result['children_scope'])
            before = (home / 'runtime.host-process.completion.json').read_bytes()
            self.assertEqual(observed.finish(), result)
            self.assertEqual((home / 'runtime.host-process.completion.json').read_bytes(), before)

    def test_over_limit_rejects_without_kill_or_repeated_ps_and_retains_raw(self):
        with tempfile.TemporaryDirectory(prefix='fsb-host-observer-') as temp:
            home = Path(temp); state = self.observer(home, limit=1024)
            with self.assertRaisesRegex(RuntimeError, 'exceeds declared limit'): state['observer'].check()
            self.assertEqual(state['ps'].call_count, 1)
            self.assertFalse(state['thread'].started)
            state['process'].returncode = 0
            with self.assertRaises(RuntimeError): state['observer'].finish()
            result = self.completion(home)
            self.assertEqual(result['status'], 'FAIL')
            self.assertEqual(result['swap_status'], 'PASS_AGGREGATE_ZERO_BEFORE_AFTER')
            self.assertTrue(any(row['event'] == 'ps_observation' and row['stdout'] == ' 2048\n' for row in self.rows(home)))
            self.assertIn('no runtime/remote signals', result['remote_cancellation'])

    def test_ps_timeout_bad_body_missing_live_pid_and_nonzero_status_are_unknown(self):
        cases = [SimpleNamespace(returncode=0, stdout='', stderr='missing'),
                 SimpleNamespace(returncode=0, stdout='2048\n4096\n', stderr=''),
                 SimpleNamespace(returncode=1, stdout='2048', stderr='failed')]
        for index, output in enumerate(cases):
            with self.subTest(index=index), tempfile.TemporaryDirectory(prefix='fsb-host-observer-') as temp:
                state = self.observer(Path(temp), ps=output)
                with self.assertRaisesRegex(RuntimeError, 'unavailable'): state['observer'].check()
                self.assertEqual(state['ps'].call_count, 1)
        with tempfile.TemporaryDirectory(prefix='fsb-host-observer-') as temp:
            process = Process()
            with (patch.object(receipts.subprocess, 'run', side_effect=subprocess.TimeoutExpired('ps', .25, output=b'partial')) as ps,
                  patch('resource.getrusage', return_value=usage())):
                observed = receipts.HostProcessObserver(process, temp, 'runtime', 8 * 1024**3)
                with self.assertRaisesRegex(RuntimeError, 'TimeoutExpired'): observed.check()
                self.assertEqual(ps.call_count, 1)
                self.assertTrue(any('partial' in str(row) for row in self.rows(Path(temp))))

    def test_known_exit_ps_race_is_not_an_inferred_success_or_zero_rss(self):
        with tempfile.TemporaryDirectory(prefix='fsb-host-observer-') as temp:
            home = Path(temp); process = Process(); polls = iter([None, 0])
            def poll():
                result = next(polls)
                if result is not None: process.returncode = result
                return result
            process.poll = poll
            state = self.observer(home, process, ps=SimpleNamespace(returncode=1, stdout='', stderr='exited'))
            with self.assertRaisesRegex(RuntimeError, 'samples unavailable'): state['observer'].check()
            with self.assertRaises(RuntimeError): state['observer'].finish()
            self.assertTrue(self.completion(home)['known_child_wait'])
            self.assertIsNone(self.completion(home)['maximum_observed_rss_bytes'])
            self.assertTrue(any(row['event'] == 'known_child_wait' for row in self.rows(home)))

    def test_swap_only_footprint_has_no_rss_cap_ps_or_child_alive_swap_zero(self):
        with tempfile.TemporaryDirectory(prefix='fsb-host-observer-') as temp:
            home = Path(temp); state = self.observer(home, limit=None)
            self.assertEqual(state['ps'].call_count, 0)
            self.assertFalse(state['thread'].started)
            self.assertEqual(state['observer'].check()['rss_status'], 'NOT_APPLICABLE_NO_CAP')
            with self.assertRaisesRegex(RuntimeError, 'retained'): state['observer'].finish()
            result = self.completion(home)
            self.assertEqual(result['swap_status'], 'UNAVAILABLE')
            self.assertIsNone(result['children_after_known_wait'])
            self.assertIsNone(result['children_aggregate_delta'])
            self.assertIsNone(state['process'].returncode)
        with tempfile.TemporaryDirectory(prefix='fsb-host-observer-') as temp:
            state = self.observer(Path(temp), limit=None)
            state['process'].returncode = 0
            self.assertEqual(state['observer'].finish()['swap_status'], 'PASS_AGGREGATE_ZERO_BEFORE_AFTER')

    def test_nonzero_before_or_after_children_swap_is_retained_failure(self):
        for values in ([usage(swaps=1), usage(swaps=1)], [usage(), usage(swaps=1)]):
            with self.subTest(values=values), tempfile.TemporaryDirectory(prefix='fsb-host-observer-') as temp:
                state = self.observer(Path(temp), limit=None, usages=values)
                state['process'].returncode = 0
                with self.assertRaises(RuntimeError): state['observer'].finish()
                self.assertEqual(self.completion(Path(temp))['swap_status'], 'FAIL')

    def test_readonly_sampler_cancellation_and_join_failure_are_finite(self):
        with tempfile.TemporaryDirectory(prefix='fsb-host-observer-') as temp:
            state = self.observer(Path(temp)); observed = state['observer']
            observed._stop.set()
            observed._run()
            self.assertEqual(state['ps'].call_count, 1)
            state['thread'].stuck = True
            state['process'].returncode = 0
            with self.assertRaises(RuntimeError): observed.finish()
            self.assertEqual(state['thread'].joins, [1])
            self.assertEqual(self.completion(Path(temp))['swap_status'], 'UNAVAILABLE')
            self.assertIsNone(self.completion(Path(temp))['children_after_known_wait'])
            self.assertTrue(any('join unavailable' in failure for failure in self.completion(Path(temp))['failures']))

    def test_sample_gaps_and_sampler_error_are_retained_without_retry(self):
        with tempfile.TemporaryDirectory(prefix='fsb-host-observer-') as temp:
            home = Path(temp); state = self.observer(home)
            observed = state['observer']; observed._sample()
            samples = [row for row in self.rows(home) if row['event'] == 'rss_sample']
            self.assertEqual(len(samples), 2)
            self.assertTrue(all(row['sample_gap_ns'] >= 0 for row in samples))
            state['ps'].side_effect = RuntimeError('observer child admission failed')
            observed._sample()
            with self.assertRaisesRegex(RuntimeError, 'admission failed'): observed.check()
            observed._run()
            self.assertEqual(state['ps'].call_count, 3)

    def test_unknown_resource_and_thread_start_failures_never_credit_swap_zero(self):
        for snapshots in ([OSError('before unavailable'), usage()], [usage(), OSError('after unavailable')]):
            with self.subTest(snapshots=snapshots), tempfile.TemporaryDirectory(prefix='fsb-host-observer-') as temp:
                state = self.observer(Path(temp), limit=None, usages=snapshots)
                state['process'].returncode = 0
                with self.assertRaises(RuntimeError): state['observer'].finish()
                result = self.completion(Path(temp))
                self.assertEqual(result['swap_status'], 'UNAVAILABLE')
                self.assertIsNone(result['children_aggregate_delta'])
        with tempfile.TemporaryDirectory(prefix='fsb-host-observer-') as temp:
            process, thread = Process(), Thread()
            def refuse():
                raise RuntimeError('thread admission refused')
            thread.start = refuse
            with (patch('threading.Thread', return_value=thread),
                  patch.object(receipts.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='100', stderr='')),
                  patch('resource.getrusage', return_value=usage())):
                observed = receipts.HostProcessObserver(process, temp, 'runtime', 8 * 1024**3)
                with self.assertRaisesRegex(RuntimeError, 'thread admission refused'): observed.check()
                process.returncode = 0
                with self.assertRaises(RuntimeError): observed.finish()
                self.assertEqual(self.completion(Path(temp))['status'], 'FAIL')

    def test_invalid_pid_limit_interval_and_duplicate_output_are_refused(self):
        with tempfile.TemporaryDirectory(prefix='fsb-host-observer-') as temp:
            for limit, interval in ((True, .01), (0, .01), (-1, .01), (1024, float('nan')), (1024, 0)):
                with self.subTest(limit=limit, interval=interval), self.assertRaises(ValueError):
                    receipts.HostProcessObserver(Process(), temp, 'runtime', limit, interval)
            state = self.observer(Path(temp), limit=None)
            with self.assertRaises(FileExistsError): receipts.HostProcessObserver(Process(), temp, 'runtime', None)
            self.assertEqual(state['ps'].call_count, 0)


if __name__ == '__main__':
    unittest.main()
