#!/usr/bin/env python3
"""Recompute Phase 5 diagnostic counts without running the product."""
import collections,gzip,json,pathlib,re,statistics
root=pathlib.Path(__file__).parent/'receipts/run05'
def read(name):
    p=root/name
    return p.read_text() if p.exists() else gzip.open(str(p)+'.gz','rt').read()
def rows(name):return [json.loads(l) for l in read(name).splitlines()]
def spread(values):return dict(median=statistics.median(values),min=min(values),max=max(values))
def accesses(name):
    reads=collections.Counter();mapped=set()
    for line in read(name).splitlines():
        m=re.search(r'(?:read|pread64)\(\d+</workspaces/\d+/([^>]+)>.* = (\d+)$',line)
        if m and int(m[2])>0:reads[m[1]]+=int(m[2])
        m=re.search(r'mmap\(.*\d+</workspaces/\d+/([^>]+)>.* = 0x',line)
        if m:mapped.add(m[1])
    paths=set(reads)|mapped;working=sorted(p for p in paths if not p.startswith('.git/'))
    return dict(working_files=len(working),working_paths=working,read_bytes=dict(reads),mapped_paths=sorted(mapped))
summary={'stability':{},'diagnosis':{},'minimal':[],'oracles':[]}
st=rows('stability/results.jsonl')[0];summary['stability']=dict(paths=len(st['first']),changed=st['changed'],readme_first=st['first']['README.md'],readme_second=st['second']['README.md'])
roles={i.lower():role for i,role in json.loads(read('diagnose/roles.json'))};counts=collections.Counter()
mount_lines=len(read('diagnose/mount.log').splitlines())
for l in read('diagnose/requests.log').splitlines()[mount_lines:]:
    if not l.startswith('STORE_READ'):continue
    op=int(re.search(r'opcode=(\d+)',l)[1]);ids=re.findall(r'ObjectId\("([a-f0-9]+)"\)',l)
    kind='length' if op==3 else '+'.join(sorted(set('content' if roles[i]<=5 else 'metadata' for i in ids)));counts[kind]+=1
summary['diagnosis']=dict(requests=dict(counts),access=accesses('diagnose/status.trace'))
for delay in [0,2,20]:
    if not (root/f'measure-{delay}').exists():continue
    selected=rows(f'measure-{delay}/results.jsonl');assert len(selected)==3
    a=[accesses(f'measure-{delay}/status-{r["rep"]}.trace') for r in selected]
    packets=[]
    for cmd in rows(f'measure-{delay}/commands.jsonl'):
        if 'ping' in cmd['command']:packets.extend(map(float,re.findall(r'time=([\d.]+) ms',cmd['output'])))
    summary['minimal'].append(dict(rtt=delay,complete=all(r['status']['exit']==0 for r in selected),wall_s=spread([(r['mount']['ns']+r['status']['ns'])/1e9 for r in selected]),requests=spread([r['mount_requests']+r['status_requests'] for r in selected]),working_files=spread([x['working_files'] for x in a]),accesses=a,ping_ms=spread(packets)))
for r in rows('oracles/results.jsonl'):
    assert r['forced_hash']!=r['index_hash'],r
    summary['oracles'].append(dict(case=r['case'],reported=r['reported'],status=r['status']['output'],forced_hash=r['forced_hash'],index_hash=r['index_hash'],evidence=r['evidence']['output'],access=accesses('oracles/'+r['case']+'.trace')))
assert sum(counts.values())==rows('diagnose/results.jsonl')[0]['requests']
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k not in ['oracles','diagnosis']},indent=2))
