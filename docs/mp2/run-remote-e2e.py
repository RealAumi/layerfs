#!/usr/bin/env python3
"""Owned-container proof. Run on remote-host from ~/lfs-remote/mp2-remote-store/."""
import concurrent.futures, hashlib, json, os, pathlib, re, subprocess, time, sys
PHASE = sys.argv[1] if len(sys.argv) == 2 else "faults"
assert PHASE in ["diagnostic", "refresh", "races", "faults"]
ROOT = pathlib.Path.home()/'lfs-remote/mp2-remote-store'
DOCKER = '/usr/local/bin/docker'
IMAGE = 'public.ecr.aws/docker/library/rust:1.85.1-bookworm'
A, B1, B2 = 'mp2-lfs-a', 'mp2-lfs-b1', 'mp2-lfs-b2'
NET_A, NET_B, LINK = 'mp2-lfs-server-net', 'mp2-lfs-sandbox-net', 'mp2-lfs-link'
VOLUMES = ['mp2-lfs-server-data', 'mp2-lfs-b1-data', 'mp2-lfs-b2-data']
BIN, SEED = ROOT/'bin', ROOT/'seed'
REPORT = ROOT/'e2e-receipts.jsonl'
assert not REPORT.exists(), 'append-only run: existing receipt must be retained'
BIN.mkdir(exist_ok=True); SEED.mkdir(exist_ok=True)
def run(args, expected=0, wall=120, env=None):
    before=time.monotonic_ns()
    p=subprocess.run([str(x) for x in args], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=wall, env=env)
    with REPORT.open('a') as f: f.write(json.dumps(dict(command=[str(x) for x in args], exit=p.returncode, wall_ns=time.monotonic_ns()-before, output=p.stdout))+'\n')
    if expected is not None: assert p.returncode==expected, (args,p.returncode,p.stdout[-5000:])
    return p.stdout

def docker(*args,**kw):return run([DOCKER,*args],**kw)
def execute(container,*args,**kw):return docker('exec',container,*args,**kw)
def ready(container, marker, path):
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        p=subprocess.run([DOCKER,'exec',container,'cat',path],capture_output=True,text=True,timeout=2)
        if marker in p.stdout:return
        time.sleep(.1)
    raise AssertionError((container,marker,p.stdout,p.stderr))
def driver(mode,path=None,text=None,expect=None):
    args=['exec','-e','LFS_MODE='+mode]
    for key,value in [('LFS_PATH',path),('LFS_TEXT',text),('LFS_EXPECT',expect)]:
        if value is not None:args+=['-e',key+'='+value]
    return docker(*args,A,'timeout','120','/opt/lfs/remote_driver','--ignored','--exact','drive','--nocapture')
def ctl(b,op,*args,expected=0):return execute(b,'timeout','110','/opt/lfs/layerfs-remote','/state/daemon.setup',op,*args,expected=expected)
def mount(b):
    text=ctl(b,'mount',(SEED/'branch').read_text())
    match=re.search(r'path=(\S+) workspace=(\S+) namespace=(\d+)',text);assert match,text
    return match.groups()
def commit(b,m,expected=0):return ctl(b,'commit',m[1],m[2],expected=expected)
def unmount(b,m,discard=False):return ctl(b,'unmount',m[1],m[2],*(['discard'] if discard else []))
def write(b,m,path,text):
    return execute(b,'python3','-c','import pathlib,sys;pathlib.Path(sys.argv[1]).write_text(sys.argv[2])',m[0]+'/'+path,text)
def cat(b,m,path,expect):
    text=execute(b,'timeout','10','cat',m[0]+'/'+path);assert text==expect,(path,text,expect)
def stats(b):
    text=ctl(b,'stats');match=re.search(r'roundTrips.*?Int\((\d+)\)',text);assert match,text;return int(match[1])
def tree(path):
    return {p.relative_to(path).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in path.rglob('*') if p.is_file()}
