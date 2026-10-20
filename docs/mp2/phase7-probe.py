#!/usr/bin/env python3
"""Read-only proc/fusectl evidence. Never opens a path within the FUSE mount."""
import glob,json,os,pathlib,sys

def read(p):
    try:return pathlib.Path(p).read_text(errors='replace')
    except OSError as e:return 'UNAVAILABLE '+str(e)
def link(p):
    try:return os.readlink(p)
    except OSError as e:return 'UNAVAILABLE '+str(e)
if len(sys.argv)>1 and sys.argv[1]=='namespaces':
    ns={}
    for p in glob.glob('/proc/[0-9]*/task/[0-9]*'):
        n=link(p+'/ns/mnt')
        if n not in ns:ns[n]=dict(representative=p,mountinfo=read(p+'/mountinfo'))
    print(json.dumps(ns));sys.exit()
processes={};connections=set()
for p in glob.glob('/proc/[0-9]*'):
    fds={}
    for fd in glob.glob(p+'/fd/*'):
        info=read(p+'/fdinfo/'+fd.rsplit('/',1)[1]);fds[fd]=dict(target=link(fd),info=info)
        for l in info.splitlines():
            if l.startswith('fuse_connection:'):connections.add(l.split()[1])
    threads={t:{k:read(t+'/'+k) for k in ['comm','wchan','stack','syscall','mountinfo']} for t in glob.glob(p+'/task/*')}
    processes[p]=dict(comm=read(p+'/comm'),cmdline=read(p+'/cmdline'),status=read(p+'/status'),cwd=link(p+'/cwd'),root=link(p+'/root'),fds=fds,threads=threads)
print(json.dumps(dict(processes=processes,waiting={c:read('/sys/fs/fuse/connections/'+c+'/waiting') for c in connections})))
