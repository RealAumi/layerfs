#!/usr/bin/env python3
"""Scoped receipt/claim checks only; no product tests or workload replay."""
import ast
import gzip
import hashlib
import json
import pathlib
import re

HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[1]
R=HERE/'receipts/noignore01/attempt2'

def read(name):
    p=R/name
    return p.read_text() if p.exists() else gzip.decompress(p.with_suffix(p.suffix+'.gz').read_bytes()).decode()

E=[json.loads(line) for line in (R/'events.jsonl').read_text().splitlines()]
commits=[x for x in E if x['kind']=='measured_commit']
assert len(commits)==63
assert len({x['label'] for x in commits})==63
for prefix in ['v2-vite-off3','v2-vite-on3','v2-maven-a-off','v2-maven-a-on']:
    selected=[x for x in commits if x['label'].startswith(prefix+'-S3-')]
    assert len(selected)==10
    assert {int(re.search(r'-S3-(\d+)',x['label'])[1]) for x in selected}==set(range(1,11))
for x in commits:
    assert x['uploaded_bytes']==x['after']['stats']['uploadedBytes']-x['before']['stats']['uploadedBytes']
    assert x['store_growth_bytes']==x['after']['store']['logical_database_bytes']-x['before']['store']['logical_database_bytes']
    assert x['product_wall_ns']>0 and x['uploaded_bytes']>=0
for prefix in ['v2-vite-off3','v2-vite-on3','v2-maven-a-off','v2-maven-a-on','v2-maven-c-off']:
    x=next(x for x in E if x['kind']=='fresh_test' and x['label']==prefix+'-S2');assert x['exit']==0
for prefix,expected in [('v2-vite-off3',1),('v2-vite-on3',1),('v2-maven-a-off',0),('v2-maven-a-on',0)]:
    x=next(x for x in E if x['kind']=='resume' and x['label']==prefix+'-S6');assert x['exit']==expected
for prefix,count in [('v2-vite-off3',3),('v2-maven-a-off',4)]:
    x=next(x for x in E if x['kind']=='generated_merge' and x['label']==prefix+'-S7')
    assert 'Text("Merged")' in x['reply'] and '("conflicts", List([]))' in x['reply']
    assert len(re.findall(r'\("kept", Text\(',x['reply']))==count
    assert '("lwwTruncated", Bool(false))' in x['reply']
    assert 'code: "Conflict"' in read(prefix+'-S7-source-conflict.log')
    assert 'nothing was created' in read(prefix+'-S7-source-conflict.log')
assert 'code: "NoSuchPath"' in read('v2-maven-c-off-cache-base-no-jar.log')
assert '("size", Int(607650))' in read('v2-maven-c-off-cache-fork-jar.log')
assert len([x for x in E if x['kind']=='multi_workspace'])==2
for name,sha in json.loads((R/'attempt1-seal.json').read_text()).items():
    assert hashlib.sha256((R.parent/name).read_bytes()).hexdigest()==sha,name
for x in E:
    if x['kind']=='command':assert (R/x['output']).exists() or (R/(x['output']+'.gz')).exists(),x['output']
report=HERE/'no-ignore.md'
for link in re.findall(r'\]\(([^)]+)\)',report.read_text()):
    if not link.startswith(('http:','https:')):assert (report.parent/link.split('#')[0]).exists(),link
scripts=sorted(HERE.glob('no-ignore*.py'))
for p in scripts:ast.parse(p.read_text())
rows=json.loads((R/'derived-metrics.json').read_text());assert len(rows)==78
hygiene=json.loads((R/'hygiene.json').read_text())
assert all(hygiene[k]==0 for k in ['home_path_matches','out_of_prefix_resource_names','internal_host_platform_matches'])
assert not any(json.loads((R/'cleanup-final.json').read_text())['remaining'].values())
result={'status':'PASS','scope':'receipt arithmetic/cardinality, expected failures, frozen attempt1, links, Python syntax and cleanup','workspace_commits':63,'successful_sdk_merge_commits':2,'edit_iterations':40,'final_cold_tests_passed':5,'resume_tests_passed':2,'resume_tests_failed_retained':2,'lww_decisions':{'node':3,'maven':4},'source_conflict_controls':2,'multi_workspace_observations':2,'cache_base_unchanged':True,'attempt1_files_unchanged':66,'table_rows':78,'harness_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in scripts},'new_product_tests_run':0,'performance_admission':False}
with (R/'validation-final.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in result.items() if k!='harness_sha256'},indent=2))
