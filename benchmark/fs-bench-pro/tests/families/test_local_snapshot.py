"""Original25k lifecycle, independent state equations and complete native qualification."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[2]
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from engine import fixtures, identity


class LocalSnapshot(unittest.TestCase):
    def test_original_membership_three_distinct_steps_and_limits(self):
        case, = json.loads((HERE/'families/local_snapshot/family.json').read_text())['cases']
        self.assertEqual(case['id'], 'local-snapshot-create-25000-onebyte-v1')
        self.assertEqual([s['run'].split()[-1] for s in case['steps']], ['0','1','2'])
        self.assertTrue(all(s['commit'] and s['expected_commit']=='Committed' for s in case['steps']))
        self.assertEqual(case['cache_class'],'C')
        self.assertEqual(case['budget'],dict(command_ms=15000,performance_hard_watchdog_ms=120000,operation_watchdog_ms=120000,verifier_ms=45000,verification_hard_watchdog_ms=59000))
        for name,digest in case['port_review']['files'].items():
            self.assertEqual(identity.sha256(ROOT/name),digest)
        for i, row in enumerate(case['history_schedule']['states']):
            self.assertEqual(row['manifest_sha256'],hashlib.sha256(fixtures.snapshot_manifest(i).encode()).hexdigest())

    def test_restored_state_equals_c1_and_c2_changes_exactly_97j(self):
        rows=[fixtures.snapshot_manifest(i).splitlines() for i in range(4)]
        self.assertEqual(len(rows[0]),2)
        self.assertEqual(len(rows[1]),25002)
        self.assertEqual(rows[1],rows[3])
        changed=[i for i in range(25000) if rows[1][i+2]!=rows[2][i+2]]
        self.assertEqual(changed,[97*j for j in range(256)])
        for ordinal in (0,1,97,194,12500,24998,24999):
            fields=rows[1][ordinal+2].split('\t')
            self.assertEqual(fields[:6],[f'f{ordinal:05}','file','1','644','1700000000','0'])
            self.assertEqual(fields[6],hashlib.sha256(bytes([ordinal%251])).hexdigest())
        with self.assertRaises(ValueError):fixtures.snapshot_manifest(4)

    @unittest.skipUnless(os.environ.get('LAYERFS_LOCAL_SNAPSHOT_BUILD'),'native qualification requires final seal')
    def test_unchanged_native_three_step_program_restores_bytes_and_inodes(self):
        build=identity.load_build(os.environ['LAYERFS_LOCAL_SNAPSHOT_BUILD'])
        writer=build['binaries']['workspace-writer']['path']
        workload=build['binaries']['workload-host']['path']
        case='local-snapshot-create-25000-onebyte-v1'
        with tempfile.TemporaryDirectory(prefix='fsb-native-local-snapshot-') as directory:
            root=Path(directory)/'root'
            subprocess.run([writer,'fixture',case,str(root)],check=True,capture_output=True,timeout=15)
            initial=None
            for step in range(3):
                subprocess.run([workload,'workspace-apply',case,'1',str(step),'performance'],cwd=root,check=True,capture_output=True,timeout=30)
                proof=subprocess.run([workload,'workspace-verify-tree',case,'1',str(step+1)],cwd=root,check=True,capture_output=True,text=True,timeout=30)
                self.assertIn('verification_status=pass',proof.stdout)
                observed={p.name:(p.stat().st_ino,p.read_bytes()) for p in root.iterdir()}
                if step==0:initial=observed
                elif step==1:
                    self.assertEqual({n:i for n,(i,_) in observed.items()},{n:i for n,(i,_) in initial.items()})
                    self.assertEqual(sum(observed[n][1]!=initial[n][1] for n in observed),256)
                else:self.assertEqual(observed,initial)
            target=root/'f00097'
            target.write_bytes(b'!')
            os.utime(target,ns=(fixtures.MTIME_NS,fixtures.MTIME_NS))
            bad=subprocess.run([workload,'workspace-verify-tree',case,'1','3'],cwd=root,capture_output=True,timeout=30)
            self.assertNotEqual(bad.returncode,0)
