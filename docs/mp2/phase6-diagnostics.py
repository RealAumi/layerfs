#!/usr/bin/env python3
"""Default Git policy, refreshed-root cohorts, and live teardown observations."""
import importlib.util,os,sys,pathlib,json,re,hashlib
mode=sys.argv[1];os.environ.update(LFS_CAMPAIGN='phase6',LFS_RESOURCE_PREFIX='mp2-p6')
sys.argv[1]='library-'+mode
spec=importlib.util.spec_from_file_location('topology',pathlib.Path(__file__).with_name('phase3-diagnostics.py'))
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def save(v):h.record(h.RESULTS,v)
def copy(c,src,name):h.docker('cp',c+':'+src,str(h.OUT/name))
def git(m,*args,trace=None,refresh=False):
    prefix=['strace','-f','-yy','-o',trace,'-e','trace=read,pread64,mmap'] if trace else []
    return h.ex(h.B,'timeout','115',*prefix,'git','-c','safe.directory=*','-C',m[0],*([] if refresh else ['--no-optional-locks']),*args,wall=120,check=False)
def unmount(m):
    r=h.ex(h.B,'timeout','25','/bin-lfs/layerfs-remote','/state/control.setup','unmount',*m[1:],wall=27,check=False);save(dict(kind='unmount',container=h.B,result=r));return r
EDIT="""import os,hashlib,json,sys
p=sys.argv[1];s=os.stat(p);b=open(p,'rb').read();open(p,'wb').write(bytes([b[0]^1])+b[1:])
if sys.argv[2]=='restore':os.utime(p,ns=(s.st_atime_ns,s.st_mtime_ns))
t=os.stat(p);print(json.dumps(dict(before={k:getattr(s,k) for k in ['st_ino','st_dev','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns']},after={k:getattr(t,k) for k in ['st_ino','st_dev','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns']},before_sha=hashlib.sha256(b).hexdigest(),after_sha=hashlib.sha256(open(p,'rb').read()).hexdigest())))"""
def oracle(case,m):
    if case=='server':
        unmount(m);h.docker('exec','-e','LFS_MODE=write','-e','LFS_PATH=/README.md','-e','LFS_TEXT=phase six server edit\n',h.A,'timeout','10','/bin-lfs/driver','--ignored','--exact','drive','--nocapture');m,_=h.mount();evidence=h.ex(h.B,'cat',m[0]+'/README.md')
    else:evidence=h.ex(h.B,'python3','-c',EDIT,m[0]+'/README.md','restore' if case=='restore' else 'ordinary')
    r=git(m,'status','--short',trace='/state/oracle.trace');copy(h.B,'/state/oracle.trace',case+'.trace')
    forced=git(m,'hash-object','README.md');index=git(m,'rev-parse',':README.md')
    save(dict(kind='oracle',case=case,status=r,evidence=evidence,reported='README.md' in r['output'],forced_hash=forced['output'].strip(),index_hash=index['output'].strip()));unmount(m)
PROBE="""import os,glob,json
p='/proc/'+open('/state/pid').read().strip();out={}
for t in glob.glob(p+'/task/*'):
 out[t]={}
 for f in ['comm','wchan','syscall','stack','mountinfo']:
  try:out[t][f]=open(t+'/'+f).read()
  except OSError as e:out[t][f]=str(e)
try:out['fds']={f:os.readlink(f) for f in glob.glob(p+'/fd/*')}
except OSError:pass
print(json.dumps(out))"""
def second_b():
    b='mp2-p6-b2';v=b+'-data';n=b+'-net'
    h.docker('volume','create',v);h.docker('network','create','--internal',n)
    h.docker('run','--rm','--name','mp2-p6-b2-config','-v',v+':/state','-v',str(h.CFG)+':/cfg:ro',h.IMAGE,'bash','-c','chmod 700 /state; cp /cfg/b2.setup /state/control.setup')
    h.docker('run','-d','--name',b,'--init','--network',h.LINK,'--device','/dev/fuse','--cap-add','SYS_ADMIN','--cap-add','SYS_PTRACE','--security-opt','apparmor=unconfined','-v',v+':/state','-v',h.INPUT+':/input:ro','-v',str(h.BIN)+':/bin-lfs:ro','-e','LAYERFS_CONSTRUCTION_WORKERS=1',h.IMAGE,'sleep','infinity')
    h.docker('network','connect',n,b);h.ex(b,'bash','-c','python3 /bin-lfs/tcp-cut.py > /state/proxy.log 2>&1 &');h.ready(b,'/state/proxy.log','PROXY_READY')
    h.ex(b,'bash','-c','/bin-lfs/layerfs-remote-daemon --config /state/control.setup > /state/daemon.log 2>&1 & echo $! > /state/pid');h.ready(b,'/state/daemon.log','REMOTE_DAEMON_READY');return b
