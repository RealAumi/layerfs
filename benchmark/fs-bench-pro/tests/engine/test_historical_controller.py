"""Original access controller qualification with mocked public bridge/tools only."""
import copy
import hashlib
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import fixtures, oracle, workspace


def declared(index=0):
    return json.loads((BENCH / 'families/historical_access/family.json').read_text())['cases'][index]


def typed(prefix, text):
    return prefix + hashlib.sha256(text.encode()).hexdigest()[:32 if prefix in ('11','31') else 64]


def prepared_case(case, folder):
    plan=fixtures.historical_plan(case); graph={'branches':{}}; acks=[]; by_role={}
    for role in plan['graph_roles']:
        source=plan['fork_sources'].get(role,{'role':None,'local':0})
        prior=by_role[source['role']][source['local']] if source['role'] else None
        parent=prior['commit_id'] if prior else '-'; root=prior['root'] if prior else 'a'*64
        branch={'branch_id':typed('11',role),'name':'original-'+role,'stack':typed('31','stack'),'base_layer':typed('32','base'),
                'initial_parent':parent,'initial_root':root,'source_role':source['role'],'source_local':source['local'],'commits':[]}
        by_role[role]={}
        for local in range(1,plan['local_commits'].get(role,0)+1):
            fields={'commit_id':typed('12',role+str(local)),'root':hashlib.sha256((role+str(local)).encode()).hexdigest(),
                    'stack':branch['stack'],'base_layer':branch['base_layer'],'parent':parent}
            branch['commits'].append({'index':local,'commit':{'fields':fields}}); by_role[role][local]=fields
            acks.append({'role':role,'local':local,'commit_id':fields['commit_id'],'root_id':fields['root'],'layer_stack_id':fields['stack'],
                         'parent_commit_id':None if parent=='-' else parent,'base_layer_id':fields['base_layer']})
            parent,root=fields['commit_id'],fields['root']
        branch.update(final_head=parent,final_root=root);graph['branches'][role]=branch
    selected=next(row for row in acks if row['role']==plan['source_role'] and row['local']==plan['selected_local'])
    manifest=folder/'selected.tsv';manifest.write_text('mock independent selected manifest\n')
    project=folder/'installed.manifest';project.write_text('mock immutable producer manifest\n')
    return {'fixture':{'recipe':case['id'],'fixture_sha256':'a'*64},'helpers':{'files':{'workload.sh':'b'*64}},
            'source_uid':501,'source_gid':20,'provision':{'manifest':str(project)},'producer_dependency':{'plan':plan},
            'closed_producer':{'producer_case':plan['producer_case'],'graph':graph,'acknowledgements':acks,'store_sha256':'c'*64,'transcript_sha256':'d'*64},
            'historical_selection':{'source_role':plan['source_role'],'original_source_role':plan['original_source_role'],
                                    'local':plan['selected_local'],'acknowledged_commit':selected,'manifest':str(manifest)}}


