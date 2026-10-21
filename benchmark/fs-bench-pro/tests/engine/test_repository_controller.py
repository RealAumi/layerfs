"""Exact original repository lifecycle; fixtures/providers are choreography mocks."""
import ast
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

BENCH=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(BENCH))
from engine import project, workspace
if os.environ.get('LAYERFS_REPOSITORY_PROJECT_SOURCE'):
    specification=importlib.util.spec_from_file_location('engine.project_repository_authoring',os.environ['LAYERFS_REPOSITORY_PROJECT_SOURCE'])
    project=importlib.util.module_from_spec(specification)
    specification.loader.exec_module(project)


if os.environ.get('LAYERFS_HOST_OBSERVER_SOURCE'):
    observer_source=Path(os.environ['LAYERFS_HOST_OBSERVER_SOURCE']).read_bytes()
    if hashlib.sha256(observer_source).hexdigest()!='d2aa05030a2be08669dcdad378cc2749c32bfe6e991badc5870f8bb7b9925b06':
        raise ValueError('exact qualified host observer suffix required')
    exec(compile(observer_source,'qualified-host-observer','exec'),project.receipts.__dict__)


def case():
    return json.loads((BENCH/'families/repository_history/family.json').read_text())['cases'][2]


class RepositoryController(unittest.TestCase):
    def prepared(self,root,selected):
        folder=root/'prepared';folder.mkdir();code=folder/'code';code.mkdir();states=[];files={}
        for local,index in enumerate(selected['repository_schedule']['full157_indices'],1):
            inside=f'repository/checkpoints/{local}';target=code/inside;(target/'blobs').mkdir(parents=True)
            statefiles={}
            for name,body in [('manifest.tsv',b'original selected manifest'),('previous.tsv',b'original selected previous')]:
                (target/name).write_bytes(body);digest=hashlib.sha256(body).hexdigest();files[inside+'/'+name]=digest;statefiles[name]=digest
            oracle=root/f'oracle-{local}.json';oracle.write_text(json.dumps({'66696c65':['100644',1,hashlib.sha256(b'x').hexdigest()]}))
            oraclecopy=code/f'repository/oracles/{local}.json';oraclecopy.parent.mkdir(exist_ok=True);oraclecopy.write_bytes(oracle.read_bytes())
            files[f'repository/oracles/{local}.json']=hashlib.sha256(oracle.read_bytes()).hexdigest()
            states.append({'index':local,'full157_index':index,'input':str(target),'helper_input':inside,'runtime_input':f'/input/checkpoint-{local}',
                           'oracle':str(oracle),'oracle_sha256':files[f'repository/oracles/{local}.json'],
                           'input_seal':{'files':statefiles,'directories':['.','blobs']},
                           'previous_full157_index':None if local==1 else selected['repository_schedule']['full157_indices'][local-2]})
        return {'schema':'fs-bench-pro-prepared-repository-history-v1','family':'repository_history','case':selected['id'],'recipe':selected['id'],
                'fixture':{'files':0,'logical_bytes':0},'source_uid':1,'source_gid':1,'helpers':{'root':str(code),'files':files},
                'provision':{'manifest':str(root/'original.manifest'),'global_profile':'Disposable/WAL/OFF'},
                'repository_inputs':{'status':'PASS','case':selected['id'],'manifest_sha256':selected['fixture']['manifest_sha256'],
                   'source_tip':selected['fixture']['source_tip'],'full157_indices':selected['fixture']['selection'],'state_count':17,'states':states,'input_identity':'sealed-native-only'}}

    def test_admission_and_parity_refuse_changed_selection_helper_or_nonempty_master(self):
        import copy
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);selected=case();prepared=self.prepared(root,selected)
            self.assertEqual(project.repository_admit(selected,prepared,{})['states'],17)
            for change in ('source','missinghelper','nonempty','adjacentprevious'):
                bad=copy.deepcopy(prepared)
                if change=='source':bad['repository_inputs']['full157_indices'][-1]=156
                if change=='missinghelper':bad['helpers']['files'].pop('repository/checkpoints/17/manifest.tsv')
                if change=='nonempty':bad['fixture']['files']=1
                if change=='adjacentprevious':bad['repository_inputs']['states'][1]['previous_full157_index']=10
                with self.assertRaises(ValueError):project.repository_admit(selected,bad,{})

    def test_created_only_transcript_never_fabricates_an_up_to_date_commit(self):
        fields={'commit_id':'12'+'a'*64,'parent':'-','root':'b'*64,'stack':'31'+'c'*32,'base_layer':'32'+'d'*64}
        records=[{'index':1,'commit':{'fields':{'commit_kind':'Committed'}},'mapping':fields,'oracle':'/one'},
                 {'index':2,'commit':{'fields':{'commit_kind':'UpToDate','root':'b'*64}},'mapping':dict(fields),'oracle':'/two'}]
        full,created,unique=project.repository_transcripts('0'*64,records)
        self.assertEqual(len(full.splitlines()),3);self.assertEqual(len(created.splitlines()),2)
        self.assertEqual(unique,[fields]);self.assertIn('/two',full);self.assertNotIn('/two',created)

    def choreography(self,fail_verify=False):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();selected=case();prepared=self.prepared(root,selected)
            output=root/'benchmark-results/fs-bench-pro/case';actions=[];runtimes=[]
            class Runtime:
                selector=raw=stderr=None
                def __init__(self,label):
                    self.process=SimpleNamespace(stdin=None,stdout=None,pid=101 if label=='performance' else 102,returncode=None)
                    def waited(**kwargs):
                        actions.append((label,'known-wait',self.process.pid));self.process.returncode=0;return 0
                    self.process.wait=waited
                    self.label=label;self.container=('1' if label=='performance' else '2')*64;self.index=0
                    self.rows=[{'event':'history_initial_root','fields':{'root':'0'*64,'stack':'31'+'3'*32,'base_layer':'32'+'4'*64}}]
                def send(self,op,key='',path=None,deadline=None):
                    actions.append((self.label,op,str(path)))
                    if op in ('command','verify'):
                        if op=='verify' and fail_verify:raise ValueError('retained original observer failure')
                        return {'fields':{'exit_code':'0'},'span':{'duration_ns':10}}
                    if op=='commit':
                        self.index+=1;return {'fields':{'commit_kind':'Committed','commit_id':'12'+f'{self.index:064x}',
                            'parent':'-' if self.index==1 else '12'+f'{self.index-1:064x}','root':f'{self.index:064x}',
                            'stack':'31'+'3'*32,'base_layer':'32'+'4'*64},'span':{'duration_ns':20}}
                    return {'fields':{},'span':{'duration_ns':1}}
                def event(self,event,deadline):return {'event':event}
                def retain(self,error):return {'container':self.container,'failure':str(error),'scope':'isolated orchestration mock'}
            class Observer:
                def __init__(self,process,folder,label,limit):
                    self.process=process;self.label=label;self.path=Path(folder)/'samples';self.completion_path=Path(folder)/'completion'
                    self.asserted_limit=limit;self.finish_calls=0;actions.append((label,'observer-start',limit))
                    if limit!=8*1024**3:raise ValueError('original repository RSS limit differs')
                def check(self):actions.append((self.label,'observer-check',self.process.pid));return {'rss_status':'PASS_CURRENT_OBSERVATIONS'}
                def finish(self):
                    self.finish_calls+=1;actions.append((self.label,'observer-finish',self.process.returncode))
                    if self.process.returncode is None:raise RuntimeError('unknown wait; sampler stopped and swap unavailable')
                    return {'status':'PASS','pid':self.process.pid,'swap_status':'PASS_AGGREGATE_ZERO_BEFORE_AFTER',
                            'children_scope':'expanded all reaped harness children; not native-specific','rss_limit_bytes':self.asserted_limit}
            def start(prepared,build,out,clone,label,stop):
                folder=Path(out)/label;folder.mkdir();runtime=Runtime(label);runtimes.append(runtime)
                runtime.host_observer=project.receipts.HostProcessObserver(runtime.process,folder,label,8*1024**3)
                actions.append((label,'start',clone['volume']));return runtime,folder
            def context(runtime,op,key='',path=None,deadline=None):
                actions.append((runtime.label,op,str(path)))
                if op=='mount-branch':
                    namespace=1 if runtime.label=='performance' else 100+int(path.split('-')[-1])
                    return {'event':'mount','span':{'duration_ns':3},'fields':{
                        'key':key,'directory':f'/workspaces/{namespace}',
                        'workspace_incarnation':key,'workspace_namespace':namespace}}
                body=Path(path).read_text().strip().split('\t');index=int(key.split('-')[-1]);return {'fields':{'root':f'{index:064x}','head':'12'+f'{index:064x}'}}
            def fork(runtime,selected,spec,graph,out,stop):
                fields={'branch_id':'11'+'5'*32,'name':'history','stack':'31'+'3'*32,'base_layer':'32'+'4'*64,'root':'0'*64,'head':'-'}
                graph['branches']['history']={'commits':[],'source_role':None,'final_head':'-','final_root':'0'*64}
                actions.append(('performance','fork','history'));return {'fields':fields}
            def end(runtime,key,row,stop):actions.append((runtime.label,'EndGone',key));return {'span':{'duration_ns':4}}
            def execute(argv,folder,name,seconds,**kwargs):
                self.assertGreater(seconds,0);self.assertLessEqual(seconds,120)
                actions.append(('docker',name,argv))
                if name.startswith('observed-copy-'):
                    Path(argv[-1]).write_text('100644\t1\t'+hashlib.sha256(b'x').hexdigest()+'\t66696c65\n')
                return {'status':'PASS','argv':argv,'exit_code':0,'attempts':1,'stdout':str(Path(folder)/'unused')}
            def normalize(raw,dest,stop):
                actions.append(('frozen','normalize',str(raw)));return {'path':str(dest),'normalized_identity':{'sha256':'f'*64},'raw_files':{'store.sqlite':{'sha256':'e'*64,'size':1}}}
            def graphproof(*args):
                actions.append(('frozen','typed+unfiltered-census','twoBranchesBeforeVerifier'))
                return {'status':'PASS','scope':'mock; real public typed fixture separately qualified'}
            build={'socket':'/owned/docker','binaries':{name:{'path':'/'+name,'sha256':name} for name in ('runtime','daemon')}}
            with ExitStack() as stack:
                for module,name,options in [
                    (project.identity,'ROOT',{'new':root}),(project.identity,'source_identity',{'return_value':{'source_commit':'a'*40,'product_tree':'b'*40}}),
                    (project.identity,'load_build',{'return_value':build}),(workspace.fixtures,'load',{'return_value':prepared}),
                    (workspace.fixtures,'clone',{'return_value':{'volume':'layerfs-fsb-sample-'+'6'*16}}),
                    (workspace.fixtures,'stage',{'side_effect':lambda *args:actions.append(('staging','once',args[0]))}),
                    (project.receipts,'HostProcessObserver',{'new':Observer}),
                    (project,'repository_runtime',{'side_effect':start}),(workspace,'context_send',{'side_effect':context}),
                    (workspace,'context_fork',{'side_effect':fork}),(workspace,'context_end',{'side_effect':end}),
                    (workspace,'history_container_profile',{'return_value':{}}),(workspace,'history_resource_guard',{'return_value':{}}),
                    (workspace,'context_observations',{'return_value':None}),(workspace,'context_history',{'return_value':{'status':'PASS'}}),
                    (project.receipts,'command',{'side_effect':execute}),(workspace.oracle,'prepare_closed_store',{'side_effect':normalize}),
                    (project,'repository_graph_proof',{'side_effect':graphproof})]:stack.enter_context(patch.object(module,name,**options))
                row=project.one_repository_history(selected,'prepared','build',output)
            self.assertEqual(len(row['repository']['records']),17)
            self.assertEqual(row['host_resource_observations']['status'],'FAIL' if fail_verify else 'PASS_CURRENT_RSS_AND_EXPANDED_AGGREGATE_ZERO_SWAPS')
            self.assertEqual(row['host_resource_observations']['runtimes']['performance']['swap_status'],'PASS_AGGREGATE_ZERO_BEFORE_AFTER')
            for label in ('performance','verification'):
                finishes=[i for i,a in enumerate(actions) if a[0]==label and a[1]=='observer-finish']
                self.assertEqual(len(finishes),1)
                if label=='verification' and fail_verify:
                    self.assertIsNone(actions[finishes[0]][2])
                else:
                    waited=next(i for i,a in enumerate(actions) if a[0]==label and a[1]=='known-wait')
                    self.assertLess(waited,finishes[0])
            self.assertEqual([r['full157_index'] for r in row['repository']['records']],selected['fixture']['selection'])
            self.assertEqual(row['phases']['command_ns'],170);self.assertEqual(row['phases']['commit_ns'],340)
            self.assertEqual(row['complete_wall_ns'],510)
            self.assertFalse(any(isinstance(a[-1],list) and ('rm' in a[-1] or 'remove' in a[-1]) for a in actions))
            indices={name:next(i for i,a in enumerate(actions) if a[0]==label and a[1]==name)
                     for name,label in [('stop','performance'),('normalize','frozen'),('typed+unfiltered-census','frozen')]}
            self.assertLess(indices['stop'],indices['normalize']);self.assertLess(indices['normalize'],indices['typed+unfiltered-census'])
            second=next(i for i,a in enumerate(actions) if a[0]=='verification' and a[1]=='start')
            self.assertLess(indices['typed+unfiltered-census'],second)
            transfers=[a[-1] for a in actions if a[1].startswith('transfer-')]
            self.assertEqual(len(transfers),17)
            self.assertTrue(all(not argv[-2].startswith('1'*64+':') for argv in transfers))
            if fail_verify:
                self.assertEqual(row['status'],'FAIL');self.assertEqual(row['proof_status'],'FAIL')
                self.assertFalse(row['resource_removal_pending']);self.assertEqual(row['retained_containers'],['1'*64,'2'*64])
                self.assertIn('2'*64,row['leaked_mount_keys'])
            else:
                self.assertEqual(row['status'],'INELIGIBLE');self.assertEqual(row['proof_status'],'PASS')
                self.assertEqual(row['additional_containers'],['2'*64]);self.assertTrue(row['resource_removal_pending'])
                self.assertEqual(len(row['repository']['native_proofs']),17)

    def test_actual_qualified_observer_finishes_after_original_known_runtime_wait(self):
        with tempfile.TemporaryDirectory() as temporary:
            actions=[]
            process=SimpleNamespace(pid=999,returncode=None,poll=lambda:None)
            def waited(**kwargs):actions.append('known-wait');process.returncode=0;return 0
            process.wait=waited
            runtime=SimpleNamespace(process=process,send=lambda op,**kwargs:actions.append(op),event=lambda *args:actions.append('finished'))
            before={'ru_nswap':0,'user_cpu_ns':10,'system_cpu_ns':20,'input_block_operations':2,'output_block_operations':3}
            after={**before,'user_cpu_ns':30,'input_block_operations':4}
            def usage():actions.append('children-usage');return before if actions.count('children-usage')==1 else after
            with patch.object(project.receipts,'_host_children_usage',side_effect=usage),patch.object(project.receipts.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='4096\n',stderr='')):
                runtime.host_observer=project.receipts.HostProcessObserver(process,temporary,'actual-adapter',8*1024**3,nominal_interval=10)
                result=project.repository_stop(runtime,time.monotonic()+10)
            self.assertEqual(result['status'],'PASS');self.assertEqual(result['rss_samples'],1)
            self.assertEqual(result['children_aggregate_delta']['user_cpu_ns'],20)
            self.assertEqual(result['children_aggregate_delta']['input_block_operations'],2)
            self.assertLess(actions.index('known-wait'),len(actions)-1)
            self.assertEqual(actions[-1],'children-usage')
            self.assertTrue(result['known_child_wait']);self.assertTrue(result['sampler_join_known'])
            self.assertIn('all reaped children',result['children_scope'])
            self.assertNotIn('native-specific swaps',result['swap_status'])

    def test_startup_host_guard_failure_keeps_actual_runtime_and_no_setup_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime=SimpleNamespace(process=SimpleNamespace(pid=7),container='7'*64)
            observer=SimpleNamespace(check=lambda:(_ for _ in ()).throw(RuntimeError('RSS guard unavailable')))
            prepared={'case':'deepseek-stride10','source_uid':1,'source_gid':1,'provision':{'manifest':'original'}}
            build={'socket':'socket','binaries':{'runtime':{'path':'runtime'},'daemon':{'path':'daemon'}}}
            with patch.object(workspace.cell_runner,'EventProcess',return_value=runtime),patch.object(project.receipts,'HostProcessObserver',return_value=observer),patch.object(project.receipts,'command') as command:
                with self.assertRaises(RuntimeError) as failed:project.repository_runtime(prepared,build,temporary,{'volume':'owned'},'performance',time.monotonic()+10)
                self.assertIs(failed.exception.event_process,runtime);self.assertIs(runtime.host_observer,observer)
                command.assert_not_called()

    def test_performance_stop_freeze_and_two_runtime_same_volume_native_proofs(self):self.choreography()
    def test_original_native_failure_retains_both_containers_and_does_not_delete(self):self.choreography(True)


if __name__=='__main__':unittest.main()
