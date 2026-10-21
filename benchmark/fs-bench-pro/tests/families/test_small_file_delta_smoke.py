"""Original thirty whole-file imports and complete independent 31-state oracles."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
HERE = ROOT / 'benchmark/fs-bench-pro'
sys.path.insert(0, str(HERE))
from engine import fixtures, identity, workspace


def original():
    spec = importlib.util.spec_from_file_location('original_small_delta', ROOT / 'benchmark/fs-bench-pro/shared/small_file_delta_fixture.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FrozenSmallDelta(unittest.TestCase):
    def test_every_original_state_operation_metadata_budget_and_source_pin(self):
        module = original()
        module.self_check()
        family = json.loads((HERE / 'families/small_file_delta_smoke/family.json').read_text())
        case, = family['cases']
        states = list(module.states())
        self.assertEqual(len(states), 31)
        self.assertEqual(case['id'], module.CASE)
        self.assertEqual(case['fixture']['sizes'], list(module.SIZES))
        self.assertEqual(case['fixture']['bytes'], 245760)
        self.assertEqual((case['fixture']['directory_mode'], case['fixture']['file_mode'], case['fixture']['mtime_seconds']), (0o755, 0o644, 1000000000))
        self.assertEqual(case['budget'], dict(command_ms=600000, verifier_ms=600000, operation_watchdog_ms=30000, verification_hard_watchdog_ms=600000))
        self.assertEqual(case['cache_class'], 'C')
        self.assertEqual(case['expected_commit'], 'Committed')
        self.assertEqual(case['history_schedule']['state_count'], len(states))
        self.assertEqual(len(case['steps']), 30)
        for step, files in enumerate(states):
            seal = case['history_schedule']['states'][step]
            self.assertEqual(seal['index'], step)
            self.assertEqual(seal['logical_bytes'], sum(map(len, files.values())))
            self.assertEqual(seal['file_sha256'], {name: hashlib.sha256(data).hexdigest() for name, data in files.items()})
            self.assertEqual(seal['original_oracle_sha256'], hashlib.sha256((json.dumps(module.oracle(files), sort_keys=True)+'\n').encode()).hexdigest())
            if step:
                changed = [name for name in files if files[name] != states[step-1][name]]
                self.assertEqual(changed, [case['steps'][step-1]['changed_path']])
                self.assertEqual(case['steps'][step-1]['run'], f'workload.sh apply {module.CASE} {step}')
                self.assertTrue(case['steps'][step-1]['commit'])
        self.assertEqual(sum(map(lambda seal: seal['logical_bytes'], case['history_schedule']['states'])), 7624960)
        for path, digest in case['port_review']['files'].items():
            self.assertEqual(identity.sha256(ROOT/path), digest)
            archived = subprocess.check_output(['git','show','reference-v0.1.6-final:'+path], cwd=ROOT)
            self.assertEqual(hashlib.sha256(archived).hexdigest(), digest)
        self.assertEqual(case['port_review']['source_commit'], 'd296981ace76fe751bebf00dee52818fe18a3eef')
        self.assertEqual(case['port_review']['source_tag_object'], 'ae3310fada4a1fe35cb99ab02270b7538a0d03f7')
        shell = (HERE/'families/small_file_delta_smoke/workload.sh').read_text()
        self.assertIn('storage-smoke-import', shell)
        self.assertNotIn('pwrite', shell)
        self.assertIn('verify-manifest', shell)

    def test_original_resource_guards_reject_oom_swap_disk_and_missing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = {'cgroup': {'oom':0,'oom_kill':0,'swap_current':0}, 'spool_allocated_bytes':0, 'staging_allocated_bytes':0,
                      'store_logical_bytes':0,'store_allocated_bytes':0}
            def observed(value):
                path = root/'observed'
                path.write_text(json.dumps(value))
                return {'stdout': str(path)}
            runtime = type('Runtime', (), {'container':'own-container'})()
            with patch.object(workspace.receipts,'command',return_value=observed(result)):
                before = workspace.history_resource_guard(runtime, {'socket':'/socket'}, root, 'before')
            for key, value in [('swap_current',1), ('oom',1), ('oom_kill',1)]:
                bad = {**result,'cgroup':{**result['cgroup'],key:value}}
                with patch.object(workspace.receipts,'command',return_value=observed(bad)), self.assertRaisesRegex(RuntimeError,'OOM/swap'):
                    workspace.history_resource_guard(runtime, {'socket':'/socket'}, root, key, before)
            bad={**result,'cgroup': {'oom':0,'oom_kill':0}}
            with patch.object(workspace.receipts,'command',return_value=observed(bad)), self.assertRaisesRegex(ValueError,'observation unavailable'):
                workspace.history_resource_guard(runtime, {'socket':'/socket'}, root, 'missing', before)
            for key in ('spool_allocated_bytes','store_logical_bytes','store_allocated_bytes'):
                with patch.object(workspace.receipts,'command',return_value=observed({**result,key:16*1024**3+1})), self.assertRaisesRegex(RuntimeError,'budget'):
                    workspace.history_resource_guard(runtime, {'socket':'/socket'}, root, key, before)
            with patch.object(workspace.shutil if hasattr(workspace,'shutil') else shutil, 'disk_usage', return_value=type('Disk',(),{'free':50*1024**3-1})()), self.assertRaisesRegex(RuntimeError,'free disk reserve'):
                workspace.history_resource_guard(runtime, {'socket':'/socket'}, root, 'low-free', before)

    def test_exact_container_readback_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            path=root/'inspect.json'
            path.write_text(json.dumps({'NanoCpus':2_000_000_000,'Memory':2_147_483_648,'MemorySwap':2_147_483_648,'PidsLimit':256}))
            runtime=type('Runtime',(),{'container':'own-container'})()
            with patch.object(workspace.receipts,'command',return_value={'stdout':str(path)}) as command:
                value=workspace.history_container_profile(runtime,{'socket':'/socket'},root)
                self.assertEqual(value['PidsLimit'],256)
                self.assertEqual(command.call_count,2)
            path.write_text(json.dumps({**value,'MemorySwap':-1}))
            with patch.object(workspace.receipts,'command',return_value={'stdout':str(path)}), self.assertRaisesRegex(ValueError,'profile differs'):
                workspace.history_container_profile(runtime,{'socket':'/socket'},root)

    def test_controller_rejects_full_only_or_unknown_mechanism_after_complete_bytes(self):
        roots=[{'event':'history_payload_encoding','fields':{'payload_objects':10,'payload_dependency_records':0}} for _ in range(31)]
        zero=workspace.qualify_history_mechanism(roots)
        self.assertEqual(zero['semantic_proof_status'],'PASS')
        self.assertEqual(zero['status'],'FAIL')
        self.assertIn('all selected payload records FULL',zero['reason'])
        self.assertEqual(zero['payload_dependency_record_observations'],0)
        # A metadata/directory dependency count cannot substitute for payload evidence.
        unknown=[*roots[:15],{'fields':{'payload_objects':10,'metadata_chain_edges':1}},*roots[16:]]
        self.assertEqual(workspace.qualify_history_mechanism(unknown)['status'],'FAIL')
        self.assertEqual(workspace.qualify_history_mechanism(roots[:30])['status'],'FAIL')
        one=[*roots[:15],{'fields':{'payload_objects':10,'payload_dependency_records':1}},*roots[16:]]
        self.assertEqual(workspace.qualify_history_mechanism(one)['status'],'PASS')
        for value in [True,-1,'1',None]:
            bad=[{'fields':{'payload_objects':10,'payload_dependency_records':value}},*roots[1:]]
            self.assertEqual(workspace.qualify_history_mechanism(bad)['status'],'FAIL')

    def test_resource_observer_wall_is_excluded_even_on_failure_without_extending_stop(self):
        for failure in [False,True]:
            clock=workspace.cell_runner.PerformanceClock()
            clock.begin(100)
            row={}
            def observe():
                if failure:raise ValueError('original resource observation failed')
                return 'observed'
            with patch.object(workspace.time,'monotonic_ns',side_effect=[200,700]):
                if failure:
                    with self.assertRaisesRegex(ValueError,'original resource'):
                        workspace.history_observer(clock,row,'state1',observe)
                else:
                    self.assertEqual(workspace.history_observer(clock,row,'state1',observe),'observed')
            clock.finish(1000)
            self.assertEqual(clock.observe(1000)['performance_ns'],400)
            self.assertEqual(row['observer_intervals'][0]['complete_wall_ns'],500)
            with patch.object(workspace.time,'monotonic',return_value=600):
                with self.assertRaisesRegex(TimeoutError,'group watchdog expired'):
                    workspace.operation_deadline(600,30)

    @unittest.skipUnless(os.environ.get('LAYERFS_SMALL_DELTA_BUILD'), 'native qualification requires final sealed binaries')
    def test_unchanged_original_importer_all31_native_states_and_corruption(self):
        build=identity.load_build(os.environ['LAYERFS_SMALL_DELTA_BUILD'])
        case=json.loads((HERE/'families/small_file_delta_smoke/family.json').read_text())['cases'][0]
        with tempfile.TemporaryDirectory(prefix='small-delta-native-',dir=ROOT/'core/target') as temporary:
            root=Path(temporary)
            _,_,proofs,states,built=fixtures.prepare_ordered_fixture(case,root,build)
            self.assertEqual(len(proofs),31)
            source=root/'source'
            wrapper=root/'import.rs'
            wrapper.write_text('#[allow(dead_code)]\n#[path = '+json.dumps(str(ROOT/'benchmark/fs-bench-pro/workload/main.rs'))+']\nmod reference;\nuse reference::{hex,Result,Sha256};\n#[allow(dead_code)]\n#[path = '+json.dumps(str(ROOT/'benchmark/fs-bench-pro/workload/storage_smoke.rs'))+']\nmod original_importer;\nfn main() { let a:Vec<_>=std::env::args().collect(); original_importer::import(std::path::Path::new(&a[1]),std::path::Path::new(&a[2])).unwrap(); }\n')
            binary=root/'import'
            compiled=subprocess.run(['rustup','run','1.85.1','rustc','--edition=2021',*identity.ARM64_FLAGS,str(wrapper),'-o',str(binary)],cwd=ROOT,capture_output=True,text=True,timeout=60)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            initial_inodes={path.name:path.stat().st_ino for path in source.iterdir()}
            for index in range(1,31):
                saved=subprocess.run([str(binary),str(Path(built['input'])/f'step-{index}'),str(source)],capture_output=True,text=True,timeout=10)
                self.assertEqual(saved.returncode,0,saved.stderr)
                checked=subprocess.run([build['binaries']['edit-host']['path'],'verify-manifest',states[index]['manifest']],cwd=source,capture_output=True,text=True,timeout=10)
                self.assertEqual(checked.returncode,0,checked.stderr)
                self.assertEqual(initial_inodes,{path.name:path.stat().st_ino for path in source.iterdir()})
            target=source/'source09.ts'
            with target.open('r+b') as stream:stream.write(b'corrupted bytes')
            os.utime(target,ns=(1000000000000000000,)*2)
            refused=subprocess.run([build['binaries']['edit-host']['path'],'verify-manifest',states[30]['manifest']],cwd=source,capture_output=True,text=True,timeout=10)
            self.assertNotEqual(refused.returncode,0)
            self.assertIn('native persistence digest mismatch: source09.ts',refused.stderr)

if __name__=='__main__':
    unittest.main()