class FakeRuntime:
    def __init__(self, prepared, output, *, bad=None):
        self.graph=copy.deepcopy(prepared['closed_producer']['graph']);self.output=output;self.bad=bad;self.rows=[];self.operations=[]
        self.container='a'*64;self.retained=[];self.pending=None;self.selector=io.StringIO();self.raw=io.StringIO();self.stderr=io.StringIO()
        self.process=self;self.stdin=self;self.stdout=io.StringIO()
        (output/'runtime.events.jsonl').write_text('{"event":"finished"}\n')
    def close(self): pass
    def wait(self,timeout): return 1 if self.bad=='stop' else 0
    def retain(self,error): self.retained.append(str(error));return {'status':'RETAINED','mock_only':True}
    def write(self,raw):
        parts=raw.decode().rstrip('\n').split('\t');self.pending=parts;self.operations.append(parts)
        return len(raw)-1 if self.bad=='short' else len(raw)
    def emit(self,event,fields=None):
        row={'event':event,'fields':fields or {},'sequence':len(self.rows)+1,'span':{'duration_ns':100}}
        self.rows.append(row);return row
    def event(self,event,deadline):
        if event in ('protocol_ready','finished'):return self.emit(event)
        op,key,*tail=self.pending
        if op=='history':
            branch=next(b for b in self.graph['branches'].values() if '@'+b['branch_id']==key)
            expected=[];current=branch
            while True:
                expected.extend(r['commit']['fields'] for r in reversed(current['commits']))
                if current['source_role'] is None:break
                parent=self.graph['branches'][current['source_role']];current={**parent,'commits':parent['commits'][:current['source_local']]}
            start,cursor,limit=Path(tail[0]).read_text().strip().split('\t');offset=0 if cursor=='-' else int(bytes.fromhex(cursor).decode())
            page=expected[offset:offset+int(limit)]
            for record in page:self.emit('history_record',record)
            next_offset=offset+len(page)
            if next_offset==len(expected):return self.emit(event,{'records':len(page),'cursor_path':'-'})
            path=self.output/f'cursor-{next_offset}';value=str(next_offset).encode();path.write_bytes(value)
            return self.emit(event,{'records':len(page),'cursor_path':str(path),'cursor_sha256':hashlib.sha256(value).hexdigest(),'cursor_bytes':len(value)})
        if op=='fork':
            _,identifier,name,source,commit=Path(tail[0]).read_text().strip().split('\t')
            source_branch=next(b for b in self.graph['branches'].values() if '@'+b['branch_id']==source)
            fields=next(r['commit']['fields'] for r in source_branch['commits'] if r['commit']['fields']['commit_id']==commit)
            return self.emit(event,{'branch_id':identifier,'name':name,'head':commit,'root':fields['root'],'stack':fields['stack'],'base_layer':fields['base_layer']})
        if op=='mount-branch':
            if self.bad=='mount':raise TimeoutError('mock lost mount reply')
            return self.emit(event,{'key':key})
        raise AssertionError('unexpected bridge operation '+repr(self.pending))
    def send(self,op,key='',path=None,**options):
        self.operations.append([op,key,str(path) if path else ''])
        if op in ('command','verify'):
            if self.bad=='command':raise TimeoutError('mock command not acknowledged')
            target=self.output/(op+'.stdout');target.write_text('mock helper pass')
            return self.emit(op,{'key':key,'exit_code':'1' if self.bad=='exit' else '0','registered_execs':'0',
                                'command_sha256':workspace.identity.sha256(path),'stdout':str(target)})
        if op=='cleanup':return self.emit(op,{'state':'Gone'})
        return self.emit(op)


