#!/usr/bin/env python3
"""Owned Linux-container diagnostics; phase is seed, cycles, or measure."""
import hashlib, json, os, pathlib, re, shutil, subprocess, sys, time
ROOT=pathlib.Path.home()/'lfs-remote/mp2-remote-store'
HOME=ROOT/'phase3'; HOME.mkdir(exist_ok=True)
PHASE=sys.argv[1]; MODE=PHASE.split('-')[0]; OUT=HOME/PHASE; OUT.mkdir() # never overwrite a receipt
D='/usr/local/bin/docker'; IMAGE='mp2-p3-tools'
A,B='mp2-p3-a','mp2-p3-b'; NA,NB,LINK='mp2-p3-a-net','mp2-p3-b-net','mp2-p3-link'
SEED='mp2-p3-seed'; INPUT='mp2-p3-input'; VA,VB='mp2-p3-a-data','mp2-p3-b-data'
BIN=HOME/'bin'; BIN.mkdir(exist_ok=True); CFG=HOME/'config'; CFG.mkdir(exist_ok=True)
REPORT=OUT/'commands.jsonl'; RESULTS=OUT/'results.jsonl'
def record(path,value):
    with path.open('a') as f:f.write(json.dumps(value)+'\n')
def run(args,wall=120,check=True):
    start=time.monotonic_ns()
    try:
        p=subprocess.run(list(map(str,args)),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=wall)
        result=dict(command=list(map(str,args)),exit=p.returncode,ns=time.monotonic_ns()-start,output=p.stdout)
    except subprocess.TimeoutExpired as e:
        result=dict(command=list(map(str,args)),exit='TIMEOUT',ns=time.monotonic_ns()-start,output=str(e.stdout))
    record(REPORT,result)
    if check:assert result['exit']==0,result
    return result

def docker(*args,**kw):return run([D,*args],**kw)
def ex(c,*args,**kw):return docker('exec',c,*args,**kw)
def ctl(op,m=None):
    return ex(B,'timeout','25','/bin-lfs/layerfs-remote','/state/control.setup',op,*(m[1:] if m else []),wall=27)
def mount():
    r=ex(B,'timeout','25','/bin-lfs/layerfs-remote','/state/control.setup','mount',(CFG/'branch').read_text(),wall=27)
    m=re.search(r'path=(\S+) workspace=(\S+) namespace=(\d+)',r['output']);assert m,r
    return m.groups(),r

def stats(native):
    if native:return dict(roundTrips=0,uploadedObjects=0,uploadedBytes=0)
    s=ctl('stats')['output'];return {k:int(v) for k,v in re.findall(r'\("(roundTrips|uploadedObjects|uploadedBytes)", Int\((\d+)\)\)',s)}
def ready(c,path,marker):
    end=time.monotonic()+15
    while time.monotonic()<end:
        p=subprocess.run([D,'exec',c,'cat',path],text=True,capture_output=True,timeout=2)
        if marker in p.stdout:return
        time.sleep(.05)
    raise AssertionError((c,path,p.stdout,p.stderr))
def cleanup():
    for c in [B,A]:
        subprocess.run([D,'cp',c+':/state/daemon.log',str(OUT/(c+'-last.log'))],capture_output=True,timeout=5)
        docker('rm','-f',c,check=False)
    for v in [VB,VA]:docker('volume','rm',v,check=False)
    for n in [LINK,NB,NA]:docker('network','rm',n,check=False)
