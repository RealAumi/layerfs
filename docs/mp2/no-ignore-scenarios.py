#!/usr/bin/env python3
"""Attempt-2 scenario orchestration; product failures stop, no replay."""
import importlib.util
import json
import pathlib
import re
import subprocess
import sys
import time

HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('v',HERE/'no-ignore-v2.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
h=v.h


def close_base(name):
    s=v.load(name)
    h.ctl(s,name+'-seal-unmount','unmount',s['workspace'],s['namespace'])
    h.docker(name+'-seal-server','stop','-t','10',s['server'])
    s['closed_base']=True;v.save(s)


def start_server(base,name,arm):
    assert base.get('closed_base'), 'clone requires closed base'
    s={'repo':name,'arm':arm,'kind':base['kind'],'server':'cxn-'+name+'-server','store':'cxn-'+name+'-store','network':base['network']}
    h.docker(name+'-store-volume','volume','create',s['store'])
    h.docker(name+'-store-clone','run','--rm','--name','cxn-clone','--network',s['network'],
      '-v',base['store']+':/source:ro','-v',s['store']+':/state',h.IMAGE,'bash','-c','set -e; cp -a /source/store /state/store; cp /source/server.setup /source/daemon.setup /state/; mkdir /state/server-overlay; chmod 700 /state',limit=60)
    h.docker(name+'-server-create','run','-d','--name',s['server'],'--network',s['network'],'--init',
      '-v','cxi-target:/cache:ro','-v',s['store']+':/state','-e','LAYERFS_CONSTRUCTION_WORKERS=1',h.IMAGE,'sleep','infinity')
    h.docker(name+'-server-start','exec',s['server'],'bash','-c','ln -s /cache/cxn-noignore01 /bins; /bins/'+arm+'/layerfs-store --config /state/server.setup > /state/server.log 2>&1 &')
    h.ready(s['server'],'/state/server.log','REMOTE_STORE_READY');v.save(s)
    return s


def client(s,label,extra_mounts=None):
    s=dict(s);s['daemon']='cxn-'+label;s['local']='cxn-'+label+'-local'
    h.docker(label+'-local-volume','volume','create',s['local'])
    extra='; printf "ignore=git\\n" >> /state/daemon.setup' if s['arm']=='on' else ''
    h.docker(label+'-config','run','--rm','--name','cxn-config','--network',s['network'],
      '-v',s['store']+':/source:ro','-v',s['local']+':/state',h.IMAGE,'bash','-c',
      'set -e; cp /source/daemon.setup /state/daemon.setup; chmod 700 /state; sed -i "s/^server=.*/server=127.0.0.1:7900/" /state/daemon.setup'+extra)
    h.docker(label+'-create','run','-d','--name',s['daemon'],'--network',s['network'],'--init',
      '--device','/dev/fuse','--cap-add','SYS_ADMIN','--security-opt','apparmor=unconfined',
      '-v','cxi-target:/cache:ro','-v',str(HERE)+':/harness:ro','-v',s['local']+':/state',
      *sum((['-v',mount] for mount in (extra_mounts or [])),[]),
      '-e','CXN_SERVER='+s['server'],'-e','LAYERFS_CONSTRUCTION_WORKERS=1',h.IMAGE,'sleep','infinity')
    h.docker(label+'-proxy-start','exec',s['daemon'],'bash','-c',
      'ln -s /cache/cxn-noignore01 /bins; python3 /harness/no-ignore-proxy.py > /state/proxy.log 2>&1 &')
    h.ready(s['daemon'],'/state/proxy.log','PROXY_READY')
    h.docker(label+'-daemon-start','exec',s['daemon'],'bash','-c',
      '/bins/'+s['arm']+'/layerfs-remote-daemon --config /state/daemon.setup > /state/daemon.log 2>&1 &')
    h.ready(s['daemon'],'/state/daemon.log','REMOTE_DAEMON_READY')
    return s


def mount(s,label,branch):
    _,branch_id=h.docker(label+'-id','exec',s['server'],'/bins/cxn-noignore-driver','id',branch)
    _,text=h.ctl(s,label+'-mount','mount',branch_id.strip())
    m=re.search(r'path=(\S+) workspace=(\S+) namespace=(\d+)',text)
    if not m:raise RuntimeError('LayerFS mount not ready')
    s=dict(s);s.update(zip(['path','workspace','namespace'],m.groups()));s['branch']=branch
    return s


def fork(s,label,name,source='base'):
    before=v.store(s)
    row,text=h.call(s,label,'branch.fork','name='+name,'from='+source)
    h.record('fork',label=label,branch=name,source=source,before=before,after=v.store(s),command_wall_ns=row['wall_ns'],sample_count=1)


def work(s,label,command,limit=300,check=True):
    before={'transport':h.proxy(s),'store':v.store(s)}
    row,text=h.docker(label,'exec','--user','1000:1000','-e','HOME=/home/runner','-w',s['path'],s['daemon'],
      'timeout',str(limit),'bash','-c',command,limit=limit+5,check=False)
    after={'transport':h.proxy(s),'store':v.store(s)}
    h.record('workload',before=before,after=after,**row)
    if check and row['exit']!=0:
        diagnostic=subprocess.run(['docker','exec',s['daemon'],'tail','-100','/state/daemon.log'],capture_output=True,text=True)
        (h.OUT/(label+'-daemon-at-failure.log')).write_text(diagnostic.stdout)
        raise RuntimeError('workload failure: '+label)
    return row,text


def unmount(s,label,discard=False):
    return h.ctl(s,label,'unmount',s['workspace'],s['namespace'],*(['discard'] if discard else []))


def node_arm(arm):
    h.IMAGE='cxn-tools:noignore02-node20';v.NODE_BUILD='pnpm build && '+v.INC
    name='v2-vite-'+arm+'3';s=start_server(v.load('v2-vite-fullbase'),name,arm)
    fork(s,name+'-thread-fork','thread')
    s=client(s,name+'-cold');before={'store':v.store(s),'transport':h.proxy(s)};start=time.monotonic_ns()
    s=mount(s,name+'-cold','thread');v.save(s)
    row,_=work(s,name+'-S2-test',v.NODE_TEST,110,False)
    h.record('fresh_test',label=name+'-S2',wall_ns=time.monotonic_ns()-start,before=before,after={'store':v.store(s),'transport':h.proxy(s)},exit=row['exit'],sample_count=1)
    if row['exit']!=0:raise RuntimeError('Node S2 unit tests failed; inspect before further selections')
    for iteration in range(1,11):
        label=name+f'-S3-{iteration:02}'
        edit='import pathlib,re; p=pathlib.Path("packages/vite/src/node/constants.ts"); s=p.read_text(); s=re.sub(r"\\nexport const CXN_MEASUREMENT_ITERATION = \\d+\\n", "\\n", s); p.write_text(s+"\\nexport const CXN_MEASUREMENT_ITERATION = '+str(iteration)+'\\n")'
        work(s,label+'-edit','python3 -c '+v.quote(edit),10)
        work(s,label+'-incremental',v.INC,120)
        v.commit(s,label+'-commit')
    work(s,name+'-S4-clean-build','rm -rf packages/vite/temp packages/vite/dist && '+v.NODE_BUILD,300)
    v.commit(s,name+'-S4-commit')
    work(s,name+'-S5-add','pnpm add -Dw decimal.js@10.4.3 --registry=https://registry.npmjs.org',600)
    v.commit(s,name+'-S5-commit');v.save(s)
    unmount(s,name+'-thread-unmount')
    fresh=client(s,name+'-resume');before={'store':v.store(fresh),'transport':h.proxy(fresh)};start=time.monotonic_ns()
    fresh=mount(fresh,name+'-resume','thread')
    if arm=='on':
        work(fresh,name+'-S6-reinstall','pnpm install --frozen-lockfile --registry=https://registry.npmjs.org',600)
        work(fresh,name+'-S6-rebuild',v.NODE_BUILD,300)
    command='node -e "if (new (require(\'decimal.js\'))(\'0.1\').plus(\'0.2\').toString() !== \'0.3\') process.exit(1)" && '+v.NODE_TEST
    row,_=work(fresh,name+'-S6-test',command,110,False)
    h.record('resume',label=name+'-S6',wall_ns=time.monotonic_ns()-start,before=before,after={'store':v.store(fresh),'transport':h.proxy(fresh)},exit=row['exit'],sample_count=1)
    unmount(fresh,name+'-resume-unmount',True)
    s.pop('workspace',None);s.pop('namespace',None);s.pop('path',None);v.save(s)


def node_fullbase():
    h.IMAGE='cxn-tools:noignore02-node20'
    name='v2-vite-fullbase';s=start_server(v.load('v2-vite'),name,'off')
    s=client(s,name+'-builder');s=mount(s,name+'-builder','base');v.save(s)
    before=v.snapshot(s,name+'-start')
    work(s,name+'-build','pnpm build && '+v.INC,300)
    v.commit(s,name+'-commit')
    h.record('revised_warm_base',label=name,reused_install='v2-vite frozen-lockfile install under Node 22',runtime='Node 20.19.0',before=before,after=v.snapshot(s,name+'-end'),inventory=v.shape(s,name+'-shape'),sample_count=1)
    v.save(s);close_base(name)


def merges(kind):
    name='v2-vite-off3' if kind=='node' else 'v2-maven-a-off'
    s=v.load(name)
    if kind=='node':h.IMAGE='cxn-tools:noignore02-node20'
    s=client(s,name+'-merge', [s['shared_cache']+':/home/runner/.m2'] if kind=='maven' else [])
    for side in ['left','right']:
        branch='generated-'+side;label=name+'-S7-'+side
        fork(s,label+'-fork',branch,'thread');m=mount(s,label,branch)
        if kind=='node':
            constant='DEFAULT_DEV_PORT' if side=='left' else 'DEFAULT_PREVIEW_PORT'
            code='import pathlib,re; p=pathlib.Path("packages/vite/src/node/constants.ts"); t=p.read_text(); t,n=re.subn(r"('+constant+' = )\\d+", r"\\g<1>'+('5174' if side=='left' else '4174')+'",t); assert n==1; p.write_text(t)'
            edit='python3 -c '+v.quote(code)
            build='pnpm build && '+v.INC
        else:
            file='welcome.html' if side=='left' else 'error.html'
            edit='printf "\\n<!-- cxn '+side+' -->\\n" >> src/main/resources/templates/'+file
            build='mvn -B -ntp -o -DskipTests package'
        work(m,label+'-edit',edit,10);work(m,label+'-build',build,110)
        v.commit(m,label+'-commit');unmount(m,label+'-unmount')
    row,text=h.call(s,name+'-S7-generated-merge','branch.merge','branch=generated-left','with=generated-right','name=generated-merged')
    h.record('generated_merge',label=name+'-S7',reply=text,command_wall_ns=row['wall_ns'],sample_count=1)
    for side in ['left','right']:
        branch='source-'+side;label=name+'-S7-source-'+side
        fork(s,label+'-fork',branch,'thread');m=mount(s,label,branch)
        source='packages/vite/src/node/constants.ts' if kind=='node' else 'src/main/java/org/springframework/samples/petclinic/PetClinicApplication.java'
        work(m,label+'-edit','printf "\\n// source control '+side+'\\n" >> '+source,10)
        v.commit(m,label+'-commit');unmount(m,label+'-unmount')
    row,text=h.docker(name+'-S7-source-conflict','exec',s['server'],'timeout','25','/bins/cxn-noignore-driver','call','branch.merge','branch=source-left','with=source-right','name=source-merged',check=False)
    expected='code: "Conflict"' in text and 'nothing was created' in text
    h.record('source_conflict_control',label=name+'-S7-source',reply=text,expected_conflict=expected,command_wall_ns=row['wall_ns'],sample_count=1)
    if not expected:raise RuntimeError('source conflict control did not conflict')


if __name__=='__main__':
    try:
        if sys.argv[1]=='merge':merges(sys.argv[2])
        elif sys.argv[1]=='node-fullbase':node_fullbase()
        elif sys.argv[1]=='close-base':close_base(sys.argv[2])
        elif sys.argv[1]=='node-arm':node_arm(sys.argv[2])
        else:raise ValueError('unknown selection')
    except BaseException as error:
        h.record('selection_failure',selection=sys.argv[1:],error=str(error));raise
