#!/usr/bin/env python3
"""Ordered Git-stat experiments using the accepted two-container transport setup."""
import importlib.util, os, sys, pathlib, json, re, hashlib
mode=sys.argv[1];os.environ.update(LFS_CAMPAIGN='phase5',LFS_RESOURCE_PREFIX='mp2-p5')
sys.argv[1]='library-'+mode
spec=importlib.util.spec_from_file_location('topology',pathlib.Path(__file__).with_name('phase3-diagnostics.py'))
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def save(value):h.record(h.RESULTS,value)
def copy(c,src,name):h.docker('cp',c+':'+src,str(h.OUT/name))
def git(m,*args,trace=None):
    prefix=['strace','-f','-yy','-o',trace,'-e','trace=read,pread64,mmap'] if trace else []
    return h.ex(h.B,'timeout','115',*prefix,'git','-c','safe.directory=*','-c','core.checkStat=minimal','-C',m[0],'--no-optional-locks',*args,wall=120,check=False)
def status(m,trace=None):return git(m,'status','--short',trace=trace)
STAT="""import os,json,sys
root=sys.argv[1]; names=json.load(open('/input/tracked.json')); out={}
for p in names:
 s=os.lstat(root+'/'+p);out[p]={k:getattr(s,k) for k in ['st_ino','st_dev','st_uid','st_gid','st_mtime_ns','st_ctime_ns','st_size']}
print(json.dumps(out))"""
def inspect(m):return json.loads(h.ex(h.B,'timeout','25','python3','-c',STAT,m[0],wall=27)['output'])
def second_b():
    b=h.PREFIX+'-b2';v=h.PREFIX+'-b2-data';n=h.PREFIX+'-b2-net'
    h.docker('network','create','--internal',n);h.docker('volume','create',v)
    h.docker('run','--rm','--name',h.PREFIX+'-b2-config','-v',v+':/state','-v',str(h.CFG)+':/cfg:ro',h.IMAGE,'bash','-c','chmod 700 /state; cp /cfg/b2.setup /state/control.setup')
    h.docker('run','-d','--name',b,'--init','--network',h.LINK,'--device','/dev/fuse','--cap-add','SYS_ADMIN','--security-opt','apparmor=unconfined','--security-opt','no-new-privileges=true','-v',v+':/state','-v',h.INPUT+':/input:ro','-v',str(h.BIN)+':/bin-lfs:ro','-e','LAYERFS_CONSTRUCTION_WORKERS=1',h.IMAGE,'sleep','infinity')
    h.docker('network','connect',n,b);h.ex(b,'bash','-c','python3 /bin-lfs/tcp-cut.py > /state/proxy.log 2>&1 &');h.ready(b,'/state/proxy.log','PROXY_READY')
    h.ex(b,'bash','-c','/bin-lfs/layerfs-remote-daemon --config /state/control.setup > /state/daemon.log 2>&1 &');h.ready(b,'/state/daemon.log','REMOTE_DAEMON_READY')
    return b
