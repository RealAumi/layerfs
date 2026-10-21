"""Original context choreography and authenticated event/receipt rejection."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import fixtures, workspace


def cases(family):
    return json.loads((BENCH / 'families' / family / 'family.json').read_text())['cases']


class ContextController(unittest.TestCase):
    def test_transcript_modes_bind_only_declared_payload_checkpoints(self):
        for family in ('branch_development', 'multi_workspace_development'):
            for case in cases(family):
                with self.subTest(case=case['id']):
                    plan = fixtures.context_plan(case)
                    checkpoints = {(item['role'], item['index']):
                                   f"checkpoint-{item['role']}-{item['index']}"
                                   for item in plan['checkpoints']}
                    prepared = {'context_checkpoints': [dict(role=role, index=index, manifest=path)
                                for (role, index), path in checkpoints.items()]}
                    branches = {}
                    expected_order = []
                    for role in plan['roles']:
                        records = []
                        for index in range(1, plan['local_commits'][role] + 1):
                            fields = dict(commit_id=f'commit-{role}-{index}', stack='stack',
                                          root=f'root-{role}-{index}', parent=f'parent-{role}-{index}',
                                          base_layer='base')
                            records.append(dict(index=index, commit={'fields': fields}))
                            expected_order.append((role, index))
                        branches[role] = dict(branch_id=f'branch-{role}', name=f'name-{role}',
                            stack='stack', base_layer='base', initial_parent='-', initial_root='initial',
                            final_head=records[-1]['commit']['fields']['commit_id'],
                            final_root=records[-1]['commit']['fields']['root'], commits=records)
                    for modes in (None, Path('declared-modes') if case.get('m1_schedule') else None):
                        transcript = workspace.context_transcript(case, prepared, {'branches': branches}, modes)
                        commits = [line.split('\t') for line in transcript.splitlines()
                                   if line.startswith('commit\t')]
                        self.assertEqual([(row[1], int(row[2])) for row in commits], expected_order)
                        selected = []
                        for row in commits:
                            pair = (row[1], int(row[2]))
                            if pair in checkpoints:
                                selected.append(pair)
                                self.assertEqual(row[8], checkpoints[pair])
                                self.assertEqual(row[9], '-' if modes is None else str(modes))
                            else:
                                self.assertEqual(row[8:], ['-', '-'])
                        self.assertEqual(set(selected), set(checkpoints))

    def test_every_original_role_stage_and_sdk_substitution(self):
        for family in ('branch_development', 'multi_workspace_development'):
            for case in cases(family):
                with self.subTest(case=case['id']):
                    plan = fixtures.context_plan(case)
                    prepared = {'prepared_context_runs': {role: {} for role in plan['roles']}}
                    for step in plan['sdk_steps']:
                        prepared['prepared_context_runs'][step['role']][str(step['index'])] = f"context/{step['role']}/steps/step-{step['index']}.sh"
                    bodies = workspace.context_bodies(case, prepared)
                    layout = workspace.context_layout(case)
                    self.assertEqual(sum(len(value) for value in bodies.values()), layout['total'])
                    for role, steps in bodies.items():
                        self.assertEqual(list(steps), [str(index) for index in range(1, plan['local_commits'][role] + 1)])
                        for local, body in steps.items():
                            expected = prepared['prepared_context_runs'][role].get(local, plan['original_context_runs'][role][local])
                            self.assertEqual(body, '/bin/bash /code/' + expected)
                    prepared['prepared_context_runs'][plan['roles'][0]]['999'] = 'invented.sh'
                    with self.assertRaises(ValueError):
                        workspace.context_bodies(case, prepared)

    def test_original_fork_topology_and_complete_discard_segments(self):
        branch = workspace.context_layout(cases('branch_development')[-1])
        self.assertEqual([(row['role'], row['source_role'], row['source_local']) for row in branch['branches']],
                         [('trunk', None, 0), ('a', 'trunk', 5), ('b', 'trunk', 5), ('c', 'a', 5)])
        for case in cases('multi_workspace_development'):
            layout = workspace.context_layout(case)
            count = case['topology_schedule']['per_worker_commits']
            self.assertEqual(layout['segments'], [[1, count]] if len(layout['roles']) == 4 else [[1, count // 2], [count // 2 + 1, count]])
            if len(layout['roles']) == 2:
                self.assertEqual(case['topology_schedule']['discard_reopen']['peer_state'], 'already committed; no original dirty-stage6 hold')
            changed = copy.deepcopy(case)
            changed['topology_schedule']['segment_ranges'][0][1] -= 1
            with self.assertRaises(ValueError):
                workspace.context_layout(changed)

    def test_context_protocol_one_write_and_no_failed_resend(self):
        class Runtime:
            def __init__(self):
                self.process = type('Process', (), {'stdin': io.BytesIO()})()
                self.expected = []
            def event(self, expected, deadline):
                self.expected.append(expected)
                return {'event': expected}
        runtime = Runtime()
        workspace.context_send(runtime, 'round', 'group', '/safe/body', deadline=time.monotonic() + 1)
        self.assertEqual(runtime.process.stdin.getvalue(), b'round\tgroup\t/safe/body\n')
        self.assertEqual(runtime.expected, ['round_finished'])
        with self.assertRaises(ValueError):
            workspace.context_send(runtime, 'fork', 'bad\trole', '/safe/body', deadline=time.monotonic() + 1)
        self.assertEqual(runtime.process.stdin.getvalue(), b'round\tgroup\t/safe/body\n')
        with self.assertRaises(TimeoutError):
            workspace.context_send(runtime, 'fork', 'role', '/safe/body', deadline=time.monotonic() - 1)
        self.assertEqual(len(runtime.expected), 1)
        class Short:
            calls = 0
            def write(self, body):
                self.calls += 1
                return len(body) - 1
        runtime.process.stdin = Short()
        with self.assertRaises(workspace.cell_runner.OriginalFailure):
            workspace.context_send(runtime, 'fork', 'role', '/safe/body', deadline=time.monotonic() + 1)
        self.assertEqual(runtime.process.stdin.calls, 1)

    def test_overlap_uses_complete_different_worker_spans_and_original_coverage(self):
        def commit(role, start, end):
            return {'role': role, 'commit': {'span': {'clock_id': 'monotonic', 'start_ns': start,
                'end_ns': end, 'duration_ns': end - start}}}
        observed = workspace.context_overlap([commit('a', 0, 10), commit('a', 2, 8), commit('b', 7, 12), commit('b', 12, 14)])
        self.assertEqual((observed['observed_overlap_ns'], observed['overlap_rounds']), (3, 2))
        self.assertEqual(workspace.context_overlap([commit('a', 0, 2), commit('b', 2, 3)])['overlap_rounds'], 0)
        damaged = commit('a', 0, 2)
        damaged['commit']['span']['duration_ns'] = 1
        with self.assertRaises(ValueError):
            workspace.context_overlap([damaged])

    def test_actual_context_modes_remain_role_separate(self):
        text = workspace.context_modes_text({'trunk': {'data/d000': 0o750}, 'a': {'data/d000': 0o755}}, ['trunk', 'a'])
        self.assertEqual(text, 'original-context-created-modes-v1\nrole\tpath\tmode\ntrunk\tdata/d000\t750\na\tdata/d000\t755\n')
        for maps in ({'trunk': {}}, {'trunk': {'../escape': 0o750}, 'a': {}}):
            with self.assertRaises(ValueError):
                workspace.context_modes_text(maps, ['trunk', 'a'])

    def test_every_original_deadline_remains_declared(self):
        for family in ('branch_development', 'multi_workspace_development'):
            for case in cases(family):
                performance = workspace.context_deadlines(case, 100, phase='performance')
                self.assertEqual(performance, {'work': 157, 'cleanup': 160})
                proof = workspace.context_deadlines(case, 100)
                self.assertEqual(proof['cleanup'], 100 + case['budget']['verifier_ms'] / 1000)
                self.assertEqual(proof['publication'], 100 + case['budget']['verification_hard_watchdog_ms'] / 1000)
                self.assertEqual(proof['cleanup'] - proof['work'], 3)

    def test_native_bridge_history_paginates_to_exact_eof_with_authenticated_cursor(self):
        records = [{'commit_id': f'id-{index}', 'stack': 'stack', 'root': f'root-{index}',
                    'parent': f'id-{index - 1}' if index else '-', 'base_layer': 'base'}
                   for index in range(40)]
        branch = {'final_head': 'id-39', 'commits': [{'commit': {'fields': record}} for record in records],
                  'source_role': None}
        class Runtime:
            rows = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cursor = root / 'cursor'
            cursor.write_bytes(b'original opaque cursor')
            for label, wrong_hash in [('good', False), ('tampered', True)]:
                folder = root / label
                folder.mkdir()
                runtime = Runtime()
                runtime.rows = []
                requests = []
                def send(owner, operation, role, path, *, deadline):
                    requests.append(Path(path).read_text())
                    page = list(reversed(records))[:32] if len(requests) == 1 else list(reversed(records))[32:]
                    owner.rows.extend({'event': 'history_record', 'fields': row} for row in page)
                    fields = {'records': len(page), 'cursor_path': '-'}
                    if len(requests) == 1:
                        fields.update(cursor_path=str(cursor), cursor_bytes=cursor.stat().st_size,
                                      cursor_sha256='bad' if wrong_hash else hashlib.sha256(cursor.read_bytes()).hexdigest())
                    return {'event': 'history_finished', 'fields': fields}
                with patch.object(workspace, 'context_send', side_effect=send):
                    if wrong_hash:
                        with self.assertRaises(ValueError):
                            workspace.context_history(runtime, 'role', branch, {}, folder, time.monotonic() + 1)
                        self.assertEqual(len(requests), 1)
                    else:
                        result = workspace.context_history(runtime, 'role', branch, {}, folder, time.monotonic() + 1)
                        self.assertEqual(result['records'], list(reversed(records)))
                        self.assertEqual(len(result['pages']), 2)
                        self.assertEqual(requests, ['id-39\t-\t32\n', f"id-39\t{cursor.read_bytes().hex()}\t32\n"])


class NativeDiscard(unittest.TestCase):
    def test_frozen_two_worker_witness_is_sealed_once_and_other_topologies_refuse(self):
        binary = os.environ['FSB_CONTEXT_NATIVE']
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for number, case in enumerate((cases('multi_workspace_development')[0], cases('multi_workspace_development')[2])):
                out = root / str(number)
                done = subprocess.run([binary, 'prepare-context-discard', case['id'], str(out)], capture_output=True, text=True, timeout=10)
                self.assertEqual(done.returncode, 0, done.stderr)
                record = json.loads(done.stdout)
                body = (out / 'witness.tsv').read_text()
                lines = body.splitlines()
                self.assertEqual(lines[0], 'original-context-discard-witness-v1')
                identifier, role, path, hex_ = lines[1].split('\t')
                self.assertEqual((identifier, role, len(hex_)), (case['id'], '0', 512))
                # Frozen v016_common.rs: pool base ceil((initial files-1120)/100),
                # then refresh-cohort1's first member is local slot64.
                self.assertEqual(path, 'd039/f00064' if number == 0 else 'd289/f00064')
                payload = bytes.fromhex(hex_)
                self.assertEqual(record, {'case': case['id'], 'role': '0', 'path': path, 'bytes': 256,
                    'payload_sha256': hashlib.sha256(payload).hexdigest(), 'descriptor_sha256': hashlib.sha256(body.encode()).hexdigest()})
                refused = subprocess.run([binary, 'prepare-context-discard', case['id'], str(out)], capture_output=True, timeout=10)
                self.assertNotEqual(refused.returncode, 0)
                self.assertEqual((out / 'witness.tsv').read_text(), body)
            for case in (cases('multi_workspace_development')[-1], cases('branch_development')[0]):
                out = root / ('refuse-' + case['id'])
                done = subprocess.run([binary, 'prepare-context-discard', case['id'], str(out)], capture_output=True, timeout=10)
                self.assertNotEqual(done.returncode, 0)
                self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
