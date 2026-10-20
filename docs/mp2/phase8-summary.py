#!/usr/bin/env python3
"""Recompute Phase 8 results from retained receipts; never executes a sample."""
import hashlib,json,pathlib,statistics as st,re
root=pathlib.Path(__file__).resolve().parent/'receipts/run08'
def rows(name):return [json.loads(s) for s in (root/name/'results.jsonl').read_text().splitlines()]
def summary(name,case,arm):
    selected=[x for x in rows(name) if x.get('case')==case and x['arm']==arm]
    assert len(selected)==10
    assert all(x['result']['exit']==0 and x['store']['roundTrips']==0 for x in selected)
    ns=[json.loads(x['result']['output'])['ns']/1e9 for x in selected]
    work=[x['fuse']['completed'] for x in selected]
    return dict(median=st.median(ns),min=min(ns),max=max(ns),requests=0,fuse_min=min(work),fuse_max=max(work))
result={'receive':{},'cold':[]}
for case in ['status','find','stat','small','large']:
    original='hot-stat' if case=='stat' else 'hot'
    a,b=summary(original,case,'before'),summary(original,case,'after')
    c,d=summary('hot-fixed',case,'before'),summary('hot-fixed',case,'fixed')
    result['receive'][case]=dict(original_before=a,original_after=b,original_delta=100*(b['median']/a['median']-1),fixed_control=c,fixed=d,fixed_delta=100*(d['median']/c['median']-1))
invalid=[x for x in rows('hot') if x.get('case')=='stat']
assert len(invalid)==20 and sum(x['fuse']['completed']==0 for x in invalid)==19
assert max(x['fuse']['completed'] for x in invalid)==60
result['receive_limit']='Correction-cohort baseline stat sample1 has11227 FUSE calls; all other stat samples4869. Raw10-run medians retained; not a strict equal-request-rate qualification.'
for x in rows('cold'):
    if x.get('kind')=='unmount':assert x['result']['exit']==0;continue
    assert x['status']['exit']==0 and not x['status']['output']
    result['cold'].append(dict(variant=x['variant'],delay=x['delay'],mount=x['mount']['ns']/1e9,status=x['status']['ns']/1e9,mount_requests=x['mount_requests'],status_requests=x['status_requests'],cache=x['cache']))
result['ownership']=[dict(case=x['case'],exit=x['result']['exit'],owners=sorted({(f['uid'],f['gid']) for f in x['files']})) for x in rows('ownership') if 'case' in x]
assert len(result['ownership'])==12
for x in result['ownership']:
    expected={'cp':1,'tar':2,'rsync':23}[x['case'].split('-')[0]] if x['case'].endswith('user0-owner0') else 0
    assert x['exit']==expected and x['owners']==[(1000,1000)]
oracle=next(x for x in rows('ctime') if x.get('kind')=='oracle')
e=json.loads(oracle['evidence']['output']);assert e['before']==e['after'] and e['before_sha']!=e['after_sha']
assert oracle['status']['output']=='' and oracle['forced']['output']!=oracle['index']['output']
result['ctime']=dict(evidence=e,detected=False,index=oracle['index']['output'].strip(),actual=oracle['forced']['output'].strip())
cycles=rows('cycles-fixed');assert len(cycles)==41
for x in cycles:
    assert x['commit']['exit']==0 and x['unmount']['exit']==0 and not x['retained_join']
    trace=x['umount_trace']
    calls=re.findall(r'(\d+)\s+umount2\("/workspaces/1", 0[) ]',trace);assert len(calls)==1
    assert re.search(r'umount2\("/workspaces/1", 0\)\s+= 0',trace) or re.search(calls[0]+r'\s+<\.\.\. umount2 resumed>\)\s+= 0',trace)
    tasks=json.loads(x['remaining'])
    assert not any('fuser' in t or 'layerfs-mount' in t or 'layerfs-fence' in t for t in tasks.values())
held=rows('held-fixed')[0];assert held['unmount']['exit']!=0 and 'Busy' in held['unmount']['output'] and 'EBUSY' in held['umount_trace']
facts=json.loads((root/'held-fixed/held-01/processes.json').read_text())
namespaces=json.loads((root/'held-fixed/held-01/namespaces.json').read_text())
assert any('/workspaces/1/local' in v['target'] for p in facts['processes'].values() for v in p['fds'].values())
assert any(' - fuse layerfs ' in n['mountinfo'] for n in namespaces.values())
loops=[t for p in facts['processes'].values() for t in p['threads'].values() if t['comm'].startswith('fuser')]
assert len(loops)==2 and all('epoll_pwait' in t['wchan'] for t in loops)
result['custody']=dict(git=40,git_retained=0,plain=1,plain_retained=0,held='Refused(Busy)/EBUSY')
print(json.dumps(result,indent=2))
