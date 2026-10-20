#!/usr/bin/env python3
"""Bounded local Phase 8 campaigns; fresh, append-only output selection."""
import importlib.util,pathlib,json,sys,time,hashlib,os,re
spec=importlib.util.spec_from_file_location('env',pathlib.Path(__file__).with_name('phase8-env.py'));h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
import fcntl
lock=(h.WORK/'run.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
mode=sys.argv[1];out=h.ROOT/mode;out.mkdir(exist_ok=False)
def rec(v):h.record(out,v)
if mode=='seed':
    for variant in ['plain','large','hot']:
        cfg=h.WORK/'config'/variant;cfg.mkdir(exist_ok=False);e=h.Env(out,variant)
        raw='cx7-p8-raw-'+variant;warm='cx7-p8-seed-'+variant
        e.d('volume','create',raw)
        e.d('run','--rm','--name','cx7-p8-init','-v',str(h.COMMON)+':/bin-lfs:ro','-v',str(cfg)+':/out','-v',raw+':/state','-v',h.INPUT+':/input:ro','-e','LFS_MODE=init','-e','LFS_SOURCE=/input/'+variant,'-e','LAYERFS_CONSTRUCTION_WORKERS=1',h.IMAGE,'timeout','120','/bin-lfs/remote_driver','--ignored','--exact','drive','--nocapture',wall=125)
        e.seed=raw
        try:
            e.start();e.mount();rec(dict(variant=variant,refresh=e.git('update-index','--refresh',refresh=True)));rec(dict(variant=variant,commit=e.ctl('commit',*e.m[1:])))
            e.d('volume','create',warm)
            backup='import sqlite3;s=sqlite3.connect("file:/a/store/store.sqlite?mode=ro",uri=True);d=sqlite3.connect("/warm/store/store.sqlite");d.execute("pragma synchronous=OFF");s.backup(d);d.close();s.close()'
            e.d('run','--rm','--name','cx7-p8-backup','-v',raw+':/raw:ro','-v',e.va+':/a:ro','-v',warm+':/warm',h.IMAGE,'bash','-c','cp -a /raw/. /warm/; python3 -c '+__import__('shlex').quote(backup))
            rec(dict(variant=variant,unmount=e.unmount()))
        finally:e.cleanup()
elif mode in ['hot','hot-stat']:
    envs={arm:h.Env(out,arm=arm,tag=arm) for arm in ['before','after']}
    rec(dict(kind='identity',source={'before':'6394865a4','after':'524862598'},harness={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [pathlib.Path(__file__),pathlib.Path(__file__).with_name('phase8-env.py'),pathlib.Path(__file__).with_name('phase8-workload.py')]}))
    try:
        for e in envs.values():e.start();e.mount()
        for case in (['stat'] if mode=='hot-stat' else ['status','find','stat','small','large']):
            for rep in range(1,11):
                for arm in (['before','after'] if rep%2 else ['after','before']):
                    e=envs[arm];e.ex('timeout','115','python3','/harness/phase8-workload.py','prepare',case,e.m[0],wall=120)
                    s0=e.stats();f0=e.fuse();r=e.ex('timeout','115','python3','/harness/phase8-workload.py','measure',case,e.m[0],wall=120,check=False);f1=e.fuse();s1=e.stats()
                    rec(dict(case=case,rep=rep,arm=arm,result=r,store={k:s1[k]-s0[k] for k in s0},fuse={k:f1[k]-f0[k] for k in f0}));print(case,rep,arm,r['output'].strip(),flush=True)
                    assert r['exit']==0,r
        for arm,e in envs.items():rec(dict(kind='unmount',arm=arm,result=e.unmount()))
    finally:
        for e in envs.values():e.cleanup()
elif mode=='cold':
    for delay in [0,2,20]:
        for variant in ['plain','large']:
            e=h.Env(out,variant,tag=variant+'-'+str(delay),delay=delay)
            try:
                e.start();s0=e.stats();m=e.mount();s1=e.stats()
                q='import sqlite3,json;d=sqlite3.connect("file:/state/cache/objects.sqlite?mode=ro",uri=True);print(json.dumps(dict(objects=d.execute("select count(*) from objects").fetchone()[0],lengths=d.execute("select count(*) from lengths").fetchone()[0],bytes=d.execute("select sum(length(body)) from objects").fetchone()[0])))'
                cache=json.loads(e.ex('python3','-c',q)['output']);f0=e.fuse();g=e.git('status','--short',check=False);f1=e.fuse();s2=e.stats()
                rec(dict(variant=variant,delay=delay,mount=m,status=g,mount_requests=s1['roundTrips']-s0['roundTrips'],status_requests=s2['roundTrips']-s1['roundTrips'],cache=cache,status_fuse={k:f1[k]-f0[k] for k in f0}));print(variant,delay,m['ns']/1e9,g['ns']/1e9,cache,flush=True);rec(dict(kind='unmount',variant=variant,delay=delay,result=e.unmount()))
            finally:e.cleanup()
elif mode=='ownership':
    e=h.Env(out,'plain')
    try:
        e.start();e.mount();e.ex('mkdir','/tmp/copy-fixtures');e.ex('chmod','777','/tmp/copy-fixtures')
        for owner in [0,1000]:
            e.ex('tar','-cpf',f'/tmp/copy-fixtures/{owner}.tar','-C',f'/input/copies-{owner}','.')
            for uid in [0,1000]:
                for tool in ['cp','tar','rsync']:
                    label=f'{tool}-user{uid}-owner{owner}';dest=e.m[0]+'/'+label;e.ex('mkdir',dest,user=f'{uid}:{uid}')
                    cmd={'cp':['cp','-a',f'/input/copies-{owner}/.',dest+'/'],'tar':['tar','-xpf',f'/tmp/copy-fixtures/{owner}.tar','-C',dest],'rsync':['rsync','-a',f'/input/copies-{owner}/',dest+'/']}[tool]
                    r=e.ex('timeout','20','strace','-f','-yy','-o','/tmp/copy-fixtures/'+label+'.trace','-e','trace=%file,fchown,fchmod,flistxattr,fgetxattr,fsetxattr,copy_file_range,ioctl',*cmd,user=f'{uid}:{uid}',wall=25,check=False)
                    e.d('cp',e.b+':/tmp/copy-fixtures/'+label+'.trace',out/(label+'.trace'))
                    state=e.ex('python3','-c','import pathlib,os,json,hashlib,sys;r=pathlib.Path(sys.argv[1]);print(json.dumps([{ "path":str(p.relative_to(r)),"uid":p.stat().st_uid,"gid":p.stat().st_gid,"mode":oct(p.stat().st_mode&0o777),"sha256":hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None} for p in [r,*r.rglob("*")]]))',dest)
                    rec(dict(case=label,tool=tool,uid=uid,source_owner=owner,result=r,files=json.loads(state['output'])))
        probe='import os,json,sys;p=sys.argv[1];out=[]\nfor uid in [1000,0]:\n try:os.chown(p,uid,uid);out.append(dict(uid=uid,result="ok"))\n except OSError as e:out.append(dict(uid=uid,errno=e.errno,error=str(e)))\nprint(json.dumps(out))'
        rec(dict(kind='direct-chown',result=e.ex('python3','-c',probe,e.m[0]+'/cp-user0-owner1000/file.txt')))
        rec(dict(kind='unmount',result=e.unmount(discard=True)))
    finally:e.cleanup()
elif mode=='ctime':
    e=h.Env(out,'plain',raw=True)
    try:
        e.start();e.mount();rec(dict(kind='refresh',result=e.git('status','--short',refresh=True)))
        edit='import os,hashlib,json,sys;p=sys.argv[1];s=os.stat(p);b=open(p,"rb").read();open(p,"wb").write(bytes([b[0]^1])+b[1:]);os.utime(p,ns=(s.st_atime_ns,s.st_mtime_ns));t=os.stat(p);print(json.dumps(dict(before={k:getattr(s,k) for k in ["st_size","st_mtime_ns","st_ctime_ns"]},after={k:getattr(t,k) for k in ["st_size","st_mtime_ns","st_ctime_ns"]},before_sha=hashlib.sha256(b).hexdigest(),after_sha=hashlib.sha256(open(p,"rb").read()).hexdigest())))'
        rec(dict(kind='oracle',evidence=e.ex('python3','-c',edit,e.m[0]+'/README.md'),status=e.git('status','--short'),forced=e.git('hash-object','README.md'),index=e.git('rev-parse',':README.md')));rec(dict(kind='unmount',result=e.unmount(discard=True)))
    finally:e.cleanup()
else:raise ValueError(mode)
