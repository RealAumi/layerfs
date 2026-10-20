#!/usr/bin/env python3
"""Warm-cache timed work. Preparation is explicit and outside the timed interval."""
import os,pathlib,subprocess,sys,time,json
mode,case,mount=sys.argv[1:];root=pathlib.Path(mount);dubbo=root/'dubbo'
paths=[root/'small'/f'f{i:05}' for i in range(5000)]
def call(args,**kw):
    r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=110,**kw)
    assert r.returncode==0,(args,r.returncode,r.stdout,r.stderr)
    return r.stdout
def work():
    if case=='status':
        for _ in range(20):assert call(['git','-c','safe.directory=*','-C',str(dubbo),'--no-optional-locks','status','--short'])==b''
        return 20
    if case=='find':return int(call(['bash','-o','pipefail','-c','find . -type f | wc -l'],cwd=dubbo))
    if case=='stat':
        data=pathlib.Path('/state/files0').read_bytes()
        call(['xargs','-0','stat','--cached=never','--printf=%s\n'],cwd=dubbo,input=data);return data.count(b'\0')
    if case=='small':
        total=0
        for p in paths:
            with p.open('rb') as f:total+=len(f.read())
        assert total==5000*1024;return total
    if case=='large':
        total=0
        with (root/'large.bin').open('rb') as f:
            while b:=f.read(1024*1024):total+=len(b)
        assert total==256*1024*1024;return total
    raise ValueError(case)
if mode=='prepare':
    if case=='stat':pathlib.Path('/state/files0').write_bytes(call(['find','.','-type','f','-print0'],cwd=dubbo))
    work()
    if case in ['small','large']:
        for p in paths if case=='small' else [root/'large.bin']:
            with p.open('rb') as f:os.posix_fadvise(f.fileno(),0,0,os.POSIX_FADV_DONTNEED)
    print(json.dumps(dict(prepared=case,policy='warm local objects; read workloads evict only FUSE data pages')))
else:
    t=time.perf_counter_ns();value=work();elapsed=time.perf_counter_ns()-t
    print(json.dumps(dict(case=case,ns=elapsed,value=value)))
