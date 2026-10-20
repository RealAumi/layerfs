#!/usr/bin/env python3
"""Aggregate the matched refreshed-root cohorts and exact Store request classes."""
import pathlib,json,gzip,re,collections,statistics
root=pathlib.Path(__file__).parent/'receipts/run06/phase6'
def read(p):
    p=root/p
    return p.read_text() if p.exists() else gzip.open(str(p)+'.gz','rt').read()
def rows(p):return [json.loads(l) for l in read(p).splitlines()]
def spread(v):return dict(median=statistics.median(v),min=min(v),max=max(v))
def accesses(p):
    paths=set()
    for l in read(p).splitlines():
        m=re.search(r'(?:read|pread64)\(\d+</workspaces/\d+/([^>]+)>.* = (\d+)$',l)
        if m and int(m[2])>0:paths.add(m[1])
        m=re.search(r'mmap\(.*\d+</workspaces/\d+/([^>]+)>.* = 0x',l)
        if m:paths.add(m[1])
    return sorted(p for p in paths if not p.startswith('.git/'))
summary={'cohorts':[],'oracles':{},'device_probe':accesses('warm/device-status.trace')}
for arm in ['before','after']:
    summary['oracles'][arm]=[r for r in rows('oracles-'+arm+'/results.jsonl') if r['kind']=='oracle']
    for delay in [0,2,20]:
        p=f'measure-{arm}-{delay}/';results=[r for r in rows(p+'results.jsonl') if r['kind']=='measure'];assert len(results)==3
        roles={i.lower():k for i,k in json.loads(read(p+'roles.json'))};classes=[];files=[];pings=[]
        for r in results:
            c=collections.Counter();files.append(accesses(p+f'status-{r["rep"]}.trace'))
            for l in read(p+f'requests-{r["rep"]}.log').splitlines():
                if l.startswith('STORE_METADATA'):c['metadata_batch']+=1
                elif l.startswith('STORE_READ'):
                    op=int(re.search(r'opcode=(\d+)',l)[1]);ids=re.findall(r'ObjectId\("([a-f0-9]+)"\)',l)
                    c['length' if op==3 else '+'.join(sorted(set('content' if roles[i]<=5 else 'metadata' for i in ids)))]+=1
            c['other']=r['mount_requests']+r['status_requests']-sum(c.values());classes.append(c)
        for r in rows(p+'commands.jsonl'):
            if 'ping' in r['command']:pings.extend(map(float,re.findall(r'time=([\d.]+) ms',r['output'])))
        keys=set().union(*classes)
        summary['cohorts'].append(dict(arm=arm,rtt=delay,wall_s=spread([(r['mount']['ns']+r['status']['ns'])/1e9 for r in results]),mount_s=spread([r['mount']['ns']/1e9 for r in results]),requests=spread([r['mount_requests']+r['status_requests'] for r in results]),classes={k:spread([c[k] for c in classes]) for k in sorted(keys)},working_files=files,ping_ms=spread(pings),exits=[r['status']['exit'] for r in results]))
summary['steady']=[r for r in rows('steady/results.jsonl') if r['kind']=='oracle'][0]
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
for r in summary['cohorts']:print(r['arm'],r['rtt'],r['wall_s'],r['requests'],r['classes'])
