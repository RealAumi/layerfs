#!/usr/bin/env python3
"""Count-only receive diagnosis, separately from performance samples."""
import importlib.util,pathlib,json,time
spec=importlib.util.spec_from_file_location('env',pathlib.Path(__file__).with_name('phase8-env.py'));h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
out=h.ROOT/'receive-diagnosis';out.mkdir(exist_ok=False)
for arm in ['before','after']:
    e=h.Env(out,arm=arm,tag=arm)
    try:
        e.start();e.mount();e.ex('timeout','115','python3','/harness/phase8-workload.py','prepare','stat',e.m[0],wall=120)
        code='import pathlib,json;p=pathlib.Path("/proc")/pathlib.Path("/state/pid").read_text().strip();print(json.dumps([int(t.name) for t in (p/"task").iterdir() if (t/"comm").read_text().startswith("fuser")]))'
        tids=json.loads(e.ex('python3','-c',code)['output']);assert len(tids)==2
        tracer=e.ex('bash','-c','strace -c -w -e trace=read,ppoll '+ ' '.join('-p '+str(t) for t in tids)+' -o /state/receive.counts 2>/state/trace.log & echo $!')['output'].strip()
        check='import pathlib,time,sys\nend=time.monotonic()+3\nwhile time.monotonic()<end:\n if all("TracerPid:\\t"+sys.argv[1]+"\\n" in pathlib.Path("/proc/"+t+"/status").read_text() for t in sys.argv[2:]):break\n time.sleep(.02)\nelse:raise RuntimeError("attach deadline")'
        e.ex('timeout','5','python3','-c',check,tracer,*map(str,tids),wall=7)
        f0=e.fuse();s0=e.stats();r=e.ex('timeout','115','python3','/harness/phase8-workload.py','measure','stat',e.m[0],wall=120);f1=e.fuse();s1=e.stats()
        e.ex('kill','-INT',tracer);e.ex('timeout','5','bash','-c','while test -e /proc/"$1"/status && ! grep -q "State:.*Z" /proc/"$1"/status; do sleep .02; done','bash',tracer,wall=7)
        for name in ['receive.counts','trace.log']:e.d('cp',e.b+':/state/'+name,out/(arm+'-'+name))
        h.record(out,dict(arm=arm,result=r,fuse={k:f1[k]-f0[k] for k in f0},store={k:s1[k]-s0[k] for k in s0},tids=tids));h.record(out,dict(kind='unmount',arm=arm,result=e.unmount()))
    finally:e.cleanup()