owned=[]; nets=[]; volumes=[]
try:
    for n in [NET_A,NET_B,LINK]:docker('network','create','--internal',n);nets.append(n)
    for v in VOLUMES:docker('volume','create',v);volumes.append(v)
    # Source and Store files never enter B: only these executables and the probe.
    for name in ['layerfs-store','layerfs-remote','layerfs-remote-daemon']:
        import shutil
        shutil.copy2(ROOT/'source/target-remote/debug'/name,BIN/name)
    driver_binary=ROOT/'source/target-remote/debug/deps'/(ROOT/'driver-path').read_text().strip()
    assert driver_binary.is_file() and os.access(driver_binary,os.X_OK),driver_binary
    shutil.copy2(driver_binary,BIN/'remote_driver')
    shutil.copy2(ROOT/'source/docs/mp2/tcp-cut.py',BIN/'tcp-cut.py')
    docker('run','--rm','--name','mp2-lfs-init','--network',NET_A,'-v',str(BIN)+':/opt/lfs:ro','-v',str(SEED)+':/out','-v',VOLUMES[0]+':/state','-e','LFS_MODE=init','-e','LAYERFS_CONSTRUCTION_WORKERS=1',IMAGE,'timeout','120','/opt/lfs/remote_driver','--ignored','--exact','drive','--nocapture')
    docker('run','-d','--name',A,'--init','--network',NET_A,'-v',str(BIN)+':/opt/lfs:ro','-v',VOLUMES[0]+':/state','-e','LAYERFS_CONSTRUCTION_WORKERS=1',IMAGE,'bash','-c','exec /opt/lfs/layerfs-store --config /state/server.setup > /state/server.log 2>&1');owned.append(A)
    docker('network','connect','--alias','store',LINK,A)
    ready(A,'REMOTE_STORE_READY','/state/server.log')
    for b,v,cfg in [(B1,VOLUMES[1],'b1.setup'),(B2,VOLUMES[2],'b2.setup')]:
        docker('run','--rm','--name','mp2-lfs-seed','--network',NET_B,'-v',str(SEED)+':/seed:ro','-v',v+':/state',IMAGE,'bash','-c','cp /seed/'+cfg+' /state/daemon.setup; chmod 700 /state; chown 0:0 /state/daemon.setup; chmod 600 /state/daemon.setup')
        docker('run','-d','--name',b,'--init','--network',LINK,'--device','/dev/fuse','--cap-add','SYS_ADMIN','--cap-add','SYS_PTRACE','--security-opt','apparmor=unconfined','--security-opt','no-new-privileges=true','-v',str(BIN)+':/opt/lfs:ro','-v',v+':/state','-e','LAYERFS_CONSTRUCTION_WORKERS=1',IMAGE,'bash','-c','python3 /opt/lfs/tcp-cut.py > /state/proxy.log 2>&1 & while ! grep -q PROXY_READY /state/proxy.log; do sleep 0.05; done; exec /opt/lfs/layerfs-remote-daemon --config /state/daemon.setup > /state/daemon.log 2>&1');owned.append(b)
        docker('network','connect',NET_B,b)
        ready(b,'REMOTE_DAEMON_READY','/state/daemon.log')
        execute(b,'bash','-c','for p in /proc/[0-9]*/ns/mnt; do printf "%s " "$p"; readlink "$p"; done')
    before=time.monotonic_ns();m1=mount(B1);mount_wall=time.monotonic_ns()-before
    if PHASE == 'diagnostic':
        after_mount=stats(B1)
        ls=execute(B1,'timeout','15','python3','-c','import subprocess,time,sys; t=time.monotonic_ns();p=subprocess.run(["ls","-R",sys.argv[1]],stdout=subprocess.PIPE,check=True);print(time.monotonic_ns()-t);print(len(p.stdout))',m1[0])
        result=dict(files=3003,mount_rtt=after_mount,mount_command_wall_ns=mount_wall,ls_rtt=stats(B1)-after_mount,ls_output=ls,cache='empty B cache before mount; mandatory bind pages reused by ls; server/OS cache not cold-qualified')
        (ROOT/'diagnostic.json').write_text(json.dumps(result,indent=2))
        driver('oracle');docker('cp',A+':/state/oracle',ROOT/'oracle-a')
        execute(B1,'timeout','30','cp','-a',m1[0],'/state/oracle');docker('cp',B1+':/state/oracle',ROOT/'oracle-b')
        assert tree(ROOT/'oracle-a')==tree(ROOT/'oracle-b')
    if PHASE == 'refresh':
        cat(B1,m1,'server','server base\n');driver('write','/server','server clean\n');commit(B1,m1);cat(B1,m1,'server','server clean\n')
        write(B1,m1,'local','local changed\n');driver('write','/server','server dirty\n');commit(B1,m1);cat(B1,m1,'server','server dirty\n');cat(B1,m1,'local','local changed\n');driver('read','/local',expect='local changed\n')
        execute(B1,'timeout','10','touch',m1[0]+'/root-created');write(B1,m1,'root-created','root writes\n');cat(B1,m1,'root-created','root writes\n');assert execute(B1,'stat','-c','%u:%g',m1[0]+'/root-created').strip()=='1000:1000'
        execute(B1,'timeout','10','bash','-c','printf "failed but kept\n" > "$1/failing"; exit 7','bash',m1[0],expected=7);commit(B1,m1);driver('read','/failing',expect='failed but kept\n')
        unmount(B1,m1) # A retained Join is a failed proof, never a retry.
    if PHASE == 'races':
        write(B1,m1,'fresh','published before fresh mount\n');commit(B1,m1)
        m1=mount(B1);cat(B1,m1,'fresh','published before fresh mount\n')
        m2=mount(B2);write(B1,m1,'race','A0\nb0\nc0\nd0\ne0\n');write(B2,m2,'race','a0\nb0\nc0\nd0\nE0\n')
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda item:commit(*item),[(B1,m1),(B2,m2)]))
        assert all('Conflict(' not in r for r in results),results
        driver('read','/race',expect='A0\nb0\nc0\nd0\nE0\n');commit(B1,m1);commit(B2,m2)
        write(B1,m1,'race','X0\nb0\nc0\nd0\nE0\n');write(B2,m2,'race','Y0\nb0\nc0\nd0\nE0\n')
        before_history=driver('history')
        with concurrent.futures.ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda item:commit(*item),[(B1,m1),(B2,m2)]))
        assert sum('Conflict(' in r for r in results)==1,results
        after_history=driver('history')
        count=lambda text:int(re.search(r'HISTORY (\d+)',text)[1])
        assert count(after_history)==count(before_history)+1
        loser=(B1,m1) if 'Conflict(' in results[0] else (B2,m2)
        assert '<<<<<<<' in execute(loser[0],'cat',loser[1][0]+'/race')
        write(*loser,'race','resolved\nb0\nc0\nd0\nE0\n');commit(*loser)
    if PHASE == 'faults':
        m2=mount(B2)
        driver('write','/cold-read','cold server payload\n');commit(B1,m1);commit(B2,m2)
        for b in [B1,B2]:
            mounts=json.loads(docker('inspect',b))[0]['Mounts'];assert all(m['Name']!=VOLUMES[0] for m in mounts if m['Type']=='volume')
            execute(b,'test','!','-e','/state/store/store.sqlite')
            fds=execute(b,'python3','-c','import os,glob;print(chr(10).join(sorted({os.readlink(f) for f in glob.glob("/proc/[0-9]*/fd/*") if os.path.islink(f) and ".sqlite" in os.readlink(f)})))')
            assert '/state/store/' not in fds and 'store.sqlite' not in fds,fds
        execute(B1,'touch','/state/cut-read');failed=execute(B1,'timeout','15','cat',m1[0]+'/cold-read',expected=1);assert 'Input/output error' in failed,failed
        execute(B2,'python3','-c','import os,sys;open(sys.argv[1],"wb").write(os.urandom(5*1024*1024))',m2[0]+'/upload-cut')
        head=driver('head');execute(B2,'touch','/state/cut-write');failed=commit(B2,m2,expected=1);assert 'Unknown' in failed,failed
        assert driver('head').split('HEAD ')[1].splitlines()[0]==head.split('HEAD ')[1].splitlines()[0]
        counts=stats(B2);commit(B2,m2,expected=1);assert stats(B2)==counts
        for b in [B1,B2]:
            events=execute(b,'cat','/state/cut-events.jsonl');assert events
            assert len(execute(b,'cat','/state/connections.jsonl').splitlines())==2
    print('PASS remote E2E phase '+PHASE,flush=True)
finally:
    for b in owned:
        for name in ['server.log','daemon.log','proxy.log','cut-events.jsonl']:
            subprocess.run([DOCKER,'cp',b+':/state/'+name,str(ROOT/(b+'-'+name))],capture_output=True,timeout=10)
        docker('rm','-f',b,expected=None)
    for v in volumes:docker('volume','rm',v,expected=None)
    for n in reversed(nets):docker('network','rm',n,expected=None)
