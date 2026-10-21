"""Finalization failures keep exact owned sample resources until known return."""
import json
from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import workspace, receipts


class ResourceRetention(unittest.TestCase):
    def test_close_failure_after_all_proofs_keeps_container_and_volume(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); output = root / 'case'; calls = []
            stdout = root / 'native.stdout'; stdout.write_text('verification_status=pass\n')
            target = 'c'*64
            class FailingClose:
                def close(self):
                    raise OSError('original output close failed')
            class Runtime:
                container = 'a'*64
                daemon_instance = scope = 'd'*64
                selector = FailingClose()
                raw = stderr = None
                process = SimpleNamespace(stdin=None, stdout=None, wait=lambda **kw: 0)
                rows = []
                def event(self, name, deadline):
                    return None
                def send(self, operation, *args, **kw):
                    fields = {'state':'Gone','stdout':str(stdout),'commit_kind':'Committed','root':target}
                    value = {'event':'workspace_status' if operation=='snapshot' else operation,
                             'fields':fields,'span':{'duration_ns':1},'sequence':len(self.rows)}
                    self.rows.append(value); return value
                def retain(self, error):
                    return {'state':'KNOWN_STOP'}
            runtime = Runtime()
            current = {'source_commit':'e'*40,'product_tree':'f'*40}
            build = {'socket':'/socket','binaries':{name:{'path':'/'+name,'sha256':name} for name in ('runtime','daemon')}}
            prepared = {'fixture':{'fixture_sha256':'fixture'},'helpers':{'files':{}},
                        'provision':{'manifest':'/manifest'},'source_uid':1,'source_gid':1}
            case = {'id':'tiny-file-churn-1','v016_case':'tiny-file-churn-1','steps':[{'run':'workload.sh apply tiny-file-churn-1','commit':True}],
                    'expected_commit':'Committed','fixture':{'recipe':'recipe'},'oracle':{'scope':'full','omissions':'none'},
                    'budget':{'command_ms':15000,'verifier_ms':45000,'verification_hard_watchdog_ms':59000}}
            def command(argv, folder, label, seconds, **kw):
                calls.append(argv)
                if label=='independent-graph':
                    (output/'graph.events.jsonl').write_text(json.dumps({'event':'workspace_verified','fields':{'root':target}})+'\n'+json.dumps({'event':'finished'})+'\n')
                result = root/(label+'.stdout'); result.write_text('false\n')
                return {'status':'PASS','stdout':str(result)}
            def observations(runtime, row, *args):
                row['cache']['status']='INELIGIBLE'
            with ExitStack() as stack:
                for module,name,options in (
                    (workspace.identity,'ROOT',{'new':root}),
                    (workspace.identity,'source_identity',{'return_value':current}),
                    (workspace.identity,'load_build',{'return_value':build}),
                    (workspace.fixtures,'load',{'return_value':prepared}),
                    (workspace.fixtures,'clone',{'return_value':{'volume':'layerfs-fsb-sample-'+'b'*16}}),
                    (workspace.fixtures,'stage',{'return_value':{}}),
                    (workspace.cell_runner,'EventProcess',{'return_value':runtime}),
                    (workspace,'terminal_cache_observation',{'return_value':([],{})}),
                    (workspace,'collect_family_observations',{'side_effect':observations}),
                    (receipts,'command',{'side_effect':command}),
                ):stack.enter_context(patch.object(module,name,**options))
                row=workspace.one_family_case('tiny_file_churn',case,'prepared','build',output)
                self.assertEqual(row['status'],'FAIL')
                self.assertEqual(row['custody'],'KNOWN_STOP')
                self.assertEqual(row['proof_status'],'PASS')
                if hasattr(workspace, 'dispose_family_resources'):
                    self.assertIsNone(workspace.dispose_family_resources(output,row))
            self.assertFalse(any('rm' in argv for argv in calls),calls)
            self.assertIn('retained',row['resource_disposition'])

    def receipt(self, root, *, guarded=False, additional=None):
        folder=root/'case';folder.mkdir(); build=root/'build';build.mkdir()
        (build/'build.json').write_text(json.dumps({'socket':'/socket'}))
        row={'family':'git_tool_workflow' if guarded else 'tiny_file_churn','case':'case',
             'source_commit':'c'*40,'product_tree':'d'*40,'image':'image',
             'build':str(build),'container':'a'*64,'clone':{'volume':'layerfs-fsb-sample-'+'b'*16},
             'status':'INELIGIBLE','functional_status':'PASS','proof_status':'PASS',
             'custody':'KNOWN_STOP','cleanup':'Gone','resource_removal_pending':True}
        if additional is not None:
            row['additional_containers']=additional
        if guarded:
            with patch.object(receipts.time,'monotonic',return_value=1.):
                row.update(receipts.finalize_guarded(folder,row,10.))
        else:
            receipts.write_new(folder/'receipt.json',row);receipts.manifest(folder)
        return folder,row

    def test_missing_outer_ack_and_failed_return_never_attempt_deletion(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder,row=self.receipt(Path(temporary),guarded=True)
            with patch.object(receipts,'command',side_effect=AssertionError('must keep resources')):
                self.assertIsNone(workspace.dispose_family_resources(folder,row))
                failed={**row,'status':'FAIL'}
                self.assertIsNone(workspace.dispose_family_resources(folder,failed))
            self.assertFalse((folder/'resource-removal').exists())

    def test_partial_removal_custody_is_bound_without_rewriting_original(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);folder,row=self.receipt(root,guarded=True)
            with patch.object(receipts.time,'monotonic',return_value=2.):
                receipts.acknowledge_guarded(folder,row)
            original=(folder/'receipt.json').read_bytes();manifest=(folder/'manifest.json').read_bytes();calls=[]
            def command(argv,output,label,seconds):
                calls.append(argv)
                if label=='volume':raise TimeoutError('volume removal acknowledgement lost')
                stdout=output/(label+'.stdout');stdout.write_text('false\n')
                return {'stdout':str(stdout),'status':'PASS'}
            with patch.object(receipts,'command',side_effect=command):
                record=workspace.dispose_family_resources(folder,row)
            self.assertEqual(len(calls),3)
            self.assertEqual(record['container_custody'],'REMOVED')
            self.assertEqual(record['volume_custody'],'REMOVAL_ATTEMPT_UNCERTAIN')
            self.assertEqual(record['status'],'FAIL')
            self.assertEqual((folder/'receipt.json').read_bytes(),original)
            self.assertEqual((folder/'manifest.json').read_bytes(),manifest)
            loaded=receipts.resource_disposition(folder,json.loads(original))
            self.assertEqual(loaded['status'],'INELIGIBLE')
            self.assertEqual(loaded['administrative_removal_status'],'FAIL')
            self.assertIn('UNCERTAIN',loaded['resource_disposition'])
            record['volume']='layerfs-fsb-sample-wrong'
            original_row=json.loads(original)
            # An independent forged copy cannot authenticate the original resource.
            with patch.object(receipts,'verify_manifest'),patch.object(receipts.json,'loads',side_effect=[record,original_row]):
                with self.assertRaisesRegex(ValueError,'binding differs'):
                    receipts.resource_disposition(folder,original_row)

    def remove(self, folder, row, *, fail_label=None):
        calls=[]
        def command(argv, output, label, seconds):
            self.assertLessEqual(seconds,15)
            calls.append((argv,label))
            if label==fail_label:
                raise TimeoutError('selected removal acknowledgement lost')
            stdout=output/(label+'.stdout');stdout.write_text('false\n')
            return {'stdout':str(stdout),'status':'PASS'}
        with patch.object(receipts,'command',side_effect=command):
            record=workspace.dispose_family_resources(folder,row)
        return record,calls

    def test_additional_owned_ids_remove_once_and_keep_exact_original_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            extras=['9'*64,'8'*64]
            folder,row=self.receipt(Path(temporary),guarded=True,additional=extras)
            with patch.object(receipts.time,'monotonic',return_value=2.):
                receipts.acknowledge_guarded(folder,row)
            original=(folder/'receipt.json').read_bytes();manifest=(folder/'manifest.json').read_bytes()
            record,calls=self.remove(folder,row)
            self.assertEqual(len(calls),7)
            self.assertEqual([argv[-1] for argv,label in calls if 'container' in label],['a'*64,*extras])
            self.assertEqual(record['identity']['additional_containers'],extras)
            self.assertEqual(record['additional_container_custody'],{value:'REMOVED' for value in extras})
            self.assertEqual(record['status'],'PASS')
            self.assertEqual((folder/'receipt.json').read_bytes(),original)
            self.assertEqual((folder/'manifest.json').read_bytes(),manifest)
            loaded=receipts.resource_disposition(folder,json.loads(original))
            self.assertEqual(loaded['status'],'INELIGIBLE')
            self.assertEqual(loaded['administrative_removal_status'],'PASS')

    def test_additional_partial_deletion_keeps_exact_remaining_custody_without_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            extras=['9'*64,'8'*64,'7'*64]
            folder,row=self.receipt(Path(temporary),additional=extras)
            original=(folder/'receipt.json').read_bytes()
            record,calls=self.remove(folder,row,fail_label='additional-2-container')
            self.assertEqual(len(calls),6)
            self.assertEqual(record['container_custody'],'REMOVED')
            self.assertEqual(record['additional_container_custody'],{
                extras[0]:'REMOVED',extras[1]:'REMOVAL_ATTEMPT_UNCERTAIN',extras[2]:'KNOWN_STOP_RETAINED'})
            self.assertEqual(record['volume_custody'],'RETAINED')
            self.assertFalse(any(label=='volume' or label.startswith('additional-3') for _,label in calls))
            loaded=receipts.resource_disposition(folder,json.loads(original))
            self.assertEqual(loaded['administrative_removal_status'],'FAIL')
            self.assertEqual(loaded['status'],'INELIGIBLE')
            self.assertEqual((folder/'receipt.json').read_bytes(),original)

    def test_additional_malformed_or_unbound_ids_refuse_before_any_deletion(self):
        invalids=[['a'*64],['9'*64,'9'*64],['F'*64],[False],[[]],{'9'*64:'owned'}]
        for invalid in invalids:
            with self.subTest(invalid=invalid),tempfile.TemporaryDirectory() as temporary:
                folder,row=self.receipt(Path(temporary),additional=invalid)
                with patch.object(receipts,'command',side_effect=AssertionError('no deletion')):
                    with self.assertRaisesRegex(ValueError,'canonical additional'):
                        workspace.dispose_family_resources(folder,row)
                self.assertFalse((folder/'resource-removal').exists())
        with tempfile.TemporaryDirectory() as temporary:
            folder,row=self.receipt(Path(temporary),additional=['9'*64])
            row['additional_containers']=['8'*64]
            with patch.object(receipts,'command',side_effect=AssertionError('no deletion')):
                with self.assertRaisesRegex(ValueError,'identity differs'):
                    workspace.dispose_family_resources(folder,row)

    def test_additional_forged_identity_custody_and_summary_are_rejected_even_when_resealed(self):
        mutations=[
            lambda record:record['identity'].update(additional_containers=['7'*64]),
            lambda record:record.update(additional_containers=['7'*64]),
            lambda record:record['additional_container_custody'].update({'7'*64:'REMOVED'}),
            lambda record:record['additional_container_custody'].update({'8'*64:'REMOVED'}),
            lambda record:record.update(status='PASS'),
            lambda record:record.update(resource_disposition='all owned resources removed'),
            lambda record:record.update(outer_ack_sha256='0'*64),
            lambda record:record['identity'].update(source_commit='forged'),
        ]
        for index,mutate in enumerate(mutations):
            with self.subTest(mutation=index),tempfile.TemporaryDirectory() as temporary:
                folder,row=self.receipt(Path(temporary),guarded=True,additional=['9'*64,'8'*64])
                with patch.object(receipts.time,'monotonic',return_value=2.):
                    receipts.acknowledge_guarded(folder,row)
                record,_=self.remove(folder,row,fail_label='additional-1-container')
                original=json.loads((folder/'receipt.json').read_text())
                mutate(record)
                # Reseal only the independent forged administrative record.
                output=folder/'resource-removal'
                (output/'completion.json').write_text(json.dumps(record))
                (output/'manifest.json').unlink();receipts.manifest(output)
                with self.assertRaises(ValueError):
                    receipts.resource_disposition(folder,original)

    def test_additional_legacy_identity_and_summary_remain_byte_compatible(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder,row=self.receipt(Path(temporary))
            record,_=self.remove(folder,row)
            self.assertEqual(set(record['identity']),{'family','case','source_commit','product_tree','image','container','clone'})
            self.assertNotIn('additional_containers',record)
            self.assertNotIn('additional_container_custody',record)
            self.assertEqual(record['resource_disposition'],'container=REMOVED; volume=REMOVED')
            self.assertEqual(receipts.resource_disposition(folder,row)['administrative_removal_status'],'PASS')


if __name__=='__main__':unittest.main()
