#!/usr/bin/env python3
"""Recompute medians/ranges from immutable Phase-3 receipts; no product runs."""
import json, pathlib, re, statistics
root=pathlib.Path(__file__).parent/'receipts/run03/phase3'
def rows(path):
    return [json.loads(line) for line in (root/path).read_text().splitlines()]
def spread(values):
    assert len(values)==3, values
    return dict(median=statistics.median(values),minimum=min(values),maximum=max(values))
results=rows('measure-v3/results.jsonl')
summary={'commits':[],'rtt':[]}
conditions=[(False,0),(False,2),(False,20),(True,0)]
for native,delay in conditions:
    for kind in ['full','delta']:
        selected=[r for r in results if (r.get('native'),r.get('rtt'),r.get('kind'))==(native,delay,kind)]
        record=dict(native=native,rtt_ms=delay,kind=kind,wall_ns=spread([r['wall_ns'] for r in selected]))
        record['metrics']={k:spread([r['metrics'][k] for r in selected]) for k in selected[0]['metrics']}
        record['save_statistics']={k:spread([int(re.search(k+r': (\d+)',r['reply'])[1]) for r in selected]) for k in ['new_canonical','new_stored','new_metadata']}
        summary['commits'].append(record)
        t=record['wall_ns'];print(native,delay,kind, *(round(t[k]/1e9,6) for k in ['median','minimum','maximum']))
case=-1;pings={}; packets={}
for r in rows('measure-v3/commands.jsonl'):
    cmd=r['command']
    if cmd[1:]==['network','create','--internal','mp2-p3-a-net']:case+=1
    if 'ping' in cmd:
        matched=re.search(r'rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/',r['output'])
        assert matched,r
        packets[case]=list(map(float,re.findall(r'time=([\d.]+) ms',r['output'])))
        pings[case]=list(map(float,matched.groups())) # last probe: 20 ms follows preparation
assert case==11
for i,(native,delay) in enumerate(conditions):
    probes=[pings[i*3+j] for j in range(3)]
    summary['rtt'].append(dict(native=native,configured_ms=delay,packet_median_ms=statistics.median([t for j in range(3) for t in packets[i*3+j]]),mean_ms=spread([p[1] for p in probes]),min_ms=min(p[0] for p in probes),max_ms=max(p[2] for p in probes)))
cold=[r for r in results if r.get('kind')=='cold-mount-status' and r['rtt']==2]
summary['cold_2ms']={k:spread([r[k] for r in cold]) for k in ['mount_requests','git_requests']}
for k in ['mount','git']:
    summary['cold_2ms'][k+'_command_ns']=spread([r[k]['ns'] for r in cold])
summary['cold_2ms']['combined_command_ns']=spread([r['mount']['ns']+r['git']['ns'] for r in cold])
cycles=[r for r in rows('cycles/results.jsonl') if 'cycle' in r]
assert len(cycles)==10 and all(r['state']==cycles[0]['state'] for r in cycles)
unmount=[int(re.search(r'wall_ns=(\d+)',r['unmount']['output'])[1]) for r in cycles]
summary['cycles']=dict(count=10,threads=cycles[0]['state']['threads'],unmount_min_ns=min(unmount),unmount_max_ns=max(unmount),unmount_median_ns=statistics.median(unmount),stopped=rows('cycles/results.jsonl')[-1]['stopped'])
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