try:
    if mode=='seed':
        for v in [h.SEED,h.INPUT]:h.docker('volume','create',v)
        h.docker('run','--rm','--name','mp2-p6-seed','-v',str(h.BIN)+':/bin-lfs:ro','-v',str(h.CFG)+':/out','-v',h.SEED+':/state','-v','lfs-src:/original:ro','-e','LFS_MODE=init','-e','LFS_SOURCE=/original/dubbo','-e','LAYERFS_CONSTRUCTION_WORKERS=1',h.IMAGE,'timeout','120','/bin-lfs/driver','--ignored','--exact','drive','--nocapture')
        save(dict(binaries={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in h.BIN.iterdir()},image=h.docker('image','inspect',h.IMAGE,'--format','{{.Id}}')['output']))
    elif mode=='check':
        h.SEED='mp2-p6-warm';h.startup(False,0)
        save(dict(kind='metadata-test',result=h.ex(h.B,'timeout','120','/bin-lfs/metadata-test','--ignored','--exact','remote_generation_is_verified_metadata_only_and_reused','--nocapture')))
    elif mode=='steady':
        h.startup(False,0);m,_=h.mount();r=git(m,'status','--short',refresh=True);assert r['exit']==0;save(dict(kind='refresh',result=r));git(m,'ls-files','--debug','README.md');oracle('restore',m)
    elif mode=='join':
        h.SEED='mp2-p6-warm';h.startup(False,0);m,_=h.mount();git(m,'status','--short');original=h.B
        h.B=second_b();m2,_=h.mount();git(m2,'status','--short');unmount(m2)
        save(dict(kind='join-probe',result=h.ex(h.B,'python3','-c',PROBE)))
        scan="import glob,json,os;out=[];\nfor p in glob.glob('/proc/[0-9]*'):\n try:\n  rows=[r for r in open(p+'/mountinfo').read().splitlines() if ' - fuse layerfs ' in r];\n  if rows:out.append(dict(pid=p,comm=open(p+'/comm').read().strip(),ns=os.readlink(p+'/ns/mnt'),rows=rows))\n except OSError:pass\nprint(json.dumps(out))"
        save(dict(kind='host-mounts',result=h.docker('run','--rm','--name','mp2-p6-observe','--pid=host','--cap-add','SYS_PTRACE','--cap-add','SYS_ADMIN','--security-opt','apparmor=unconfined',h.IMAGE,'python3','-c',scan)))
        copy(h.B,'/state/daemon.log','b2-daemon.log');h.B=original;unmount(m)
        # Leave these exact owned processes for follow-up read-only observations.
    elif mode=='warm':
        h.startup(False,0);m,_=h.mount();r=git(m,'update-index','--refresh',refresh=True);assert r['exit']==0,r;save(dict(kind='refresh',result=r));git(m,'ls-files','--debug','README.md');save(dict(kind='commit',result=h.ctl('commit',m)))
        h.docker('volume','create','mp2-p6-warm')
        backup="import sqlite3;src=sqlite3.connect('file:/a/store/store.sqlite?mode=ro',uri=True);dst=sqlite3.connect('/warm/store/store.sqlite');dst.execute('pragma synchronous=OFF');src.backup(dst);dst.close();src.close()"
        h.docker('run','--rm','--name','mp2-p6-backup','-v',h.SEED+':/seed:ro','-v',h.VA+':/a:ro','-v','mp2-p6-warm:/warm',h.IMAGE,'bash','-c','cp -a /seed/. /warm/; python3 -c '+__import__('shlex').quote(backup))
        original=h.B;h.B=second_b();m2,mr=h.mount();before=h.stats(False);r=git(m2,'status','--short',trace='/state/status.trace');copy(h.B,'/state/status.trace','device-status.trace');git(m2,'ls-files','--debug','README.md')
        h.ex(h.B,'stat','-c','dev=%d ino=%i uid=%u gid=%g mtime=%y ctime=%z',m2[0]+'/README.md');save(dict(kind='different-device',mount=mr,status=r,requests=h.stats(False)['roundTrips']-before['roundTrips']))
        unmount(m2);save(dict(kind='join-probe',container=h.B,result=h.ex(h.B,'python3','-c',PROBE)));copy(h.B,'/state/daemon.log','b2-daemon.log')
        h.B=original;save(dict(kind='other-probe',container=h.B,result=h.ex(h.B,'python3','-c',PROBE)));unmount(m)
    elif mode.startswith('measure-'):
        _,arm,delay=mode.split('-');delay=int(delay);h.SEED='mp2-p6-warm';os.environ['LAYERFS_REMOTE_TRACE_READS']='1'
        for rep in range(1,4):
            try:
                h.startup(False,delay);before=h.stats(False);m,mr=h.mount();mounted=h.stats(False);r=git(m,'status','--short',trace='/state/status.trace');copy(h.B,'/state/status.trace',f'status-{rep}.trace')
                copy(h.A,'/state/daemon.log',f'requests-{rep}.log')
                code='import sqlite3,json;d=sqlite3.connect("file:/state/store/store.sqlite?mode=ro",uri=True);print(json.dumps(list(d.execute("select hex(object_id),role from object_location"))))'
                if rep==1:(h.OUT/'roles.json').write_text(h.ex(h.A,'python3','-c',code)['output'])
                save(dict(kind='measure',arm=arm,rep=rep,rtt=delay,mount=mr,status=r,mount_requests=mounted['roundTrips']-before['roundTrips'],status_requests=h.stats(False)['roundTrips']-mounted['roundTrips']));unmount(m)
            finally:h.cleanup()
    elif mode.startswith('oracles-'):
        h.SEED='mp2-p6-warm'
        for case in ['restore','server','ordinary']:
            try:h.startup(False,0);m,_=h.mount();oracle(case,m)
            finally:h.cleanup()
    else:raise ValueError(mode)
finally:
    if mode=='warm':
        h.B='mp2-p6-b';h.docker('rm','-f','mp2-p6-b2',check=False);h.docker('volume','rm','mp2-p6-b2-data',check=False);h.docker('network','rm','mp2-p6-b2-net',check=False)
    if mode in ['steady','warm','check']:h.cleanup()
