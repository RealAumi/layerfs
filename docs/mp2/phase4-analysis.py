#!/usr/bin/env python3
"""Derive request attribution and diagnostic summaries from retained receipts."""
import collections, gzip, json, pathlib, re, statistics
root=pathlib.Path(__file__).parent/'receipts/run04/phase4'
def read(p):
    p=root/p
    return p.read_text() if p.exists() else gzip.open(str(p)+'.gz','rt').read()
def rows(p):return [json.loads(l) for l in read(p).splitlines()]
def spread(v):return dict(median=statistics.median(v),min=min(v),max=max(v))
roles={i.lower():role for i,role,n in rows('diagnose/roles.jsonl')[0]}
owners=collections.defaultdict(set)
for l in read('receipts/request-paths02.log').splitlines():
    if l.startswith('OWNER\t'):
        _,i,p=l.split('\t');owners[i].add(p or '/')
counts=collections.Counter();object_counts=collections.Counter();bypath=collections.defaultdict(set);bygroup=collections.Counter();requests=[]
mount_lines=len(read('diagnose/mount-requests.log').splitlines())
for l in read('diagnose/all-requests.log').splitlines()[mount_lines:]:
    if not l.startswith('STORE_READ'):continue
    op=int(re.search(r'opcode=(\d+)',l)[1]);ids=re.findall(r'ObjectId\("([a-f0-9]+)"\)',l)
    kinds=set();paths=set()
    for i in ids:
        role=roles[i];k='length' if op==3 else ('whole-content' if role==1 else 'chunked-content' if role<=5 else 'metadata')
        kinds.add(k);object_counts[f'{op}:{role}']+=1
        paths.update(owners[i] if role not in [6,9,10] else ['<shared inode table/root>'])
        assert owners[i] or role in [6,9,10],i
    kind='+'.join(sorted(kinds));counts[kind]+=1
    groups={p.split('/')[0] if not p.startswith('<') else p for p in paths};group=next(iter(groups)) if len(groups)==1 else '<shared across top-level paths>'
    bygroup[(group,kind)]+=1
    ordinal=len(requests)+1
    for p in paths:bypath[p].add(ordinal)
    requests.append(dict(ordinal=ordinal,opcode=op,ids=ids,kind=kind,owners=sorted(paths)))
access=collections.defaultdict(collections.Counter)
for l in read('diagnose/git.strace').splitlines():
    m=re.search(r'read\(\d+</workspaces/1/([^>]+)>.* = (\d+)$',l)
    if m:access[m[1]]['read_calls']+=1;access[m[1]]['read_bytes']+=int(m[2])
    m=re.search(r'mmap\(.*\d+</workspaces/1/([^>]+)>',l)
    if m:access[m[1]]['mmap_calls']+=1
with gzip.open(root/'requests-by-path.jsonl.gz','wt') as f:
    for row in requests:f.write(json.dumps(row)+'\n')
with gzip.open(root/'path-totals.jsonl.gz','wt') as f:
    for p in sorted(set(bypath)|set(access)):f.write(json.dumps(dict(path=p,requests_touching=len(bypath[p]),**access[p]))+'\n')
summary=dict(requests=dict(counts),objects=dict(object_counts),top_level=[dict(path=p,kind=k,requests=n) for (p,k),n in sorted(bygroup.items())],git_read_paths=len([p for p,c in access.items() if c['read_bytes']>0]),git_mmap_paths=[p for p,c in access.items() if c['mmap_calls']])
summary['cold']=[];summary['node']=[]
for delay in [0,2,20]:
    if (root/f'cold-{delay}/results.jsonl').exists():
        selected=rows(f'cold-{delay}/results.jsonl');assert len(selected)==3
        summary['cold'].append(dict(rtt=delay,complete=all(r['git']['exit']==0 for r in selected),exits=[r['git']['exit'] for r in selected],observed_wall_s=spread([(r['mount']['ns']+r['git']['ns'])/1e9 for r in selected]),requests=spread([r['mount_requests']+r['git_requests'] for r in selected])))
for delay in [2,20]:
    if not (root/f'node-{delay}/results.jsonl').exists():continue
    for kind in ['full','delta']:
        selected=[r for r in rows(f'node-{delay}/results.jsonl') if r['kind']==kind];assert len(selected)==3
        summary['node'].append(dict(rtt=delay,kind=kind,wall_s=spread([r['wall_ns']/1e9 for r in selected]),metrics={k:spread([r['metrics'][k] for r in selected]) for k in selected[0]['metrics']},growth={k:spread([r['store_growth'][k] for r in selected]) for k in selected[0]['store_growth']}))
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k!='top_level'},indent=2))
