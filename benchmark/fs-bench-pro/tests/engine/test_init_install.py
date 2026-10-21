"""Retain actual measured Init for public installation; no second Init or fake metadata."""
import copy
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

BENCH=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(BENCH))
from engine import project,fixtures,receipts,workspace


class InitInstall(unittest.TestCase):
    def setup(self,root,*,change=None,write_count=8,mutate_verifier=False):
        case=copy.deepcopy(json.loads((BENCH/'families/dedup_cross_file/family.json').read_text())['cases'][0])
        source=root/'source';source.mkdir()
        shell=root/'benchmark/fs-bench-pro/families/dedup_cross_file/workload.sh'
        shell.parent.mkdir(parents=True);shell.write_text('original qualified workload placeholder')
        prepared={'family':'dedup_cross_file','case':case['id'],'schema':'fs-bench-pro-prepared-native-import-v1',
            'source':str(source),'source_uid':501,'source_gid':20,'fixture':{'files':1,'entries':3,'logical_bytes':1048576},
            'source_qualification':{'status':'PASS'},'cache':'setup warmth unknown'}
        build={'socket':'/socket','binaries':{name:{'path':'/'+name,'sha256':name} for name in ('runtime','daemon','workload-linux')}}
        current={'source_commit':'c'*40,'product_tree':'d'*40,'files':{
            'benchmark/fs-bench-pro/engine/workspace.py':'e'*64,
            'benchmark/fs-bench-pro/engine/receipts.py':'f'*64}}
        calls=[];self.owners=[]
        class Stream:
            def __init__(self):self.writes=[]
            def write(inner,body):
                calls.append(('write',body));inner.writes.append(body)
                return write_count
            def flush(inner):calls.append(('flush',))
            def close(inner):pass
        outer=self
        class Runtime:
            def __init__(inner,argv,folder,label):
                calls.append(('launch',argv));inner.argv=argv;inner.rows=[];inner.container=None
                inner.selector=inner.raw=inner.stderr=None
                inner.process=SimpleNamespace(pid=4242,returncode=None,stdin=Stream(),stdout=None,wait=inner.wait)
                inner.folder=Path(folder);inner.label=label
                inner.manifest=Path(argv[argv.index('--manifest')+1])
                inner.sealed=Path(argv[argv.index('--sealed')+1])
                inner.installed=Path(argv[argv.index('--installed-manifest')+1]) if '--installed-manifest' in argv else None
                inner.retained=False;outer.owners.append(inner)
            def wait(inner,timeout):
                calls.append(('wait',timeout));inner.process.returncode=0;return 0
            def event(inner,name,deadline):
                calls.append(('event',name))
                if name=='project_init':
                    inner.sealed.write_bytes(b'actual sealed Store fixture');inner.manifest.write_bytes(b'actual host manifest fixture')
                    fields={'case':case['id'],'root':'1'*64,'stack':'31'+'2'*32,'branch':'11'+'3'*32,
                        'host_sqlite':'3.50.0','profile':'Disposable/WAL/OFF','entries':3,'files':1,
                        'logical_bytes':inner.sealed.stat().st_size,'allocated_bytes':inner.sealed.stat().st_blocks*512,
                        'manifest_path':str(inner.manifest),'manifest_sha256':hashlib.sha256(inner.manifest.read_bytes()).hexdigest()}
                elif name=='project_install':
                    if inner.process.stdin.writes!=[b'install\n']:raise AssertionError('exact one install write required')
                    inner.installed.write_bytes(b'actual public installed manifest fixture')
                    inner.container='a'*64
                    fields={**inner.rows[0]['fields'],'container':inner.container,'daemon_sqlite':'3.53.2',
                        'installed_manifest':str(inner.installed),'installed_manifest_sha256':hashlib.sha256(inner.installed.read_bytes()).hexdigest(),
                        'host_manifest_sha256':hashlib.sha256(inner.manifest.read_bytes()).hexdigest()}
                    if change:change(fields,inner)
                elif name=='setup_container_stopped':fields={}
                elif name=='finished':fields={}
                else:raise AssertionError(name)
                row={'event':name,'fields':fields,'value':inner.container if name=='setup_container_stopped' else '',
                     'sequence':len(inner.rows)+1,'span':{'duration_ns':5}}
                inner.rows.append(row);return row
            def retain(inner,error):
                inner.retained=True;calls.append(('retain',));return {'state':'HOST_FENCE_ONLY_REMOTE_UNKNOWN'}
        class Observer:
            def __init__(inner,process,folder,label,limit):
                inner.process=process;calls.append(('observer_start',limit))
            def check(inner):calls.append(('observer_check',));return {'rss_status':'PASS_CURRENT_OBSERVATIONS'}
            def finish(inner):
                calls.append(('observer_finish',))
                if inner.process.returncode is None:raise RuntimeError('unknown child wait; swaps unavailable')
                return {'status':'PASS','known_child_wait':True,'swap_status':'PASS_AGGREGATE_ZERO_BEFORE_AFTER'}
        def command(argv,folder,label,seconds,**options):
            calls.append(('command',label,argv))
            out=Path(folder)/(label+'.stdout');out.parent.mkdir(parents=True,exist_ok=True)
            if label=='init-install-empty-volume':out.write_text(argv[-1]+'\n')
            elif label=='independent-verifier':
                if mutate_verifier:
                    Path(argv[argv.index('--sealed')+1]).write_bytes(b'physically changed observer SQLite identity')
                event_path=Path(argv[argv.index('--receipt')+1]);event_path.write_text(json.dumps({'event':'project_verified','fields':{'status':'PASS','root':'1'*64}})+'\n'+json.dumps({'event':'finished'})+'\n');out.write_text('')
            elif argv[1]=='init':raise AssertionError('cannot end host process and discard actual SealedProject before install')
            else:raise AssertionError(label)
            return {'stdout':str(out),'complete_wall_ns':7,'status':'PASS'}
        def mounted(*args):calls.append(('mounted',));args[4].update(cleanup='Gone',custody='KNOWN_STOP')
        stack=ExitStack()
        for module,name,options in (
            (project.identity,'ROOT',{'new':root}),(project.identity,'source_identity',{'return_value':current}),
            (project.identity,'load_build',{'return_value':build}),(fixtures,'load',{'return_value':prepared}),
            (fixtures,'validate_import_qualification',{'return_value':prepared['source_qualification']}),
            (receipts,'command',{'side_effect':command}),(receipts,'HostProcessObserver',{'new':Observer}),
            (workspace.cell_runner,'EventProcess',{'new':Runtime}),(workspace,'verify_import_mount',{'side_effect':mounted}),
        ):stack.enter_context(patch.object(module,name,**options))
        return stack,case,prepared,build,calls

    def test_import_parent_retains_measured_init_and_installs_only_after_independent_proof(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);stack,case,prepared,build,calls=self.setup(root)
            with stack:row=project.one_init(case,'prepared','build',root/'case',family='dedup_cross_file')
            self.assertEqual(row['status'],'INELIGIBLE',row.get('original_failure'))
            self.assertEqual(row['proof_status'],'PASS')
            modes=[item[1][1] for item in calls if item[0]=='launch']
            self.assertEqual(modes,['init-install'])
            self.assertEqual([item[1] for item in calls if item[0]=='write'],[b'install\n'])
            proof=next(i for i,item in enumerate(calls) if item[:2]==('command','independent-verifier'))
            install=next(i for i,item in enumerate(calls) if item[0]=='write')
            mounted=next(i for i,item in enumerate(calls) if item[0]=='mounted')
            self.assertLess(proof,install);self.assertLess(install,mounted)
            self.assertEqual(row['additional_containers'],['a'*64])
            self.assertEqual(row['installation']['global_profile'],'Disposable/WAL/OFF')
            self.assertIn('launch-to-project_init',row['timing_scope'])
            self.assertFalse(any('rm' in item[2] for item in calls if item[0]=='command'))

    def test_install_binding_refuses_changed_identity_metadata_size_and_encoded_ack(self):
        fields={'root':'f'*64,'stack':'31'+'f'*32,'branch':'11'+'f'*32,'profile':'Durable',
            'logical_bytes':999,'host_sqlite':'unknown','host_manifest_sha256':'0'*64,
            'installed_manifest_sha256':'0'*64,'container':'short','daemon_sqlite':''}
        for key,value in fields.items():
            with self.subTest(field=key),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);stack,case,prepared,build,calls=self.setup(root,change=lambda fields,owner:fields.update({key:value}))
                with stack:
                    row={};owner=project.fresh_init_start(case,prepared,build,root,row,deadline=project.time.monotonic()+10,host_rss_limit_bytes=2*1024**3)
                    with self.assertRaises(ValueError):project.fresh_init_finish(owner,row,deadline=project.time.monotonic()+10)
                    project.fresh_init_close(owner,row,RuntimeError('retained binding refusal'))
                self.assertEqual([item[1] for item in calls if item[0]=='write'],[b'install\n'])
                self.assertTrue(self.owners[-1].retained)
                self.assertFalse(any(item[0]=='mounted' for item in calls))

    def test_short_install_write_is_not_resent_and_partial_runtime_is_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);stack,case,prepared,build,calls=self.setup(root,write_count=1)
            with stack:
                row={};owner=project.fresh_init_start(case,prepared,build,root,row,deadline=project.time.monotonic()+10,host_rss_limit_bytes=None)
                with self.assertRaisesRegex(RuntimeError,'short'):
                    project.fresh_init_finish(owner,row,deadline=project.time.monotonic()+10)
                project.fresh_init_close(owner,row,RuntimeError('short original write'))
            self.assertEqual([item[1] for item in calls if item[0]=='write'],[b'install\n'])
            self.assertFalse(any(item[:2]==('event','project_install') for item in calls))
            self.assertTrue(self.owners[-1].retained)
            self.assertEqual(row['status'],'FAIL')

    def test_duplicate_ack_or_wrong_stop_is_not_known_successful_installation(self):
        for duplicate in (True,False):
            with self.subTest(duplicate=duplicate),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);stack,case,prepared,build,calls=self.setup(root)
                with stack:
                    row={};owner=project.fresh_init_start(case,prepared,build,root,row,deadline=project.time.monotonic()+10,host_rss_limit_bytes=None)
                    runtime=owner['runtime'];original=runtime.event
                    def event(name,deadline):
                        result=original(name,deadline)
                        if name=='setup_container_stopped':
                            if duplicate:runtime.rows.append(copy.deepcopy(owner['ack']))
                            else:result['value']='b'*64
                        return result
                    runtime.event=event
                    with self.assertRaises(ValueError):project.fresh_init_finish(owner,row,deadline=project.time.monotonic()+10)
                    project.fresh_init_close(owner,row,RuntimeError('unqualified original acknowledgement'))
                self.assertTrue(runtime.retained)
                self.assertEqual([item[1] for item in calls if item[0]=='write'],[b'install\n'])

    def test_namespace_init_remains_original_standalone_host_route(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);stack,case,prepared,build,calls=self.setup(root)
            legacy_shell=root/'benchmark/fs-bench-pro/families/init_namespace/workload.sh'
            legacy_shell.parent.mkdir(parents=True);legacy_shell.write_text('unchanged namespace workload placeholder')
            def command(argv,folder,label,seconds,**options):
                calls.append(('legacy',argv[1]))
                if argv[1]=='init':
                    Path(folder/'store.sqlite').write_bytes(b'legacy sealed Store')
                    events=[{'event':'project_init','span':{'duration_ns':5},'fields':{'logical_bytes':19,'allocated_bytes':4096}}, {'event':'finished'}]
                elif argv[1]=='verify-init':events=[{'event':'project_verified','fields':{'status':'PASS'}},{'event':'finished'}]
                else:raise AssertionError('legacy namespace must not install or launch a daemon')
                Path(argv[argv.index('--receipt')+1]).write_text(''.join(json.dumps(event)+'\n' for event in events))
                return {'complete_wall_ns':7}
            with stack,patch.object(receipts,'command',side_effect=command):
                row=project.one_init(case,'prepared','build',root/'legacy')
            self.assertEqual(row['status'],'INELIGIBLE',row.get('original_failure'))
            self.assertEqual(row['cleanup'],'SEALED_CLOSED; no mount')
            self.assertEqual([item for item in calls if item[0]=='legacy'],[('legacy','init'),('legacy','verify-init')])
            self.assertFalse(any(item[0] in ('launch','observer_start','write') for item in calls))

    def test_mounted_import_refuses_missing_public_install_or_changed_custody_files(self):
        for mutation in ('missing','container','manifest','store'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as temporary:
                output=Path(temporary);store=output/'store.sqlite';store.write_bytes(b'actual imported Store')
                manifest=output/'installed.manifest';manifest.write_bytes(b'actual SDK installed manifest')
                provision={'schema':'fs-bench-pro-public-init-install-v1','status':'PASS','global_profile':'Disposable/WAL/OFF',
                    'volume':'layerfs-fsb-sample-'+'b'*16,'container':'a'*64,'manifest':str(manifest),
                    'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),'store_sha256':hashlib.sha256(store.read_bytes()).hexdigest()}
                row={'installation':provision,'clone':{'volume':provision['volume']},'additional_containers':['a'*64]}
                if mutation=='missing':row.pop('installation')
                elif mutation=='container':row['additional_containers']=[]
                elif mutation=='manifest':manifest.write_bytes(b'changed installed manifest')
                else:store.write_bytes(b'changed imported Store')
                with patch.object(fixtures,'install_closed_history_store',side_effect=AssertionError('byte installation cannot replace public qualification')):
                    with self.assertRaisesRegex(ValueError,'actual public installation'):
                        workspace.verify_import_mount({}, {}, {}, output, row, {'work':project.time.monotonic()+10})

    def test_typed_observer_changes_only_its_copy_and_held_sdk_source_stays_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);stack,case,prepared,build,calls=self.setup(root,mutate_verifier=True)
            with stack:row=project.one_init(case,'prepared','build',root/'case',family='dedup_cross_file')
            self.assertEqual(row['status'],'INELIGIBLE',row.get('original_failure'))
            observed=row['init_observer_copy']
            self.assertNotEqual(observed['source'],observed['copy'])
            self.assertTrue(observed['source_unchanged'])
            self.assertEqual(observed['source_sha256_before'],observed['source_sha256_after_proof'])
            self.assertEqual(observed['copy_sha256_before'],observed['source_sha256_before'])
            self.assertNotEqual(observed['copy_sha256_after_proof'],observed['copy_sha256_before'])
            self.assertEqual(Path(observed['source']).read_bytes(),b'actual sealed Store fixture')
            self.assertEqual(row['installation']['store_sha256'],observed['source_sha256_before'])

    def test_independent_observer_copy_rejects_copy_or_source_mismatch_before_proof(self):
        import shutil
        for mutate_source in (True,False):
            with self.subTest(mutate_source=mutate_source),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);stack,case,prepared,build,calls=self.setup(root)
                with stack:
                    row={};owner=project.fresh_init_start(case,prepared,build,root,row,deadline=project.time.monotonic()+10,host_rss_limit_bytes=None)
                    if mutate_source:
                        owner['sealed'].write_bytes(b'changed held immutable source')
                        with self.assertRaisesRegex(ValueError,'source changed'):
                            project.fresh_init_observer_copy(owner,root,row,deadline=project.time.monotonic()+10)
                    else:
                        original=shutil.copy2
                        def copy(source,target):
                            original(source,target);Path(target).write_bytes(b'wrong independent copy')
                        with patch.object(shutil,'copy2',side_effect=copy):
                            with self.assertRaisesRegex(ValueError,'identity differs'):
                                project.fresh_init_observer_copy(owner,root,row,deadline=project.time.monotonic()+10)
                    project.fresh_init_close(owner,row,RuntimeError('unqualified copy identity'))
                self.assertFalse(any(item[0]=='write' for item in calls))

    def test_post_ack_identity_work_is_charged_to_original_proof_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);stack,case,prepared,build,calls=self.setup(root)
            original=project.fresh_init_start
            def start(*args,**kwargs):
                result=original(*args,**kwargs)
                # Model one second of identity work after the real ACK, without
                # sleeping or altering any workload/limit.
                result['init_acknowledged_ns']-=1_000_000_000
                return result
            with stack,patch.object(project,'fresh_init_start',side_effect=start):
                row=project.one_init(case,'prepared','build',root/'case',family='dedup_cross_file')
            self.assertEqual(row['status'],'INELIGIBLE',row.get('original_failure'))
            self.assertGreaterEqual(row['proof_wall_ns'],1_000_000_000)
            self.assertLess(row['complete_wall_ns'],1_000_000_000)


if __name__=='__main__':unittest.main()
