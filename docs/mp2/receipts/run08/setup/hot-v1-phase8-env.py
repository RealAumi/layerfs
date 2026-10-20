"""Local Docker operation helpers. Never execute on a remote host."""
import pathlib,json,subprocess,time,re,os
REPO=pathlib.Path(__file__).resolve().parents[2];WORK=REPO/'target/cx7/phase8';ROOT=REPO/'docs/mp2/receipts/run08';IMAGE='cx7-p8-tools';INPUT='cx7-p8-input';COMMON=REPO/'target/cx7/bin-after'
class Env:
    def __init__(self,out,variant='hot',arm='after',tag='b',delay=0,raw=False):
        self.out=out;self.variant=variant;self.arm=arm;self.tag=tag;self.delay=delay;self.seed='cx7-p8-'+('raw-' if raw else 'seed-')+variant
        self.a='cx7-p8-a-'+tag;self.b='cx7-p8-b-'+tag;self.va=self.a+'-data';self.vb=self.b+'-data';self.nets=['cx7-p8-a-net-'+tag,'cx7-p8-b-net-'+tag,'cx7-p8-link-'+tag];self.m=None
    def run(self,args,check=True,wall=30):
        start=time.monotonic_ns()
        try:
            p=subprocess.run(list(map(str,args)),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=wall);r=dict(command=list(map(str,args)),exit=p.returncode,ns=time.monotonic_ns()-start,output=p.stdout)
        except subprocess.TimeoutExpired as e:r=dict(command=list(map(str,args)),exit='TIMEOUT',ns=time.monotonic_ns()-start,output=(e.stdout or b'').decode(errors='replace'))
        with (self.out/'commands.jsonl').open('a') as f:f.write(json.dumps(r)+'\n')
        if check:assert r['exit']==0,r
        return r
    def d(self,*a,**kw):return self.run(['docker',*a],**kw)
    def ex(self,*a,user=None,**kw):return self.d('exec',*(['--user',user] if user else []),self.b,*a,**kw)
    def ready(self,c,path,marker):
        until=time.monotonic()+15
        while time.monotonic()<until:
            if marker in self.d('exec',c,'cat',path,check=False)['output']:return
            time.sleep(.05)
        raise RuntimeError('readiness deadline '+c)
    def start(self):
        for n in self.nets:self.d('network','create','--internal',n)
        for v in [self.va,self.vb]:self.d('volume','create',v)
        self.d('run','--rm','--name','cx7-p8-copy-'+self.tag,'-v',self.seed+':/seed:ro','-v',self.va+':/a','-v',self.vb+':/b','-v',str(WORK/'config'/self.variant)+':/cfg:ro',IMAGE,'bash','-c','cp -a /seed/. /a/; cp /cfg/b1.setup /b/daemon.setup; chmod 700 /a /b; chmod 600 /b/daemon.setup')
        self.d('run','-d','--name',self.a,'--init','--network',self.nets[0],'-v',self.va+':/state','-v',str(COMMON)+':/bin-lfs:ro','-e','LAYERFS_CONSTRUCTION_WORKERS=1',IMAGE,'bash','-c','exec /bin-lfs/layerfs-store --config /state/server.setup > /state/server.log 2>&1')
        self.d('network','connect',self.nets[2],self.a);self.ready(self.a,'/state/server.log','REMOTE_STORE_READY')
        self.ip=self.d('inspect','--format','{{(index .NetworkSettings.Networks "'+self.nets[2]+'").IPAddress}}',self.a)['output'].strip()
        self.d('run','--rm','--name','cx7-p8-config-'+self.tag,'-v',self.vb+':/state',IMAGE,'sed','-i','s/^server=.*/server='+self.ip+':7800/','/state/daemon.setup')
        self.d('run','-d','--name',self.b,'--init','--network',self.nets[2],'--device','/dev/fuse','--cap-add','SYS_ADMIN','--cap-add','SYS_PTRACE','--cap-add','NET_ADMIN','--security-opt','apparmor=unconfined','-v',self.vb+':/state','-v',INPUT+':/input:ro','-v',str(COMMON)+':/bin-lfs:ro','-v',str(REPO/'target/cx7'/('bin-'+self.arm))+':/daemon:ro','-v',str(WORK/'bin')+':/observe:ro','-v',str(REPO/'docs/mp2')+':/harness:ro','-e','LAYERFS_CONSTRUCTION_WORKERS=1',IMAGE,'sleep','infinity')
        self.d('network','connect',self.nets[1],self.b)
        if self.delay:self.ex('tc','qdisc','add','dev','eth0','root','netem','delay',str(self.delay)+'ms')
        self.ex('timeout','8','ping','-n','-c','5','-i','.1',self.ip,wall=10)
        self.ex('bash','-c','mkdir -p /sys/fs/fuse/connections; mount -t fusectl none /sys/fs/fuse/connections; /daemon/layerfs-remote-daemon --config /state/daemon.setup > /state/daemon.log 2>&1 & echo $! > /state/pid')
        self.ready(self.b,'/state/daemon.log','REMOTE_DAEMON_READY')
    def ctl(self,op,*args,**kw):return self.ex('timeout','25','/bin-lfs/layerfs-remote','/state/daemon.setup',op,*args,wall=28,**kw)
    def mount(self):
        r=self.ctl('mount',(WORK/'config'/self.variant/'branch').read_text().strip());m=re.search(r'path=(\S+) workspace=(\S+) namespace=(\d+)',r['output']);assert m,r;self.m=m.groups();return r
    def stats(self):return {k:int(v) for k,v in re.findall(r'\("(roundTrips|uploadedObjects|uploadedBytes)", Int\((\d+)\)\)',self.ctl('stats')['output'])}
    def fuse(self):
        r=self.d('exec','-e','LFS_WS='+self.m[1],'-e','LFS_NS='+self.m[2],self.b,'timeout','8','/observe/receive_observe','--ignored','--exact','observe','--nocapture',wall=10)
        return {k:int(v) for k,v in re.findall(r'(\w+): (\d+)',r['output'].split('FUSE_WORK ')[1].split('\n')[0])}
    def git(self,*args,refresh=False,**kw):
        path=self.m[0]+('/dubbo' if self.variant=='hot' else '')
        return self.ex('timeout','110','git','-c','safe.directory=*','-C',path,*([] if refresh else ['--no-optional-locks']),*args,wall=115,**kw)
    def unmount(self,discard=False):
        r=self.ctl('unmount',*self.m[1:],*(['discard'] if discard else []),check=False)
        if r['exit']!=0:
            p=self.out/('unmount-'+self.tag);p.mkdir(exist_ok=True)
            x=self.ex('timeout','15','python3','/harness/phase7-probe.py',check=False,wall=20);(p/'processes.json').write_text(x['output'])
        return r
    def cleanup(self):
        for c,f in [(self.a,'server.log'),(self.b,'daemon.log')]:self.d('cp',c+':/state/'+f,str(self.out/(c+'-'+f)),check=False)
        for c in [self.b,self.a]:self.d('rm','-f',c,check=False)
        for v in [self.vb,self.va]:self.d('volume','rm',v,check=False)
        for n in reversed(self.nets):self.d('network','rm',n,check=False)
def record(out,value):
    with (out/'results.jsonl').open('a') as f:f.write(json.dumps(value)+'\n')
