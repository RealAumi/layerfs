"""Original checkpoint/observation/deadline boundaries before mounted attempts."""
import copy
from contextlib import ExitStack
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

BENCH=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(BENCH))
from engine import workspace


def cases(family):
    return json.loads((BENCH/'families'/family/'family.json').read_text())['cases']


def acknowledged(case):
    records=[];previous='-'
    for index in range(1,case['history_schedule']['commits']+1):
        current='12'+f'{index:064x}'
        records.append({'index':index,'commit':{'fields':{'commit_id':current,'parent':previous,'root':'a'*64}}})
        previous=current
    return {'initial_root':'a'*64,'commits':records}


class HistoryController(unittest.TestCase):
    def test_helper_refusal_precedes_case_claim_and_any_clone_or_mount(self):
        case=cases('file_size_transition')[0]
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();output=root/'case'
            prepared={'fixture':{'fixture_sha256':'fixture'},'helpers':{'files':{}}}
            build={'binaries':{name:{'path':'/'+name,'sha256':name} for name in ('runtime','daemon')}}
            with patch.object(workspace.identity,'ROOT',root), \
                    patch.object(workspace.identity,'source_identity',return_value={'source_commit':'a'*40,'product_tree':'b'*40}), \
                    patch.object(workspace.identity,'load_build',return_value=build), \
                    patch.object(workspace.fixtures,'load',return_value=prepared), \
                    patch.object(workspace.fixtures,'validate_runtime_helpers',side_effect=ValueError('prepared SDK step/native fallback refused')) as admission, \
                    patch.object(workspace.fixtures,'clone',side_effect=AssertionError('no clone permitted')) as clone, \
                    patch.object(workspace.cell_runner,'EventProcess',side_effect=AssertionError('no process permitted')) as process:
                with self.assertRaisesRegex(ValueError,'native fallback refused'):
                    workspace.one_family_case('file_size_transition',case,'prepared','build',output)
                self.assertEqual(admission.call_count,1)
                clone.assert_not_called();process.assert_not_called()
            self.assertFalse(output.exists())
            self.assertFalse((root/'benchmark-results/fs-bench-pro/claims').exists())

    def test_sparse_workflow_uses_prepared_steps_and_separate_census_copy_before_publication(self):
        self.sparse_workflow()

    def test_closed_wal_acknowledgements_reach_typed_proof_and_census_copy(self):
        self.sparse_workflow(closed_wal=True)

    def sparse_workflow(self, closed_wal=False):
        case=next(c for c in cases('dedup_branch_history') if c['id']=='dedup-history-distributed-100')
        selected=case['history_schedule']['verification_steps']
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();output=root/'case';observed=[];commands=[]
            fixture_manifest=root/'manifest';fixture_manifest.write_bytes(b'isolated fixture manifest')
            prepared={'fixture':{'fixture_sha256':'fixture'},'helpers':{'files':{}},'source_uid':1,'source_gid':1,
                      'provision':{'manifest':str(fixture_manifest)},
                      'history_states':[{'index':i,'manifest':f'/sealed/state-{i}.tsv'} for i in selected],
                      'prepared_step_runs':{str(i):f'history/steps/step-{i}.sh' for i in range(1,101)}}
            class Runtime:
                container='a'*64
                selector=raw=stderr=None
                process=SimpleNamespace(stdin=None,stdout=None,wait=lambda **kw:0)
                rows=[{'event':'history_initial_root','fields':{'root':'0'*64}}]
                commits=0
                def event(self,*args):return None
                def retain(self,error):return {'failure':str(error)}
                def send(self,operation,*args,**kw):
                    fields={'state':'Gone'}
                    if operation=='command':commands.append(Path(args[1]).read_text())
                    if operation=='commit':
                        self.commits+=1
                        fields={'commit_kind':'Committed','commit_id':'12'+f'{self.commits:064x}',
                                'parent':'-' if self.commits==1 else '12'+f'{self.commits-1:064x}',
                                'root':f'{self.commits:064x}','stack':'31'+'b'*32,'base_layer':'32'+'c'*64}
                    if operation=='verify':
                        observed.append(('native',Path(args[1]).read_text()))
                        path=root/'native.stdout';path.write_text('verification_status=pass\n')
                        fields={'stdout':str(path),'exit_code':'0'}
                    row={'event':'workspace_status' if operation=='snapshot' else operation,'fields':fields,
                         'span':{'duration_ns':1},'sequence':len(self.rows)}
                    self.rows.append(row);return row
            runtime=Runtime()
            build={'socket':'/socket','binaries':{name:{'path':'/'+name,'sha256':name} for name in ('runtime','daemon')}}
            def execute(argv,folder,label,seconds,**kw):
                observed.append((label,argv))
                stdout=root/(label+'.stdout');stdout.write_text('false\n')
                completion={'argv':argv,'status':'PASS','exit_code':0,'attempts':1}
                if label=='closed-store-export':
                    original=root/'source.sqlite'
                    connection=sqlite3.connect(original,timeout=0,isolation_level=None)
                    connection.execute('PRAGMA journal_mode=WAL')
                    connection.execute('PRAGMA synchronous=OFF')
                    connection.execute('PRAGMA wal_autocheckpoint=0')
                    connection.execute('CREATE TABLE acknowledged(step INTEGER PRIMARY KEY)')
                    connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                    connection.executemany('INSERT INTO acknowledged VALUES(?)',[(i,) for i in range(1,101)])
                    if not closed_wal:connection.close()
                    (output/'graph-store').mkdir()
                    for suffix in ('','-wal','-shm'):
                        source=Path(str(original)+suffix)
                        if source.exists():shutil.copy2(source,output/('graph-store/store.sqlite'+suffix))
                    if closed_wal:connection.close()
                    raw_inputs.update({path.name:path.read_bytes() for path in (output/'graph-store').iterdir()})
                    (output/'closed-store-export.completion.json').write_text(json.dumps(completion))
                    (output/'runtime.events.jsonl').write_text('isolated runtime events\n')
                if label=='independent-graph':
                    events=[{'event':'history_root_verified','fields':{'step':i,'root':f'{i:064x}'}} for i in selected]
                    events += [{'event':'workspace_verified','fields':{'root':f'{100:064x}'}},{'event':'finished'}]
                    (output/'graph.events.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in events))
                    typed=Path(argv[argv.index('--sealed')+1]);self.assertEqual(typed,output/'typed-store/store.sqlite')
                    with sqlite3.connect(typed.as_uri()+'?mode=ro&immutable=1',uri=True,timeout=0) as db:
                        self.assertEqual(db.execute('SELECT count(*) FROM acknowledged').fetchone(),(100,))
                    for name,data in raw_inputs.items():self.assertEqual((output/'graph-store'/name).read_bytes(),data)
                return {**completion,'stdout':str(stdout)}
            def census(path,tuples,provider,custody):
                observed.append(('census',tuples))
                with sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True,timeout=0) as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM acknowledged').fetchone(),(100,))
                self.assertEqual(Path(custody['local_source']),output/'graph-store/store.sqlite')
                self.assertEqual(len(tuples),100);self.assertEqual(tuples[0]['parent_commit_id'],None)
                self.assertEqual(tuples[-1]['commit_id'],'12'+f'{100:064x}')
                transcript=Path(custody['transcript']).read_text().splitlines()
                self.assertEqual(len(transcript),101);self.assertEqual(transcript[3].split('\t')[-1],'-')
                self.assertEqual(custody['container'],runtime.container)
                return {'status':'PASS','commit_count':100,'scope':'isolated census orchestration mock; not public/store qualification'}
            raw_inputs={}
            def counts(runtime,row,*args):row['cache']['status']='INELIGIBLE'
            with ExitStack() as stack:
                for module,name,options in (
                    (workspace.identity,'ROOT',{'new':root}),
                    (workspace.identity,'source_identity',{'return_value':{'source_commit':'d'*40,'product_tree':'e'*40}}),
                    (workspace.identity,'load_build',{'return_value':build}),
                    (workspace.fixtures,'load',{'return_value':prepared}),
                    # Assets are deliberately opaque in this choreography
                    # unit; real byte/seal admission is covered separately.
                    (workspace.fixtures,'validate_runtime_helpers',{'return_value':{'scope':'isolated choreography mock'}}),
                    (workspace.fixtures,'clone',{'return_value':{'volume':'layerfs-fsb-sample-'+'f'*16}}),
                    (workspace.fixtures,'stage',{'return_value':{}}),
                    (workspace.cell_runner,'EventProcess',{'return_value':runtime}),
                    (workspace,'history_container_profile',{'return_value':{}}),
                    (workspace,'ordinary_resource_guard',{'return_value':{}}),
                    (workspace,'terminal_cache_observation',{'return_value':([],{})}),
                    (workspace,'collect_family_observations',{'side_effect':counts}),
                    (workspace.receipts,'command',{'side_effect':execute}),
                    (workspace.oracle,'commit_census',{'side_effect':census}),
                ):stack.enter_context(patch.object(module,name,**options))
                row=workspace.one_family_case('dedup_branch_history',case,'prepared',root/'build',output)
            self.assertEqual(row['status'],'INELIGIBLE',row.get('original_failure'))
            self.assertEqual(row['proof_status'],'PASS')
            self.assertEqual(row['cleanup'],'Gone')
            self.assertEqual(len(commands),100)
            self.assertIn('/code/history/steps/step-1.sh',commands[0])
            self.assertIn('/code/history/steps/step-2.sh',commands[1])
            self.assertEqual(row['history']['verification_steps'],selected)
            self.assertTrue(row['resource_removal_pending'])
            self.assertEqual(row['publication_guard']['scope'],workspace.receipts.HISTORY_PUBLICATION_SCOPE)
            self.assertTrue(any(label=='native' and body.endswith(' 100') for label,body in observed))
            self.assertFalse(any(isinstance(argv,list) and 'rm' in argv for _,argv in observed))

    def test_original_work_cleanup_publication_and_owner_stops_are_separate(self):
        boundary=cases('file_size_transition')[0]
        dedup=cases('dedup_branch_history')[0]
        episodes=cases('mixed_load_bearing')[0]
        exhaustive=cases('mixed_load_bearing')[-1]
        with patch.object(workspace.time,'monotonic',return_value=100.):
            self.assertEqual(workspace.family_proof_deadlines(boundary),{'work':122.,'cleanup':125.,'publication':135.})
            for case in (dedup,episodes):
                self.assertEqual(workspace.family_proof_deadlines(case,3_000_000_000),{'work':138.,'cleanup':142.,'publication':156.})
            self.assertEqual(workspace.family_proof_deadlines(exhaustive,owner_stop=130.),{'work':127.,'cleanup':130.,'publication':130.})
            for field,value in [('verifier_ms',26000),('cleanup_reserve_ms',2000),('publication_guard_ms',0)]:
                altered=copy.deepcopy(boundary);altered['budget'][field]=value
                with self.assertRaises(ValueError):workspace.family_proof_deadlines(altered)
            for charged in (True,-1,None,'0'):
                with self.assertRaises(ValueError):workspace.family_proof_deadlines(boundary,charged)
        self.assertEqual(exhaustive['budget']['command_ms'],None)
        self.assertEqual(exhaustive['budget']['verifier_ms'],300000)

    def test_dedup_transcript_binds_all_commits_with_only_selected_payloads(self):
        case=next(c for c in cases('dedup_branch_history') if c['id']=='dedup-history-distributed-100')
        selected=case['history_schedule']['verification_steps']
        prepared={'history_states':[{'index':i,'manifest':f'/sealed/state-{i}.tsv'} for i in selected]}
        history=acknowledged(case)
        body,got=workspace.history_transcript(case,prepared,history)
        self.assertEqual(got,[0,1,2,49,50,99,100])
        lines=[line.split('\t') for line in body.splitlines()]
        self.assertEqual(len(lines),101)
        self.assertEqual(lines[3][-1],'-')
        self.assertEqual([int(row[0]) for row in lines if row[-1]!='-'],selected)
        self.assertEqual(len({row[3] for row in lines}),1)  # Original recurring roots need not be distinct.
        for mutation in ('missing','duplicate','parent','extra-manifest'):
            h,p=copy.deepcopy(history),copy.deepcopy(prepared)
            if mutation=='missing':h['commits'].pop(49)
            elif mutation=='duplicate':h['commits'][1]['commit']['fields']['commit_id']=h['commits'][0]['commit']['fields']['commit_id']
            elif mutation=='parent':h['commits'][1]['commit']['fields']['parent']='-'
            else:p['history_states'].append({'index':3,'manifest':'/unselected.tsv'})
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):workspace.history_transcript(case,p,h)

    def test_m1_transcript_has_genesis_and_all_acknowledgements_but_only_cycle_ends(self):
        case=cases('mixed_load_bearing')[-1];selected=case['history_schedule']['verification_steps']
        prepared={'history_states':[{'index':i,'manifest':f'/sealed/scope-{i}.tsv'} for i in selected]}
        body,got=workspace.history_transcript(case,prepared,acknowledged(case))
        rows=[line.split('\t') for line in body.splitlines()]
        self.assertEqual(got,list(range(5,101,5)))
        self.assertEqual(rows[0],['0','-','-','a'*64,'-'])
        self.assertEqual(len(rows),101)
        self.assertEqual([int(row[0]) for row in rows if row[-1]!='-'],got)
        boundary=cases('file_size_transition')[0]
        with self.assertRaises(ValueError):workspace.history_transcript(boundary,{'history_states':[{'index':2,'manifest':'/final.tsv'}]},acknowledged(boundary))

    def command(self,path,body,exit_code='0'):
        path.write_text(body)
        return {'fields':{'stdout':str(path),'exit_code':exit_code}}

    def test_m1_mode_custody_uses_only_successful_unique_helper_observations(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'stdout'
            command=self.command(path,'m1_created_directory_modes=scratch/d0:755,scratch/d1:750\n')
            initial=workspace.m1_created_modes(command,{})
            self.assertEqual(initial,{'scratch/d0':0o755,'scratch/d1':0o750})
            next_command=self.command(path,'m1_created_directory_modes=scratch/d0:750\n')
            self.assertEqual(workspace.m1_created_modes(next_command,initial),{'scratch/d0':0o750,'scratch/d1':0o750})
            for text in ('','m1_created_directory_modes=../escape:750\n','m1_created_directory_modes=scratch/d0:1755\n',
                         'm1_created_directory_modes=/absolute:750\n','m1_created_directory_modes=scratch/d0:750,scratch/d0:750\n',
                         'm1_created_directory_modes=\nm1_created_directory_modes=\n'):
                with self.subTest(text=text),self.assertRaises(ValueError):workspace.m1_created_modes(self.command(path,text),{})
            with self.assertRaises(ValueError):workspace.m1_created_modes(self.command(path,'m1_created_directory_modes=\n','1'),{})

    def test_selective_native_json_cannot_be_mistaken_for_generic_full_proof(self):
        case=next(c for c in cases('mixed_load_bearing') if c['id']=='v016-mixed-development-100mb-5000-k10-v1')
        proof={'case':case['id'],'seed':1,'step':10,'verification_status':'pass','scope':'original-m1-selective-scope-v1',
               'scope_digest':'a'*64,'created_modes_digest':'b'*64,'entries':5000,'checked_range_bytes':100}
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'stdout'
            got=workspace.verify_native_receipt(case,self.command(path,json.dumps(proof)+'\n'))
            self.assertEqual(got['status'],'PASS')
            for key,value in [('case','wrong'),('seed',True),('step',5),('scope','complete-file-bytes'),('created_modes_digest','x'*64),('entries',True),('checked_range_bytes',-1)]:
                changed={**proof,key:value}
                with self.subTest(key=key),self.assertRaises(ValueError):workspace.verify_native_receipt(case,self.command(path,json.dumps(changed)))
            with self.assertRaises(ValueError):workspace.verify_native_receipt(case,self.command(path,json.dumps(proof),'1'))
            duplicate=json.dumps(proof).replace('"seed": 1','"seed": 1, "seed": 1')
            with self.assertRaises(ValueError):workspace.verify_native_receipt(case,self.command(path,duplicate))


if __name__=='__main__':unittest.main()
