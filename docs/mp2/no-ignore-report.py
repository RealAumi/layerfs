#!/usr/bin/env python3
"""Derive tables from immutable noignore01 receipts; never fill missing metrics."""
import json
import pathlib
import re

HERE=pathlib.Path(__file__).resolve().parent
R=HERE/'receipts/noignore01/attempt2'
E=[json.loads(line) for line in (R/'events.jsonl').read_text().splitlines()]
W={x['label']:x for x in E if x['kind']=='workload'}
C={x['label']:x for x in E if x['kind']=='measured_commit'}
ROWS=[]


def db(snapshot):return snapshot['store']['logical_database_bytes']
def rx(snapshot):
    return snapshot.get('transport',snapshot)['from_store_bytes']
def sec(ns):return f'{ns/1e9:.3f}'
def num(n):return '—' if n is None else f'{n:,}'
def row(repo,scenario,mode,time,upload=None,fetch=None,growth=None,note='',labels=(),status='PASS'):
    ROWS.append(dict(repo=repo,scenario=scenario,mode=mode,time=time,uploaded_bytes=upload,fetched_wire_bytes=fetch,store_growth_bytes=growth,note=note,evidence_labels=list(labels),status=status,sample_count=1 if status!='NOT_RUN' else 0))


def phase(repo,scenario,mode,first_label,commit_label,build_label=None):
    first=W.get(first_label);c=C.get(commit_label)
    if not first or not c:
        row(repo,scenario,mode,'NOT_RUN',note='Missing completed selection',status='NOT_RUN');return
    build=W.get(build_label) if build_label else first
    time='work '+sec(build['wall_ns'])+'; Commit '+sec(c['product_wall_ns'])
    row(repo,scenario,mode,time,c['uploaded_bytes'],rx(c['after'])-rx(first['before']),db(c['after'])-db(first['before']),labels=[first_label,commit_label]+([build_label] if build_label else []))


def tests(repo,prefix,mode):
    for kind,scenario in [('fresh_test','S2 cold mount + test'),('resume','S6 mount → tests finish')]:
        found=next((x for x in E if x['kind']==kind and x['label']==prefix+('-S2' if kind=='fresh_test' else '-S6')),None)
        if not found:
            row(repo,scenario,mode,'NOT_RUN',status='NOT_RUN');continue
        failed=found['exit']!=0
        row(repo,scenario,mode,sec(found['wall_ns'])+(' FAIL' if failed else ''),0,rx(found['after'])-rx(found['before']),db(found['after'])-db(found['before']),
            note='Failed test; not time to pass' if failed else ('Recovery includes reinstall/rebuild' if mode=='on' and kind=='resume' else 'No reinstall'),labels=[found['label']],status='FAIL' if failed else 'PASS')


def main_rows(repo,prefix,mode):
    tests(repo,prefix,mode)
    for i in range(1,11):
        stem=prefix+f'-S3-{i:02}'
        phase(repo,f'S3 edit {i:02}',mode,stem+'-edit',stem+('-commit' if repo=='Node' else '-repo-commit'),stem+'-incremental')
    stem=prefix+'-S4'
    phase(repo,'S4 clean build',mode,stem+'-clean-build',stem+('-commit' if repo=='Node' else '-repo-commit'))
    stem=prefix+'-S5'
    phase(repo,'S5 dependency change',mode,stem+('-add' if repo=='Node' else '-jar-absent'),stem+('-commit' if repo=='Node' else '-repo-commit'),stem+('-add' if repo=='Node' else '-download-build'))


