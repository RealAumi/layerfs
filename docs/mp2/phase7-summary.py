#!/usr/bin/env python3
"""Recompute rates and evidence invariants, without running another treatment."""
import pathlib,json,gzip,re,statistics
root=pathlib.Path(__file__).parent/'receipts/run07'
def text(p):return p.read_text() if p.exists() else gzip.open(str(p)+'.gz','rt').read()
summary={}
for arm in ['before','after']:
    folder=root/('cycles-'+arm)
    rows=[json.loads(l) for l in text(folder/'results.jsonl').splitlines()]
    git=[r for r in rows if r['shape']=='git'];plain=[r for r in rows if r['shape']=='plain'];assert len(git)==40 and len(plain)==1
    failures=[]
    for r in rows:
        assert 'error' not in r and r['commit']['exit']==0,r
        assert len(re.findall(r' umount2\("/workspaces/1", 0[) ]',r['umount_trace']))==1
        if r['retained_join']:
            p=folder/r['case'];facts=json.loads(text(p/'processes.json'));namespaces=json.loads(text(p/'namespaces.json'))
            loops=[t for proc in facts['processes'].values() for t in proc['threads'].values() if t['comm'].startswith('fuser')]
            mounts=[l for n in namespaces.values() for l in n['mountinfo'].splitlines() if ' - fuse layerfs ' in l]
            holders=[dict(pid=pid,kind=k,path=proc[k]) for pid,proc in facts['processes'].items() for k in ['cwd','root'] if '/workspaces/' in proc[k]]
            holders += [dict(pid=pid,kind=fd,path=v['target']) for pid,proc in facts['processes'].items() for fd,v in proc['fds'].items() if '/workspaces/' in v['target']]
            assert len(loops)==2 and all('fuse_dev_do_read' in t['stack'] for t in loops)
            assert facts['waiting'] and all(v=='0\n' for v in facts['waiting'].values())
            assert not mounts and not holders
            failures.append(dict(case=r['case'],waiting=facts['waiting'],namespaces=len(namespaces),fuser_loops=len(loops),holders=holders,mounts=mounts))
        else:
            assert r['unmount']['exit']==0,r
            tasks=json.loads(r['remaining']);assert not any('fuser' in t or 'layerfs-mount' in t or 'layerfs-fence' in t for t in tasks.values()),tasks
    count=sum(r['retained_join'] for r in git)
    summary[arm]=dict(git=dict(cycles=40,retained_join=count,rate=count/40,success=40-count),plain=dict(cycles=1,retained_join=plain[0]['retained_join']),failures=failures)
held=[json.loads(l) for l in text(root/'held-after/results.jsonl').splitlines()];assert len(held)==1
summary['held']=held[0];assert held[0]['unmount']['exit']!=0 and 'Busy' in held[0]['unmount']['output'] and 'EBUSY' in held[0]['umount_trace']
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
for arm in ['before','after']:print(arm,summary[arm]['git'],summary[arm]['plain'])
print('held:',held[0]['unmount']['output'])