def startup(native,delay):
    for n in [NA,NB,LINK]:docker('network','create','--internal',n)
    for v in [VA,VB]:docker('volume','create',v)
    docker('run','--rm','--name','mp2-p3-clone','-v',SEED+':/seed:ro','-v',VA+':/a','-v',VB+':/b','-v',str(CFG)+':/cfg:ro',IMAGE,'bash','-c','cp -a /seed/. /a/; chmod 700 /a /b; cp /cfg/b1.setup /b/control.setup')
    # A owns the only remote Store. B receives it solely for the native baseline.
    if native:
        docker('run','--rm','--name','mp2-p3-native-clone','-v',SEED+':/seed:ro','-v',VB+':/state','-v',str(CFG)+':/cfg:ro',IMAGE,'bash','-c','cp -a /seed/store /state/; chmod 700 /state/store; chmod 600 /state/store/store.sqlite; cp /cfg/native.setup /state/native.setup')
    docker('run','-d','--name',A,'--network',NA,'--cap-add','NET_ADMIN','-v',VA+':/state','-v',str(BIN)+':/bin-lfs:ro','-e','LAYERFS_CONSTRUCTION_WORKERS=1',IMAGE,'bash','-c','exec /bin-lfs/layerfs-store --config /state/server.setup > /state/daemon.log 2>&1')
    docker('network','connect','--alias','store',LINK,A);ready(A,'/state/daemon.log','REMOTE_STORE_READY')
    address=json.loads(docker('inspect',A)['output'])[0]['NetworkSettings']['Networks'][LINK]['IPAddress']
    docker('run','-d','--name',B,'--init','--network',LINK,'--device','/dev/fuse','--cap-add','SYS_ADMIN','--cap-add','SYS_PTRACE','--cap-add','NET_ADMIN','--security-opt','apparmor=unconfined','--security-opt','no-new-privileges=true','-v',VB+':/state','-v',INPUT+':/input:ro','-v',str(BIN)+':/bin-lfs:ro','-e','LAYERFS_CONSTRUCTION_WORKERS=1',IMAGE,'sleep','infinity')
    docker('network','connect',NB,B)
    ex(B,'bash','-c','taskset -c 0 python3 /bin-lfs/tcp-cut.py > /state/proxy.log 2>&1 &')
    ready(B,'/state/proxy.log','PROXY_READY')
    docker('exec','-d',B,'taskset','-c','0','nice','-n','19','python3','-c','import os\nwhile True: os.sched_yield()')
    if delay:ex(B,'tc','qdisc','add','dev','eth0','root','netem','delay',str(delay)+'ms')
    ex(B,'timeout','8','taskset','-c','0','ping','-n','-c','5','-i','0.1',address,wall=10)
    exe='layerfs-daemon' if native else 'layerfs-remote-daemon';cfg='native.setup' if native else 'control.setup'
    ex(B,'bash','-c','/bin-lfs/'+exe+' --config /state/'+cfg+' > /state/daemon.log 2>&1 & echo $! > /state/pid')
    if native:
        # Application readiness has no stdout marker: wait only for the listening socket.
        ex(B,'timeout','10','bash','-c','until grep -q "1E79.*0A" /proc/net/tcp; do sleep .05; done')
    else:ready(B,'/state/daemon.log','REMOTE_DAEMON_READY')
    return address