def merges(repo,prefix):
    for side in ['left','right']:
        stem=prefix+'-S7-'+side
        phase(repo,'S7 rebuild '+side,'off',stem+'-edit',stem+'-commit',stem+'-build')
    item=next((x for x in E if x['kind']=='generated_merge' and x['label']==prefix+'-S7'),None)
    if item:
        reply=item['reply'];ns=int(re.search(r'wall_ns=(\d+)',reply)[1])
        decisions=len(re.findall(r'\("kept", Text\(',reply))
        right=C[prefix+'-S7-right-commit']
        following=next(x for x in E if x['kind']=='fork' and x['label']==prefix+'-S7-source-left-fork')
        growth=following['before']['logical_database_bytes']-db(right['after'])
        row(repo,'S7 generated merge','off','SDK '+sec(ns),None,None,growth,note=f'{decisions} LWW decisions; no conflicts. Growth interval includes preceding unmount; SDK is Store-local.',labels=[item['label']])
    for side in ['left','right']:
        stem=prefix+'-S7-source-'+side
        phase(repo,'S7 source-control '+side,'off',stem+'-edit',stem+'-commit')
    item=next((x for x in E if x['kind']=='source_conflict_control' and x['label']==prefix+'-S7-source'),None)
    if item:
        row(repo,'S7 source conflict','off','SDK '+sec(int(re.search(r'wall_ns=(\d+)',item['reply'])[1])),None,None,None,note='Expected Conflict; no merge Commit',labels=[item['label']],status='EXPECTED_CONFLICT' if item['expected_conflict'] else 'FAIL')


initial=next(x for x in E if x['kind']=='warm_base' and x['label']=='v2-vite')
revised=next(x for x in E if x['kind']=='revised_warm_base')
row('Node','S1 shared warm base','off builder',
    'clone '+sec(W['v2-vite-clone']['wall_ns'])+'; install '+sec(W['v2-vite-install']['wall_ns'])+'; builds '+sec(W['v2-vite-build']['wall_ns'])+' + '+sec(W['v2-vite-fullbase-build']['wall_ns'])+'; Commits '+sec(C['v2-vite-base-commit']['product_wall_ns'])+' + '+sec(C['v2-vite-fullbase-commit']['product_wall_ns']),
    C['v2-vite-base-commit']['uploaded_bytes']+C['v2-vite-fullbase-commit']['uploaded_bytes'],
    rx(initial['after'])-rx(initial['before'])+rx(revised['after'])-rx(revised['before']),db(revised['after'])-db(initial['before']),
    note='Initial partial build/Node 22 cold test failed; full build revised on Node 20, reusing installed base. Final '+num(revised['inventory']['files'])+' files / '+num(revised['inventory']['bytes'])+' B.',labels=['v2-vite','v2-vite-fullbase'])
for arm in ['off','on']:main_rows('Node','v2-vite-'+arm+'3',arm)
merges('Node','v2-vite-off3')
base=next(x for x in E if x['kind']=='warm_base' and x['label']=='v2-maven-a')
row('Maven','S1 / S8a shared warm base','off builder','clone '+sec(W['v2-maven-a-clone']['wall_ns'])+'; install '+sec(W['v2-maven-a-install']['wall_ns'])+'; build/test '+sec(W['v2-maven-a-build']['wall_ns'])+'; Commit '+sec(C['v2-maven-a-base-repo-commit']['product_wall_ns']),
    C['v2-maven-a-base-repo-commit']['uploaded_bytes'],rx(base['after'])-rx(base['before']),db(base['after'])-db(base['before']),
    note=num(base['inventory']['files'])+' repo files / '+num(base['inventory']['bytes'])+' B; .m2 on separate shared volume.',labels=['v2-maven-a'])
