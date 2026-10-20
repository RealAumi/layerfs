#!/usr/bin/env python3
"""Local Phase 8 ignore/restore cost and crash receipts; no implicit reruns."""
import pathlib, os, sys, json, hashlib, gzip, shutil, importlib.util, time, statistics, re
ROOT = pathlib.Path(__file__).resolve().parents[2]
WORK = pathlib.Path.home() / '.cache/cxi-ignore09'
FIXTURE = WORK / 'fixture'
MANIFEST = ROOT / 'docs/mp2/receipts/run04/phase4/full-manifest.json.gz'

def fixture():
    WORK.mkdir(exist_ok=True)
    assert not FIXTURE.exists(), 'reuse existing fixture; never replace it silently'
    FIXTURE.mkdir()
    rows = json.load(gzip.open(MANIFEST, 'rt'))
    for row in rows:
        p = FIXTURE / row['path']; p.parent.mkdir(parents=True, exist_ok=True)
        block = hashlib.shake_256(row['sha256'].encode()).digest(min(row['size'], 65536))
        with p.open('wb') as f:
            left = row['size']
            while left:
                n = min(left, len(block)); f.write(block[:n]); left -= n
    dirs = sum(p.is_dir() for p in FIXTURE.rglob('*'))
    result = dict(files=len(rows), bytes=sum(r['size'] for r in rows), directories=dirs,
                  manifest_sha256=hashlib.sha256(MANIFEST.read_bytes()).hexdigest(), recipe='Phase8 SHAKE, repeated 64KiB blocks')
    assert result['files'] == 30000 and result['bytes'] == 211730666 and dirs == 9470, result
    (WORK/'fixture.json').write_text(json.dumps(result, indent=2)+'\n')
    print(result, flush=True)

def load(arm):
    os.environ['IGN_RECEIPTS'] = 'ignore09/' + arm
    os.environ['IGN_WORK'] = str(WORK / arm)
    spec=importlib.util.spec_from_file_location('ignore_env', ROOT/'docs/mp2/run-ignore-e2e.py')
    h=importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
    original=h.docker
    def docker(*args, **kw):
        args=list(args)
        if args[0]=='run' and '--name' in args:
            name=args[args.index('--name')+1]
            if name in [h.B1,h.B2]: args[1:1]=['-v',f'{FIXTURE}:/fixture:ro']
            if name=='cxi-seed' and '/seed/b2.setup' in args[-1]:
                args[-1] += "; printf 'ignore=git\\n' >> /state/daemon.setup"
        return original(*args, **kw)
    h.docker=docker
    return h