PROBE='''import os,glob,json
p='/proc/'+open('/state/pid').read().strip()
print(json.dumps(dict(threads=len(glob.glob(p+'/task/*')),fds=sorted(os.readlink(f) for f in glob.glob(p+'/fd/*')))))'''
try:
    if MODE=='seed':
        for name in ['layerfs-store','layerfs-remote','layerfs-remote-daemon','layerfs-daemon']:
            shutil.copy2(ROOT/'source/target-remote/debug'/name,BIN/name)
        shutil.copy2(ROOT/'source/docs/mp2/tcp-cut.py',BIN/'tcp-cut.py')
        shutil.copy2(ROOT/'source/target-remote/debug/deps'/(ROOT/'driver-path').read_text().strip(),BIN/'driver')
        for v in [SEED,INPUT]:docker('volume','create',v)
        docker('run','--rm','--name','mp2-p3-seed','-v',str(BIN)+':/bin-lfs:ro','-v',str(CFG)+':/out','-v',SEED+':/state','-v','lfs-src:/original:ro','-e','LFS_MODE=init','-e','LFS_SOURCE=/original/dubbo','-e','LAYERFS_CONSTRUCTION_WORKERS=1',IMAGE,'timeout','120','/bin-lfs/driver','--ignored','--exact','drive','--nocapture')
        docker('run','--rm','--name','mp2-p3-input','-v',INPUT+':/input','-v',str(ROOT/'phase3-work')+':/work:ro',IMAGE,'bash','-c','cp -a /work/full /work/delta /input/')
        for p in BIN.iterdir():
            saved=HOME/'artifacts'/hashlib.sha256(p.read_bytes()).hexdigest()/p.name
            saved.parent.mkdir(parents=True,exist_ok=True)
            if not saved.exists():shutil.copy2(p,saved)
        record(RESULTS,dict(binaries={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in BIN.iterdir()},image=docker('image','inspect',IMAGE,'--format','{{.Id}}')['output']))
    elif MODE=='cycles':
        startup(False,0);initial=json.loads(ex(B,'python3','-c',PROBE)['output'])
        for i in range(10):
            m,_=mount();ex(B,'python3','-c','import pathlib,sys;pathlib.Path(sys.argv[1]).write_text(sys.argv[2])',m[0]+'/cycle',str(i));ctl('commit',m);r=ctl('unmount',m)
            assert 'Unmounted(' in r['output'],r
            state=json.loads(ex(B,'python3','-c',PROBE)['output']);assert state==initial,(state,initial)
            record(RESULTS,dict(cycle=i+1,unmount=r,state=state))
        pid=ex(B,'cat','/state/pid')['output'].strip();ex(B,'kill',pid)
        ex(B,'timeout','5','bash','-c','while test -d /proc/'+pid+'; do sleep .05; done')
        ex(B,'ss','-tnlp');ex(B,'ss','-tnp');record(RESULTS,dict(stopped=True))
    elif MODE=='calibrate':
        address=startup(False,0)
        for delay in [1,2,20]:
            ex(B,'tc','qdisc','replace','dev','eth0','root','netem','delay',str(delay)+'ms')
            r=ex(B,'timeout','8','taskset','-c','0','ping','-n','-c','20','-i','0.01',address,wall=10)
            record(RESULTS,dict(delay=delay,reply=r['output']))
        ex(B,'tc','qdisc','del','dev','eth0','root')
        m,_=mount();r=ex(B,'timeout','25','git','-c','safe.directory=*','-C',m[0],'--no-optional-locks','status','--short',wall=27)
        record(RESULTS,dict(unshaped_git_ns=r['ns']));ctl('unmount',m)
    elif MODE=='measure':
        for native,delay in [(False,0),(False,2),(False,20),(True,0)]:
            for rep in range(1,4):
                try:
                    address=startup(native,delay if delay!=20 else 0);before=stats(native);m,mr=mount();after=stats(native)
                    gr=ex(B,'timeout','25','git','-c','safe.directory=*','-C',m[0],'--no-optional-locks','status','--short',wall=27)
                    record(RESULTS,dict(kind='cold-mount-status',native=native,rtt=(0 if delay==20 else delay),rep=rep,commit_rtt=delay,mount=mr,git=gr,mount_requests=after['roundTrips']-before['roundTrips'],git_requests=stats(native)['roundTrips']-after['roundTrips']))
                    if delay==20:
                        ex(B,'tc','qdisc','add','dev','eth0','root','netem','delay','20ms')
                        ex(B,'timeout','8','taskset','-c','0','ping','-n','-c','20','-i','0.01',address,wall=10)
                    for label in ['full','delta']:
                        ex(B,'timeout','120','cp','-a','--no-preserve=ownership','/input/'+label+'/.',m[0]+'/')
                        before=stats(native);r=ctl('commit',m);after=stats(native)
                        assert any(x in r['output'] for x in ['Committed(', 'MergeCommitted(']),r
                        record(RESULTS,dict(kind=label,native=native,rtt=delay,rep=rep,wall_ns=int(re.search(r'wall_ns=(\d+)',r['output'])[1]),command_ns=r['ns'],metrics={k:after[k]-before[k] for k in before},reply=r['output']))
                    ctl('unmount',m)
                except Exception as e:
                    record(RESULTS,dict(native=native,rtt=delay,rep=rep,error=str(e)));raise
                finally:cleanup()
    else:raise AssertionError(PHASE)
finally:
    if MODE in ['cycles','calibrate']:cleanup()