for arm in ['off','on']:main_rows('Maven','v2-maven-a-'+arm,arm)
merges('Maven','v2-maven-a-off')
row('Maven','S8b repo-local .m2','off','install '+sec(W['v2-maven-b-install']['wall_ns'])+'; build '+sec(W['v2-maven-b-build']['wall_ns'])+' FAIL',0,None,None,note='3,757 NoHTTP violations in downloaded POMs; no warm-base Commit or cold sample',labels=['v2-maven-b-install','v2-maven-b-build'],status='FAIL')
cache_base=next((x for x in E if x['kind']=='warm_base' and x['label']=='v2-maven-c'),None)
if cache_base:
    cache=C['v2-maven-c-base-cache-commit'];repo=C['v2-maven-c-base-repo-commit']
    row('Maven','S8c base, two Workspaces','off','install '+sec(W['v2-maven-c-install']['wall_ns'])+'; build/test '+sec(W['v2-maven-c-build']['wall_ns'])+'; cache Commit '+sec(cache['product_wall_ns'])+'; repo Commit '+sec(repo['product_wall_ns']),cache['uploaded_bytes']+repo['uploaded_bytes'],rx(cache_base['after'])-rx(cache_base['before']),db(cache_base['after'])-db(cache_base['before']),note='One daemon; '+num(cache_base['cache_inventory']['files'])+' cache files / '+num(cache_base['cache_inventory']['bytes'])+' B.',labels=['v2-maven-c'])
    tests('Maven','v2-maven-c-off','off')
    for item in E:
        if item['kind']=='fork' and item['label'] in ['v2-maven-c-off-repo-fork','v2-maven-c-off-cache-fork']:
            row('Maven','S8c '+item['branch']+' fork','off',sec(item['command_wall_ns']),0,None,item['after']['logical_database_bytes']-item['before']['logical_database_bytes'],note='Independent writable Branch; metadata-only fork',labels=[item['label']])
    if 'v2-maven-c-off-S5-repo-commit' in C:
        first=W['v2-maven-c-off-S5-jar-absent'];last=C['v2-maven-c-off-S5-repo-commit'];cc=C['v2-maven-c-off-S5-cache-commit'];build=W['v2-maven-c-off-S5-download-build']
        row('Maven','S8c S5 complete change','off','work '+sec(build['wall_ns'])+'; Commits '+sec(cc['product_wall_ns']+last['product_wall_ns']),cc['uploaded_bytes']+last['uploaded_bytes'],rx(last['after'])-rx(first['before']),db(last['after'])-db(first['before']),note='Total row; following rows split the two explicit Commits',labels=['v2-maven-c-off-S5'])
    for kind in ['cache','repo']:
        label='v2-maven-c-off-S5-'+kind+'-commit'
        c=C.get(label)
        if c:row('Maven','S8c S5 '+kind+' Commit','off',sec(c['product_wall_ns']),c['uploaded_bytes'],c['fetched_wire_bytes'],c['store_growth_bytes'],note='ZXing core 3.5.3; cache fork never merged back',labels=[label])
else:row('Maven','S8c base/fresh fork/S5','off','NOT_RUN',status='NOT_RUN')

# S8c does not select S6: eliminate the placeholder generated by tests().
ROWS=[x for x in ROWS if not (x['repo']=='Maven' and x['scenario']=='S6 mount → tests finish' and x['status']=='NOT_RUN')]
for x in ROWS:
    if x['evidence_labels']==['v2-maven-c-off-S2']:x['scenario']='S8c cold repo + cache forks'
with (R/'derived-metrics.json').open('x') as stream: stream.write(json.dumps(ROWS,indent=2)+'\n')
parts=[]
for repo in ['Node','Maven']:
    parts += ['## '+repo+' results','', 'All measured cells are **single samples**. Bytes are exact. Times are seconds.','', '| Scenario | Mode | Time (s) | Uploaded B | Fetched B | Store growth B | Notes |','| --- | --- | --- | ---: | ---: | ---: | --- |']
    for x in ROWS:
        if x['repo']==repo:parts.append('| '+ ' | '.join([x['scenario'],x['mode'],x['time'],num(x['uploaded_bytes']),num(x['fetched_wire_bytes']),num(x['store_growth_bytes']),x['note']])+' |')
    parts.append('')
with (R/'tables.md').open('x') as stream: stream.write('\n'.join(parts)+'\n')
print('derived rows',len(ROWS))