def seal(arm, source):
    dest=WORK/arm/'bin'; dest.mkdir(parents=True)
    receipt=ROOT/'docs/mp2/receipts/ignore09'/arm; receipt.mkdir(parents=True,exist_ok=True)
    identities={}
    for p in pathlib.Path(source).iterdir():
        if p.is_file():
            shutil.copy2(p,dest/p.name); identities[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
    (receipt/'binaries.json').write_text(json.dumps(identities,indent=2)+'\n')

def measure(arm):
    h=load(arm); output=h.RECEIPTS/'samples.jsonl'
    assert not output.exists(), 'append-only cohort; choose a new registered arm'
    def record(r):
        with output.open('a') as f: f.write(json.dumps(r)+'\n')
        print(json.dumps(r),flush=True)
    record(dict(kind='identity',fixture=json.loads((WORK/'fixture.json').read_text()),cache='Phase8 hot prepared mount; OS uncontrolled',delay_ms=0))
    start=time.monotonic_ns()
    with h.Env():
        mounts={}
        fork=h.docker('exec','-e','LFS_MODE=fork','-e','LFS_BRANCH=other',h.A,'timeout','25','/opt/lfs/remote_driver','--ignored','--exact','drive','--nocapture')
        other=re.search(r'BRANCH (\w+)',fork.stdout)[1]
        original_mount=h.mount
        def mount(b,key=None):
            if b==h.B1: return original_mount(b,key)
            text=h.ctl(b,'mount',other,*([key] if key else [])).stdout
            return h.Mount(b,*re.search(r'path=(\S+) workspace=(\S+) namespace=(\d+)',text).groups())
        h.mount=mount
        # Independent Branches: every sample has exactly one kept file change.
        for label,b,key in [('keyed',h.B1,'phase8'),('unkeyed',h.B2,None)]:
            m=h.mount(b,key); mounts[label]=m
            h.put(m,'.gitignore','node_modules/\n')
            h.put(m,f'{label}.txt','initial 00000000\n')
            h.execute(b,'timeout','115','python3','-c',
                      'import shutil,sys;shutil.copytree("/fixture/node_modules",sys.argv[1]+"/node_modules")',m.path,wall=120)
            result,ns,outer=h.commit(m)
            record(dict(kind='setup',arm=label,ns=ns,outer_ns=outer,result=result))
        record(dict(kind='setup_complete',ns=time.monotonic_ns()-start))
        for i in range(10):
            for label in (['keyed','unkeyed'] if i%2==0 else ['unkeyed','keyed']):
                m=mounts[label]
                h.put(m,f'{label}.txt',f'edit {i:010d}\n')
                p=h.docker('exec',m.b,'timeout','25','/opt/lfs/layerfs-remote','/state/daemon.setup','commit',m.ws,m.ns,expected=None,wall=28)
                match=re.search(r'wall_ns=(\d+)',p.stdout)
                record(dict(kind='sample',arm=label,index=i,ns=int(match[1]) if match else None,outer_ns=p.wall_ns,exit=p.returncode,output=p.stdout))
                assert p.returncode==0, p.stdout
        for label,m in mounts.items():
            count=h.execute(m.b,'timeout','20','python3','-c',
                'import pathlib,sys;print(sum(p.is_file() for p in pathlib.Path(sys.argv[1]).rglob("*")))',m.p('node_modules'),wall=25).stdout.strip()
            assert int(count)==30000, count
            branch='work' if label=='keyed' else 'other'
            result=h.docker('exec','-e','LFS_MODE=read','-e','LFS_BRANCH='+branch,'-e','LFS_PATH=/'+label+'.txt',h.A,'timeout','25','/opt/lfs/remote_driver','--ignored','--exact','drive','--nocapture').stdout
            assert json.loads(re.search(r'SDK_READ (.+)',result)[1])==h.cat(m,label+'.txt')
            rows=json.load(gzip.open(MANIFEST,'rt'))
            assert h.server_read('/'+rows[0]['path']) is None
            size=h.execute(m.b,'python3','-c',
                'import sqlite3,json,os;c=sqlite3.connect("/state/cache/objects.sqlite");print(json.dumps(dict(records=c.execute("SELECT length(body) FROM restore_points").fetchall(),objects=c.execute("SELECT count(*),sum(length(body)) FROM objects WHERE remote=0").fetchone(),files={p:os.stat(p).st_size for p in ["/state/cache/objects.sqlite","/state/cache/objects.sqlite-wal"] if os.path.exists(p)})))').stdout
            record(dict(kind='verified',arm=label,files=int(count),storage=json.loads(size)))
        m=mounts['keyed']; h.unmount(m)
        t=time.monotonic_ns(); restored=h.mount(h.B1,'phase8'); elapsed=time.monotonic_ns()-t
        assert h.exists(restored,rows[0]['path'])
        record(dict(kind='restore',outer_ns=elapsed,stats=h.ctl(h.B1,'stats').stdout))
        h.unmount(restored); h.unmount(mounts['unkeyed'])
    record(dict(kind='complete',ns=time.monotonic_ns()-start))

if __name__=='__main__':
    if sys.argv[1]=='fixture': fixture()
    elif sys.argv[1]=='seal': seal(sys.argv[2],sys.argv[3])
    elif sys.argv[1]=='measure': measure(sys.argv[2])
    else: raise ValueError(sys.argv)
