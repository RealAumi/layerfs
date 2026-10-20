#!/usr/bin/env python3
"""Preserve executables; remove only this campaign's Docker resources."""
import hashlib,json,pathlib,shutil,subprocess
home=pathlib.Path.home()/'lfs-remote/mp2-remote-store/phase4'
identity={}
for p in list((home/'bin').iterdir())+list((home.parent/'source/target-remote/debug/deps').glob('request_paths-*')):
    if not p.is_file() or p.suffix:continue
    digest=hashlib.sha256(p.read_bytes()).hexdigest();dest=home/'artifacts'/digest/p.name
    dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists():shutil.copy2(p,dest)
    identity[p.name]=dict(sha256=digest,path=str(dest))
(home/'receipts/binary-custody.json').write_text(json.dumps(identity,indent=2)+'\n')
commands=[['volume','rm',v] for v in ['mp2-p4-seed','mp2-p4-input']]+[['image','rm','mp2-p4-tools'],['ps','-a','--filter','name=mp2-p4','--format','{{.Names}}'],['network','ls','--filter','name=mp2-p4','--format','{{.Name}}'],['volume','ls','--filter','name=mp2-p4','--format','{{.Name}}']]
with (home/'receipts/cleanup.log').open('x') as f:
    for args in commands:
        p=subprocess.run(['/usr/local/bin/docker',*args],capture_output=True,text=True,timeout=30)
        f.write(json.dumps(dict(command=args,exit=p.returncode,output=p.stdout+p.stderr))+'\n');f.flush();assert p.returncode==0
        if 'ls' in args or args[0]=='ps':assert not p.stdout.strip(),p.stdout