class HistoricalController(unittest.TestCase):
    def test_original_deadlines_preserve_reserve_hard_guard_and_owner_stop(self):
        case=declared();self.assertEqual(workspace.access_deadlines(case,10,200),{'work':32,'cleanup':35,'publication':45,'owner':200})
        self.assertEqual(workspace.access_deadlines(case,10,34)['publication'],34)
        for key in ('verification_complete_work_ms','verification_worker_work_ms','cleanup_reserve_ms','verification_hard_ms','publication_guard_seconds','owner_test_invocation_ceiling_ms'):
            bad=copy.deepcopy(case);bad['original_v016_guards'][key]=0
            with self.subTest(key=key),self.assertRaises(ValueError):workspace.access_deadlines(bad,0,120)

    def test_history_pages_select_exact_local_ordinal_excluding_inherited_prefix(self):
        for index in range(6):
            with self.subTest(index=index),tempfile.TemporaryDirectory() as temporary:
                output=Path(temporary);case=declared(index);prepared=prepared_case(case,output);runtime=FakeRuntime(prepared,output)
                selected=workspace.access_selected_history(runtime,prepared,prepared['closed_producer']['graph'],output,time.monotonic()+5)
                self.assertEqual(selected['selected']['commit_id'],prepared['historical_selection']['acknowledged_commit']['commit_id'])
                self.assertTrue(all(op[1]=='@'+selected['source_branch_id'] for op in runtime.operations))
                self.assertEqual(len(selected['history']['pages']),4 if index<4 else 1)
                self.assertEqual(selected['history']['page_limit'],32)
                workspace.access_fork(runtime,case,selected,prepared['closed_producer']['graph'],output,time.monotonic()+5)
                branch=prepared['closed_producer']['graph']['branches']['access']
                self.assertEqual(branch['source_local'],case['historical_access']['selected_ordinal']);self.assertEqual(branch['commits'],[])
                self.assertIn('@'+selected['source_branch_id'],(output/'access-fork.tsv').read_text())

    def flow(self,root,case,bad=None):
        prepared=prepared_case(case,root);current={'source_commit':'mock-source','product_tree':'mock-product','cross_worktree_interference':'mocked only'}
        prepared['closed_producer']['graph'].update(public_proof='earlier producer proof',global_census='earlier producer census')
        build={'socket':'mock','binaries':{name:{'path':'mock-'+name,'sha256':name} for name in ('runtime','daemon')}}
        runtime_holder={}
        def start(argv,output,label):
            runtime=FakeRuntime(prepared,output,bad=bad);runtime_holder['runtime']=runtime;return runtime
        with patch.object(workspace.identity,'ROOT',root),patch.object(workspace.identity,'source_identity',return_value=current),\
             patch.object(workspace.identity,'load_build',return_value=build),patch.object(workspace.fixtures,'load',return_value=prepared),\
             patch.object(workspace.fixtures,'validate_runtime_helpers',return_value={'status':'PASS'}),\
             patch.object(workspace.fixtures,'clone',return_value={'volume':'layerfs-fsb-sample-mock'}),\
             patch.object(workspace.fixtures,'stage',return_value={'status':'PASS'}),patch.object(workspace.cell_runner,'EventProcess',side_effect=start),\
             patch.object(workspace,'history_container_profile',return_value={'Memory':2147483648}),\
             patch.object(workspace,'ordinary_resource_guard',return_value={'oom':0,'oom_kill':0,'swap_current':0}),\
             patch.object(workspace,'context_observations'),patch.object(workspace,'access_graph_proof',return_value={'status':'PASS'}) as proof:
            result=workspace.one_family_case('historical_access',case,'prepared','build',root/'attempt')
        return result,runtime_holder['runtime'],proof

    def test_one_fresh_mount_two_helpers_zero_commits_known_stop_pending_outer_removal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);result,runtime,proof=self.flow(root,declared(5))
            self.assertEqual((result['status'],result['proof_status'],result['cleanup'],result['custody']),('PASS','PASS','Gone','KNOWN_STOP'))
            self.assertEqual((result['sample_count'],result['verification_attempt_count'],result['completed_operation_count']),(0,1,1))
            names=[row[0] for row in runtime.operations]
            self.assertEqual(names.count('mount-branch'),1);self.assertEqual(names.count('command'),1);self.assertEqual(names.count('verify'),1)
            self.assertNotIn('commit',names);self.assertEqual(names.count('unmount'),1);self.assertEqual(names.count('stop'),1)
            commands=[row for row in runtime.operations if row[0] in ('command','verify')]
            self.assertEqual(commands[0][1],commands[1][1]);proof.assert_called_once()
            self.assertTrue(result['resource_removal_pending']);self.assertEqual(runtime.retained,[])
            self.assertNotIn('public_proof',result['topology']);self.assertNotIn('global_census',result['topology'])
            self.assertTrue((root/'attempt/receipt.json').is_file())

    def test_actual_access_result_is_accepted_by_bench_and_published_before_disposal(self):
        spec=importlib.util.spec_from_file_location('historical_actual_cli', BENCH/'bench.py')
        bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);case=declared();result,_,_=self.flow(root,case)
            output=root/'benchmark-results/fs-bench-pro/access-run'
            current={'source_commit':'mock-source','source_tree':'mock-tree','product_tree':'mock-product'}
            calls=[]
            with patch.object(workspace.identity,'ROOT',root), patch.object(workspace.identity,'source_identity',return_value=current), \
                 patch.object(workspace,'one_family_case',return_value=result), \
                 patch.object(workspace.receipts,'acknowledge_guarded',side_effect=lambda *args:calls.append('publication')), \
                 patch.object(workspace,'dispose_family_resources',side_effect=lambda *args:calls.append('disposal')), \
                 contextlib.redirect_stdout(io.StringIO()):
                status=bench.main(['run','historical_access','--case',case['id'],'--build','build','--prepared','prepared','--out',str(output)])
            self.assertEqual(status,0)
            self.assertEqual(result['performance_mode'],'verification-only')
            self.assertEqual(calls,['publication','disposal'])

    def test_unknown_mount_command_stop_and_bad_exit_retain_without_replay(self):
        for bad in ('mount','command','stop','exit','short'):
            with self.subTest(bad=bad),tempfile.TemporaryDirectory() as temporary:
                result,runtime,proof=self.flow(Path(temporary),declared(),bad)
                self.assertEqual(result['status'],'FAIL');self.assertEqual(result['sample_count'],0);self.assertTrue(runtime.retained)
                self.assertNotIn('public_proof',result['topology']);self.assertNotIn('global_census',result['topology'])
                proof.assert_not_called()
                if bad in ('mount','command','exit'):self.assertIn('access',result['retained_mount_keys'])
                self.assertFalse(result.get('resource_removal_pending',False))
                self.assertLessEqual([op[0] for op in runtime.operations].count('mount-branch'),1)

    def test_historical_dispatch_rejects_producer_setup_substitution(self):
        with patch.object(workspace,'one_access_case') as called,self.assertRaises(ValueError):
            workspace.one_family_case('historical_access',declared(),'prepared','build','out',preparation_only=True)
        called.assert_not_called()

    def test_closed_access_proof_binds_producer_header_selected_root_both_passes_and_immutable_census(self):
        for index,fault in [(index,fault) for index in (3,4,5) for fault in (None,'head','selected','bytes','extra')]:
            with self.subTest(index=index,fault=fault),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);case=declared(index);prepared=prepared_case(case,root);graph=json.loads(json.dumps(prepared['closed_producer']['graph'],sort_keys=True))
                selected=prepared['historical_selection'];source=graph['branches'][selected['source_role']];ack=selected['acknowledged_commit']
                graph['branches']['access']={'branch_id':typed('11','access'),'name':'access-'+str(selected['local'])+'-'+case['id'],
                    'stack':source['stack'],'base_layer':source['base_layer'],'initial_parent':ack['commit_id'],'initial_root':ack['root_id'],
                    'final_head':ack['commit_id'],'final_root':ack['root_id'],'source_role':selected['source_role'],'source_local':selected['local'],'commits':[]}
                if fault=='extra':
                    extra=graph['branches'][fixtures.historical_plan(case)['graph_roles'][0]]
                    graph['branches']['unexpected']={**extra,'branch_id':typed('11','unexpected'),'name':'unexpected','commits':[],
                                                       'final_head':extra['initial_parent'],'final_root':extra['initial_root']}
                events=[];data=b'x'*case['historical_access']['reads'][0]['bytes'];payload=data.hex();sha=hashlib.sha256(data).hexdigest()
                for target in case['historical_access']['reads']:
                    events.append({'event':'access_expected_read','fields':{'path':target['path'],'bytes':target['bytes'],'sha256':sha,'payload_hex':payload}})
                for absent in case['historical_access']['absent']:events.append({'event':'access_expected_absent','fields':{'path':absent}})
                commands={}
                for phase in ('reader','verifier'):
                    rows=[('access_case',case['id']),('access_phase',phase),('access_reader_profile',case['historical_access']['reader_profile']),('access_pre_read','0'),('access_commits','0')]
                    for target in case['historical_access']['reads']:
                        rows += [('access_target',target['path']),('access_declared_bytes',str(target['bytes'])),('access_bytes',str(target['bytes'])),
                                 ('access_sha256',sha),('access_ino','200'),('access_dev','1'),('access_nlink','1'),('access_payload_hex',payload)]
                    rows += [('access_absent',path) for path in case['historical_access']['absent']];rows.append(('access_status','pass'))
                    path=root/(phase+'.txt');path.write_text(''.join(key+'='+value+'\n' for key,value in rows))
                    if fault=='bytes' and phase=='verifier':path.write_text(path.read_text().replace(payload,'00'*len(data)))
                    commands[phase]={'fields':{'stdout':str(path)}}
                events += [{'event':'topology_branch_verified','fields':{'role':role,'branch_id':branch['branch_id'],'head':branch['final_head'],'root':branch['final_root']}} for role,branch in graph['branches'].items()]
                events += [{'event':'topology_root_verified','fields':{'role':selected['source_role'],'local':selected['local'],'commit_id':ack['commit_id'],'root':ack['root_id']}},
                           {'event':'workspace_verified','fields':{'status':'PASS','case':case['id'],'topology_case':prepared['closed_producer']['producer_case'],'root':ack['root_id']}},
                           {'event':'finished','fields':{}}]
                if fault=='head':next(event for event in events if event['event']=='topology_branch_verified')['fields']['head']='-'
                if fault=='selected':events[-2]['fields']['root']='0'*64
                public=root/'public.stdout';public.write_text('\n'.join(json.dumps(event) for event in events)+'\n')
                runtime=FakeRuntime(prepared,root);row={'custody':'KNOWN_STOP','clone':{'volume':'layerfs-fsb-sample-mock'},'topology':graph}
                build={'socket':'mock','binaries':{'runtime':{'path':'mock-runtime'},'daemon':{'path':'mock-daemon'}}}
                def command(argv,out,label,seconds,**options):
                    if label=='closed-store-export':
                        raw=root/'graph-store';raw.mkdir();(raw/'store.sqlite').write_bytes(b'mocked exported Store, no SQLite')
                        completion=root/'closed-store-export.completion.json';completion.write_text(json.dumps({'argv':argv,'status':'PASS','exit_code':0,'attempts':1}))
                        return {'status':'PASS'}
                    self.assertEqual(label,'public-access-proof');self.assertIn('verify-access',argv)
                    history=Path(argv[argv.index('--history-file')+1]).read_text()
                    self.assertEqual(history.splitlines()[0],'topology-v1\t'+prepared['closed_producer']['producer_case'])
                    self.assertEqual(len([line for line in history.splitlines() if line.startswith('branch\taccess\t')]),1)
                    self.assertEqual(len([line for line in history.splitlines() if line.startswith('commit\taccess\t')]),0)
                    return {'stdout':str(public),'status':'PASS'}
                def normalize(raw,out,deadline):
                    out.parent.mkdir();out.write_bytes(b'mocked normalized standalone, no SQLite')
                    receipt=out.parent/'normalization.json';receipt.write_text('{}')
                    return {'path':str(out),'receipt':str(receipt),'receipt_sha256':workspace.identity.sha256(receipt)}
                def typed_census(store,tuples,provider,custody):
                    initial=graph['branches'][fixtures.historical_plan(case)['graph_roles'][0]]
                    provider={**provider,'stack_id':source['stack'],'base_layer_id':source['base_layer'],
                              'initial_root':initial['initial_root'],'branch_id':initial['branch_id'],
                              'final_head_commit_id':initial['final_head'],'final_head_root':initial['final_root'],
                              'topology_acknowledgements':len(tuples),'topology_distinct_commits':len({item['commit_id'] for item in tuples}),
                              'topology_branches':len(graph['branches'])}
                    oracle._topology_transcript(custody['transcript'],tuples,provider)
                    return {'status':'PASS'}
                with patch.object(workspace.receipts,'command',side_effect=command),patch.object(workspace.oracle,'prepare_closed_store',side_effect=normalize),\
                     patch.object(workspace.oracle,'graph_commit_census',side_effect=typed_census) as census:
                    if fault:
                        with self.assertRaises(ValueError):workspace.access_graph_proof(case,prepared,graph,runtime,row,build,root,commands,time.monotonic()+5)
                        census.assert_not_called()
                    else:
                        result=workspace.access_graph_proof(case,prepared,graph,runtime,row,build,root,commands,time.monotonic()+5)
                        self.assertEqual(result['read_passes']['full_read_bytes'],2*sum(item['bytes'] for item in case['historical_access']['reads']));census.assert_called_once()
                        args=census.call_args.args;self.assertEqual(len(args),4)
                        self.assertEqual(len(args[1]),fixtures.historical_plan(case)['acknowledgements']);self.assertTrue(str(args[0]).endswith('/census-store/store.sqlite'))
                        self.assertEqual(args[3]['custody'],'KNOWN_STOP')
                        self.assertNotEqual(str(args[0]),str(root/'typed-store/store.sqlite'))


if __name__=='__main__':unittest.main()