try:
    if mode=='seed':
        for v in [h.SEED,h.INPUT]:h.docker('volume','create',v)
        h.docker('run','--rm','--name','mp2-p5-seed','-v',str(h.BIN)+':/bin-lfs:ro','-v',str(h.CFG)+':/out','-v',h.SEED+':/state','-v','lfs-src:/original:ro','-e','LFS_MODE=init','-e','LFS_SOURCE=/original/dubbo','-e','LAYERFS_CONSTRUCTION_WORKERS=1',h.IMAGE,'timeout','120','/bin-lfs/driver','--ignored','--exact','drive','--nocapture')
        code="import subprocess,json,pathlib;v=subprocess.check_output(['git','-c','safe.directory=*','-C','/original/dubbo','ls-files','-z']).decode().rstrip('\\0').split('\\0');pathlib.Path('/input/tracked.json').write_text(json.dumps(v));print(len(v))"
        h.docker('run','--rm','--name','mp2-p5-paths','-v',h.INPUT+':/input','-v','lfs-src:/original:ro',h.IMAGE,'python3','-c',code)
        save(dict(binaries={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in h.BIN.iterdir()},image=h.docker('image','inspect',h.IMAGE,'--format','{{.Id}}')['output']))
    elif mode=='stability':
        h.startup(False,0);original=h.B;m1,_=h.mount();s1=inspect(m1)
        h.B=second_b();m2,_=h.mount();s2=inspect(m2)
        save(dict(kind='stat-stability',first=s1,second=s2,changed={k:sum(s1[p][k]!=s2[p][k] for p in s1) for k in s1['README.md']}))
        h.ctl('unmount',m2);h.B=original;h.ctl('unmount',m1)
    elif mode=='diagnose':
        os.environ['LAYERFS_REMOTE_TRACE_READS']='1';h.startup(False,0);m,mr=h.mount();before=h.stats(False);copy(h.A,'/state/daemon.log','mount.log')
        r=status(m,trace='/state/status.trace');copy(h.B,'/state/status.trace','status.trace');copy(h.A,'/state/daemon.log','requests.log')
        code='import sqlite3,json;d=sqlite3.connect("file:/state/store/store.sqlite?mode=ro",uri=True);print(json.dumps(list(d.execute("select hex(object_id),role from object_location"))))'
        (h.OUT/'roles.json').write_text(h.ex(h.A,'python3','-c',code)['output'])
        save(dict(kind='minimal-diagnosis',mount=mr,status=r,requests=h.stats(False)['roundTrips']-before['roundTrips']));h.ctl('unmount',m)
    elif mode.startswith('measure-'):
        delay=int(mode.split('-')[1])
        for rep in range(1,4):
            try:
                h.startup(False,delay);before=h.stats(False);m,mr=h.mount();mounted=h.stats(False)
                r=status(m,trace='/state/status.trace');copy(h.B,'/state/status.trace',f'status-{rep}.trace')
                save(dict(kind='minimal',rep=rep,rtt=delay,mount=mr,status=r,mount_requests=mounted['roundTrips']-before['roundTrips'],status_requests=h.stats(False)['roundTrips']-mounted['roundTrips']))
                h.ctl('unmount',m)
            finally:h.cleanup()
    elif mode=='oracles':
        for case in ['same-size-mtime','server-edit','ordinary-edit']:
            try:
                h.startup(False,0);m,_=h.mount();clean=status(m);assert clean['exit']==0 and not clean['output'],clean
                # Git refresh is intentionally absent for the minimal/imported-index variant.
                path=m[0]+'/README.md'
                if case=='server-edit':
                    h.ctl('unmount',m)
                    h.docker('exec','-e','LFS_MODE=write','-e','LFS_PATH=/README.md','-e','LFS_TEXT=phase five server edit\n',h.A,'timeout','10','/bin-lfs/driver','--ignored','--exact','drive','--nocapture')
                    m,_=h.mount();path=m[0]+'/README.md';evidence=h.ex(h.B,'cat',path)
                else:
                    code="import os,hashlib,json,sys;p=sys.argv[1];s=os.stat(p);b=open(p,'rb').read();v=bytes([b[0]^1])+b[1:];open(p,'wb').write(v);"+("os.utime(p,ns=(s.st_atime_ns,s.st_mtime_ns));" if case=='same-size-mtime' else '')+"t=os.stat(p);print(json.dumps(dict(before={k:getattr(s,k) for k in ['st_size','st_mtime_ns','st_ctime_ns']},after={k:getattr(t,k) for k in ['st_size','st_mtime_ns','st_ctime_ns']},before_sha=hashlib.sha256(b).hexdigest(),after_sha=hashlib.sha256(open(p,'rb').read()).hexdigest())))"
                    evidence=h.ex(h.B,'python3','-c',code,path)
                r=status(m,trace='/state/status.trace');copy(h.B,'/state/status.trace',case+'.trace')
                # The forced-content oracle verifies the edit independently of the stat shortcut.
                forced=git(m,'hash-object','README.md');index=git(m,'rev-parse',':README.md')
                save(dict(kind='oracle',case=case,evidence=evidence,status=r,reported=r['exit']==0 and 'README.md' in r['output'],forced_hash=forced['output'].strip(),index_hash=index['output'].strip()))
                h.ctl('unmount',m)
            finally:h.cleanup()
    else:raise ValueError(mode)
finally:
    if mode=='stability':
        h.B=h.PREFIX+'-b';h.docker('rm','-f',h.PREFIX+'-b2',check=False);h.docker('volume','rm',h.PREFIX+'-b2-data',check=False);h.docker('network','rm',h.PREFIX+'-b2-net',check=False);h.cleanup()
    elif mode=='diagnose':h.cleanup()
