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
    def ctl(b,op,*args,expected=0):
        return h.docker('exec',b,'timeout','115','/opt/lfs/layerfs-remote',
                        '/state/daemon.setup',op,*args,expected=expected,wall=120)
    h.ctl=ctl
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

def kill_loop():
    import subprocess
    h=load('kill-loop'); output=h.RECEIPTS/'cycles.jsonl'
    assert not output.exists(), 'each cycle runs once'
    delays=[0,2,5,10,20,40,80,160,320,640,1,3,7,15,30,60,120,240,480,960]
    def record(r):
        with output.open('a') as f: f.write(json.dumps(r)+'\n')
        print(json.dumps(r),flush=True)
    def prepare(m, generation):
        h.put(m,'tracked.txt',f'gen {generation:08d}\n')
        h.execute(m.b,'timeout','20','python3','-c',
            'import pathlib,sys,hashlib\np=pathlib.Path(sys.argv[1]);p.mkdir(exist_ok=True)\n'
            'g=int(sys.argv[2])\n'
            'for name in ["a","b"]:(p/name).write_bytes((f"generation:{g:08d}\\n").encode()+hashlib.shake_256(f"{g}:{name}".encode()).digest(8*1024*1024))',
            m.p('target'),str(generation),wall=25)
    with h.Env():
        m=h.mount(h.B1,'crash')
        h.put(m,'.gitignore','node_modules/\ntarget/\n')
        h.execute(h.B1,'timeout','115','python3','-c','import shutil,sys;shutil.copytree("/fixture/node_modules",sys.argv[1]+"/node_modules")',m.path,wall=120)
        prepare(m,0); h.commit(m)
        record(dict(kind='setup',fixture=json.loads((WORK/'fixture.json').read_text()),delays_ms=delays))
        for cycle, delay in enumerate(delays,1):
            row=dict(cycle=cycle,delay_ms=delay,result='FAIL')
            try:
                prepare(m,cycle)
                # Change only the NEXT process incarnation's paths before kill.
                h.execute(h.B1,'sed','-i','-e',f's|^overlay=.*|overlay=/state/overlay-{cycle}/template.sqlite|','-e',f's|^mounts=.*|mounts=/workspaces-{cycle}|','/state/daemon.setup')
                h.execute(h.B1,'rm','-f','/state/commit.pid')
                h.execute(h.B1,'mv','/state/daemon.log',f'/state/daemon-cycle-{cycle}.log')
                script='echo $$ > /state/commit.pid; exec timeout 25 /opt/lfs/layerfs-remote /state/daemon.setup commit "$1" "$2"'
                p=subprocess.Popen(['docker','--context','orbstack','exec',h.B1,'bash','-c',script,'bash',m.ws,str(m.ns)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
                # Observe a live CLI process before applying the chosen delay.
                h.execute(h.B1,'timeout','3','bash','-c','while ! test -s /state/commit.pid; do sleep .001; done',wall=5)
                time.sleep(delay/1000)
                row['client_finished_before_kill']=p.poll() is not None
                h.docker('kill','--signal','KILL',h.B1)
                stdout,_=p.communicate(timeout=30)
                row.update(commit_exit=p.returncode,commit_output=stdout)
                h.docker('cp',f'{h.B1}:/state/daemon-cycle-{cycle}.log',str(h.RECEIPTS/f'cycle-{cycle:02d}-killed.log'))
                h.docker('start',h.B1)
                h.ready(h.B1,'REMOTE_DAEMON_READY','/state/daemon.log')
                # A fresh log plus actual control creation prove this incarnation opened the cache.
                t=time.monotonic_ns();m=h.mount(h.B1,'crash');row['restore_outer_ns']=time.monotonic_ns()-t
                stats=h.ctl(h.B1,'stats').stdout;row['stats_after_restore']=stats
                validation=h.execute(h.B1,'timeout','20','python3','-c',
                    'import pathlib,sys,json,sqlite3,hashlib\n'
                    'p=pathlib.Path(sys.argv[1]);c=sqlite3.connect("file:/state/cache/objects.sqlite?mode=ro",uri=True)\n'
                    'pair=[]\n'
                    'for n in ["a","b"]:\n'
                    ' f=p/"target"/n;data=f.read_bytes() if f.exists() else None\n'
                    ' if data is None:pair.append(None);continue\n'
                    ' head,tail=data.split(b"\\n",1);g=int(head.split(b":")[1]);assert tail==hashlib.shake_256(f"{g}:{n}".encode()).digest(8*1024*1024);pair.append(g)\n'
                    'record=c.execute("SELECT body FROM restore_points WHERE key=?",("crash",)).fetchone()\n'
                    'print(json.dumps(dict(integrity=c.execute("PRAGMA quick_check").fetchone()[0],journal=c.execute("PRAGMA journal_mode").fetchone()[0],generation=pair,record_sha=hashlib.sha256(record[0]).hexdigest() if record else None)))',m.path,wall=25)
                facts=json.loads(validation.stdout);row.update(facts)
                assert facts['integrity']=='ok' and facts['journal']=='wal',facts
                if 'Text("restored")' in stats or 'String("restored")' in stats:
                    assert facts['generation'][0]==facts['generation'][1] and 0<=facts['generation'][0]<=cycle,facts
                else:
                    assert any(reason in stats for reason in ['missing-local-objects','invalid-local-objects','invalid-record','validation-unavailable','not-found']),stats
                    assert facts['generation']==[None,None],facts
                result,ns,outer=h.commit(m);row.update(next_commit=result,next_ns=ns)
                first=json.load(gzip.open(MANIFEST,'rt'))[0]['path']
                assert h.server_read('/'+first) is None
                assert h.server_read('/target/a') is None and h.server_read('/target/b') is None
                assert h.server_read('/tracked.txt')==h.cat(m,'tracked.txt')
                row['result']='PASS'
                h.execute(h.B1,'rm','-f','/state/commit.pid')
            except Exception as e:
                row['error']=repr(e)
            record(row)
        h.try_unmount('kill-loop',m,discard=True)

if __name__=='__main__':
    if sys.argv[1]=='fixture': fixture()
    elif sys.argv[1]=='seal': seal(sys.argv[2],sys.argv[3])
    elif sys.argv[1]=='measure': measure(sys.argv[2])
    elif sys.argv[1]=='kill-loop': kill_loop()
    else: raise ValueError(sys.argv)
