#!/usr/bin/env python3
"""Local-only, append-only unmount rate experiment; exact same harness per arm."""
import hashlib,json,os,pathlib,re,subprocess,sys,time
REPO=pathlib.Path(__file__).resolve().parents[2];WORK=REPO/'target/cx7';ROOT=REPO/'docs/mp2/receipts/run08'
IMAGE='cx7-tools';A='cx7-a';B='cx7-b';VA='cx7-a-data';VB='cx7-b-data';SEED='cx7-seed';NETS=['cx7-server','cx7-sandbox','cx7-link']
mode=sys.argv[1];arm=sys.argv[2] if len(sys.argv)>2 else 'before';BIN=WORK/('bin-'+arm);CFG=WORK/'config';OUT=ROOT/(mode+'-'+arm);OUT.mkdir(exist_ok=False)
LOG=OUT/'commands.jsonl';RESULT=OUT/'results.jsonl'
def record(p,v):
    with p.open('a') as f:f.write(json.dumps(v)+'\n')
def run(args,check=True,wall=30):
    start=time.monotonic_ns()
    try:
        p=subprocess.run([str(a) for a in args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=wall)
        r=dict(command=[str(a) for a in args],exit=p.returncode,ns=time.monotonic_ns()-start,output=p.stdout)
    except subprocess.TimeoutExpired as e:
        r=dict(command=[str(a) for a in args],exit='TIMEOUT',ns=time.monotonic_ns()-start,output=(e.stdout or b'').decode(errors='replace'))
    record(LOG,r)
    if check:assert r['exit']==0,r
    return r
def d(*args,**kw):return run(['docker',*args],**kw)
def ex(c,*args,**kw):return d('exec',c,*args,**kw)
def ready(c,path,marker):
    until=time.monotonic()+15
    while time.monotonic()<until:
        r=ex(c,'cat',path,check=False)
        if marker in r['output']:return
        time.sleep(.05)
    raise RuntimeError('readiness deadline '+c)
def ctl(op,*args):return ex(B,'timeout','25','/bin-lfs/layerfs-remote','/state/daemon.setup',op,*args,check=False,wall=28)
def capture(case):
    p=OUT/case;p.mkdir()
    for c,name in [(B,'daemon.log'),(B,'umount.trace'),(A,'server.log')]:d('cp',c+':/state/'+name,p/name,check=False)
    r=ex(B,'timeout','15','python3','/probe.py',wall=20,check=False);(p/'processes.json').write_text(r['output'])
    r=d('run','--rm','--name','cx7-observe','--pid=host','--cap-add','SYS_PTRACE','--cap-add','SYS_ADMIN','--security-opt','apparmor=unconfined','-v',str(REPO/'docs/mp2/phase7-probe.py')+':/probe.py:ro',IMAGE,'timeout','15','python3','/probe.py','namespaces',wall=20,check=False);(p/'namespaces.json').write_text(r['output'])
def cleanup_cycle():
    for c in [B,A]:d('rm','-f',c,check=False)
    for v in [VB,VA]:d('volume','rm',v,check=False)
def start():
    for v in [VA,VB]:d('volume','create',v)
    d('run','--rm','--name','cx7-copy','-v',SEED+':/seed:ro','-v',VA+':/state','-v',str(CFG)+':/cfg:ro','-v',VB+':/b',IMAGE,'bash','-c','cp -a /seed/. /state/; cp /cfg/b1.setup /b/daemon.setup; chmod 700 /b; chmod 600 /b/daemon.setup')
    d('run','-d','--name',A,'--init','--network',NETS[0],'-v',VA+':/state','-v',str(BIN)+':/bin-lfs:ro','-e','LAYERFS_CONSTRUCTION_WORKERS=1',IMAGE,'bash','-c','exec /bin-lfs/layerfs-store --config /state/server.setup > /state/server.log 2>&1')
    d('network','connect','--alias','store',NETS[2],A);ready(A,'/state/server.log','REMOTE_STORE_READY')
    ip=json.loads(d('inspect',A)['output'])[0]['NetworkSettings']['Networks'][NETS[2]]['IPAddress']
    d('run','--rm','--name','cx7-config','-v',VB+':/state',IMAGE,'sed','-i','s/^server=.*/server='+ip+':7800/','/state/daemon.setup')
    d('run','-d','--name',B,'--init','--network',NETS[2],'--device','/dev/fuse','--cap-add','SYS_ADMIN','--cap-add','SYS_PTRACE','--security-opt','apparmor=unconfined','-v',VB+':/state','-v',str(BIN)+':/bin-lfs:ro','-v',str(REPO/'docs/mp2/phase7-probe.py')+':/probe.py:ro','-e','LAYERFS_CONSTRUCTION_WORKERS=1',IMAGE,'bash','-c','mkdir -p /sys/fs/fuse/connections; mount -t fusectl none /sys/fs/fuse/connections; exec strace --seccomp-bpf -f -e trace=umount2 -o /state/umount.trace /bin-lfs/layerfs-remote-daemon --config /state/daemon.setup > /state/daemon.log 2>&1')
    d('network','connect',NETS[1],B);ready(B,'/state/daemon.log','REMOTE_DAEMON_READY')
    r=ctl('mount',(CFG/'branch').read_text().strip());assert r['exit']==0,r
    m=re.search(r'path=(\S+) workspace=(\S+) namespace=(\d+)',r['output']);assert m,r
    return m.groups()
def cycle(shape,i):
    label=f'{shape}-{i:02}';out=dict(case=label,shape=shape)
    try:
        path,ws,ns=start();out['mount']=dict(path=path,workspace=ws,namespace=ns)
        ex(B,'timeout','15','bash','-c','mkdir -p "$1/src"; printf "class A {}\\n" > "$1/src/A.java"; printf "build/\\n" > "$1/.gitignore"','bash',path,wall=18)
        if shape=='git':
            for args in [('init','-q'),('add','-A'),('commit','-q','-m','init')]:
                ex(B,'timeout','60','git','-c','safe.directory=*','-c','user.name=cx7','-c','user.email=cx7@example.invalid','-c','init.defaultBranch=main','-C',path,*args,wall=65)
        out['commit']=ctl('commit',ws,ns);assert out['commit']['exit']==0,out
        if shape=='held':
            ex(B,'bash','-c','timeout 90 python3 -c \'import time;f=open("'+path+'/local");open("/state/held.ready","w").write("ready");time.sleep(80)\' > /state/held.log 2>&1 &')
            ready(B,'/state/held.ready','ready')
        out['unmount']=ctl('unmount',ws,ns)
        # Preserve exact syscall flags and original reply even on success.
        out['umount_trace']=ex(B,'cat','/state/umount.trace')['output']
        out['retained_join']='Retained(' in out['unmount']['output'] and 'stage: Join' in out['unmount']['output']
        if out['unmount']['exit']!=0 or shape=='held':capture(label)
        else:
            out['remaining']=ex(B,'python3','-c','import glob,os,json;print(json.dumps({p:open(p+"/comm").read() for p in glob.glob("/proc/[0-9]*/task/*") if "layerfs-" in open(p+"/comm").read() or "fuser" in open(p+"/comm").read()}))')['output']
    except BaseException as e:
        out['error']=repr(e)
        try:capture(label+'-error')
        except BaseException as p:out['capture_error']=repr(p)
        raise
    finally:
        record(RESULT,out);print(label,'JOIN' if out.get('retained_join') else out.get('unmount',{}).get('exit',out.get('error')),flush=True);cleanup_cycle()
if mode=='seed':
    d('volume','create',SEED)
    d('run','--rm','--name','cx7-init','-v',str(BIN)+':/bin-lfs:ro','-v',str(CFG)+':/out','-v',SEED+':/state','-e','LFS_MODE=init','-e','LAYERFS_CONSTRUCTION_WORKERS=1',IMAGE,'timeout','120','/bin-lfs/remote_driver','--ignored','--exact','drive','--nocapture',wall=125)
    p=CFG/'b1.setup';p.write_text(p.read_text().replace('server=127.0.0.1:7900','server=store:7800'));p.chmod(0o600)
else:
    for n in NETS:d('network','create','--internal',n)
    record(OUT/'identity.jsonl',dict(head=run(['git','rev-parse','HEAD'])['output'].strip(),binaries={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in BIN.iterdir()},harness=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),image=d('image','inspect',IMAGE,'--format','{{.Id}}')['output']))
    try:
        if mode=='cycles':
            for i in range(1,41):cycle('git',i)
            cycle('plain',1)
        elif mode=='held':cycle('held',1)
        else:raise ValueError(mode)
    finally:
        for n in reversed(NETS):d('network','rm',n,check=False)
