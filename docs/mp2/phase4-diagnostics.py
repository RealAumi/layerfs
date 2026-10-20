#!/usr/bin/env python3
"""Phase 4 diagnostics. Reuse Phase 3 topology, calibration and bounded commands."""
import importlib.util, os, sys, json, re, hashlib, pathlib, shutil
mode=sys.argv[1]; os.environ.update(LFS_CAMPAIGN='phase4',LFS_RESOURCE_PREFIX='mp2-p4')
sys.argv[1]='library-'+mode
spec=importlib.util.spec_from_file_location('topology',pathlib.Path(__file__).with_name('phase3-diagnostics.py'))
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def save(name,value):h.record(h.OUT/(name+'.jsonl'),value)
def copy(c,src,name):h.docker('cp',c+':'+src,str(h.OUT/name))
def storage():
    code='import sqlite3,json;d=sqlite3.connect("file:/state/store/store.sqlite?mode=ro",uri=True);print(json.dumps(dict(pack_bytes=d.execute("select coalesce(sum(length),0) from pack").fetchone()[0],occupied_bytes=(d.execute("pragma page_count").fetchone()[0]-d.execute("pragma freelist_count").fetchone()[0])*d.execute("pragma page_size").fetchone()[0])))'
    return json.loads(h.ex(h.A,'python3','-c',code)['output'])
try:
    if mode=='seed':
        for v in [h.SEED,h.INPUT]:h.docker('volume','create',v)
        h.docker('run','--rm','--name','mp2-p4-seed','-v',str(h.BIN)+':/bin-lfs:ro','-v',str(h.CFG)+':/out','-v',h.SEED+':/state','-v','lfs-src:/original:ro','-e','LFS_MODE=init','-e','LFS_SOURCE=/original/dubbo','-e','LAYERFS_CONSTRUCTION_WORKERS=1',h.IMAGE,'timeout','120','/bin-lfs/driver','--ignored','--exact','drive','--nocapture')
        save('identity',dict(binaries={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in h.BIN.iterdir()},image=h.docker('image','inspect',h.IMAGE,'--format','{{.Id}}')['output']))
    elif mode=='diagnose':
        os.environ['LAYERFS_REMOTE_TRACE_READS']='1'
        h.startup(False,0);before=h.stats(False);m,mr=h.mount();after=h.stats(False)
        copy(h.A,'/state/daemon.log','mount-requests.log')
        r=h.ex(h.B,'timeout','120','strace','-f','-ttt','-yy','-o','/state/git.strace','-e','trace=%file,read,mmap,close','git','-c','safe.directory=*','-C',m[0],'--no-optional-locks','status','--short',wall=120)
        save('results',dict(mount=mr,git=r,mount_metrics=after,final_metrics=h.stats(False)))
        copy(h.A,'/state/daemon.log','all-requests.log');copy(h.B,'/state/git.strace','git.strace')
        for c,sql,name in [(h.A,"select hex(object_id),role,canonical_length from object_location",'roles'),(h.B,"select hex(id),body from objects",'cache')]:
            db='/state/store/store.sqlite' if c==h.A else '/state/cache/objects.sqlite'
            code='import sqlite3,json,hashlib;db=sqlite3.connect("file:'+db+'?mode=ro",uri=True);print(json.dumps([(r[0],hashlib.sha256(r[1][13:]).hexdigest(),len(r[1])) if isinstance(r[1],bytes) else r for r in db.execute('+repr(sql)+')]))'
            save(name,json.loads(h.ex(c,'python3','-c',code)['output']))
        h.ctl('unmount',m)
    elif mode=='index':
        h.startup(False,0);m,_=h.mount()
        h.ex(h.B,'timeout','10','git','-c','safe.directory=*','-C',m[0],'ls-files','--debug','README.md')
        h.ex(h.B,'stat','-c','ino=%i uid=%u gid=%g mtime=%y ctime=%z',m[0]+'/README.md')
        h.ctl('unmount',m)
    elif mode.startswith('cold'):
        delay=int(mode.split('-')[1])
        for rep in range(1,4):
            try:
                h.startup(False,delay);before=h.stats(False);m,mr=h.mount();after=h.stats(False)
                r=h.ex(h.B,'timeout','115','git','-c','safe.directory=*','-C',m[0],'--no-optional-locks','status','--short',wall=120,check=False)
                save('results',dict(rep=rep,rtt=delay,mount=mr,git=r,mount_requests=after['roundTrips']-before['roundTrips'],git_requests=h.stats(False)['roundTrips']-after['roundTrips']))
                h.ctl('unmount',m)
            finally:h.cleanup()
    elif mode.startswith('node'):
        delay=int(mode.split('-')[1])
        for rep in range(1,4):
            try:
                h.startup(False,delay);m,_=h.mount()
                for label in ['full','delta']:
                    h.ex(h.B,'timeout','115','cp','-a','--no-preserve=ownership','/input/'+label+'/.',m[0]+'/',wall=120)
                    stored_before=storage();before=h.stats(False);r=h.ctl('commit',m);after=h.stats(False);stored_after=storage()
                    assert 'Committed(' in r['output'],r
                    save('results',dict(rep=rep,rtt=delay,kind=label,wall_ns=int(re.search(r'wall_ns=(\d+)',r['output'])[1]),metrics={k:after[k]-before[k] for k in before},reply=r['output'],store_growth={k:stored_after[k]-stored_before[k] for k in stored_before}))
                expected=(h.HOME/'work/shape/delta/node_modules/added-zod/package.json').read_text()
                h.docker('exec','-e','LFS_MODE=read','-e','LFS_PATH=/node_modules/added-zod/package.json','-e','LFS_EXPECT='+expected,h.A,'timeout','10','/bin-lfs/driver','--ignored','--exact','drive','--nocapture')
                h.ctl('unmount',m)
            finally:h.cleanup()
    else:raise ValueError(mode)
finally:
    if mode in ['diagnose','index']:h.cleanup()
